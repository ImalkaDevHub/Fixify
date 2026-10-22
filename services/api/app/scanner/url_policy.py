"""URL safety policy that every scanner destination must pass.

The policy is enforced twice: once before a scan is queued (fast feedback) and again by the
egress proxy for every connection the browser or link checker opens, including each
redirect hop and every sub-resource. The proxy connects to the exact IP address it
validated, which closes the DNS-rebinding gap between "check" and "use" for proxied traffic.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

from app.scanner.contract import PolicyConfig

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Awaitable[list[str]]]

_BLOCKED_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})
# Suffixes used for local, internal, or cloud-metadata names. Public DNS names do not use them.
_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".localdomain",
    ".internal",
    ".intranet",
    ".lan",
    ".home",
    ".home.arpa",
    ".corp",
    ".private",
)
# Addresses Python may report as global but that must never be reached by the scanner.
_EXTRA_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "0.0.0.0/8",
        "100.64.0.0/10",  # carrier-grade NAT
        "169.254.0.0/16",  # link-local, includes cloud metadata 169.254.169.254
        "192.0.0.0/24",
        "198.18.0.0/15",  # benchmarking
        "fd00:ec2::/32",  # AWS IPv6 metadata
        "64:ff9b::/96",  # NAT64 can map to private IPv4
        "2002::/16",  # 6to4 can embed private IPv4
    )
)


class BlockedDestinationError(ValueError):
    """The URL or host is not allowed by the scanner safety policy."""


class UnresolvableHostError(ValueError):
    """DNS resolution failed. This is a property of the website, not a policy block."""


@dataclass(frozen=True)
class AllowedDestination:
    host: str
    port: int
    address: str


def is_prohibited_address(address: IPAddress) -> bool:
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped or address.sixtofour
        if mapped is not None and is_prohibited_address(mapped):
            return True
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or not address.is_global
    ):
        return True
    return any(address in network for network in _EXTRA_BLOCKED_NETWORKS)


def normalize_host(host: str) -> str:
    host = host.strip().rstrip(".").lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        return host.encode("idna").decode("ascii") if host else host
    except UnicodeError as error:
        raise BlockedDestinationError("The host name is not valid.") from error


def _parse_ip(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    # Reject legacy numeric forms such as "2130706433" or "0x7f.1" that resolvers accept.
    try:
        return ipaddress.ip_address(socket.inet_aton(host))
    except OSError:
        return None


def check_hostname_rules(host: str) -> None:
    if not host:
        raise BlockedDestinationError("The URL has no host.")
    if host in _BLOCKED_HOSTNAMES or host.endswith(_BLOCKED_SUFFIXES):
        raise BlockedDestinationError("Local and internal host names are not allowed.")
    if _parse_ip(host) is None and "." not in host:
        # Single-label names ("postgres", "redis", "api") are internal service names.
        raise BlockedDestinationError("Single-label internal host names are not allowed.")


def split_http_url(url: str) -> tuple[SplitResult, str, int]:
    """Validate URL syntax and return (parts, normalized host, port)."""
    if len(url) > 2048:
        raise BlockedDestinationError("The URL is too long.")
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as error:
        raise BlockedDestinationError("The URL is not valid.") from error
    if parts.scheme not in ("http", "https"):
        raise BlockedDestinationError("Only HTTP and HTTPS URLs can be scanned.")
    if parts.username is not None or parts.password is not None:
        raise BlockedDestinationError("URLs with embedded credentials are not allowed.")
    host = normalize_host(parts.hostname or "")
    return parts, host, port or (443 if parts.scheme == "https" else 80)


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


class UrlPolicy:
    def __init__(self, config: PolicyConfig, resolver: Resolver = system_resolver) -> None:
        self.config = config
        self._resolver = resolver

    def _is_unsafe_allowed(self, host: str, port: int) -> bool:
        return f"{host}:{port}" in self.config.unsafe_allowed_hosts

    async def check_destination(self, host: str, port: int) -> AllowedDestination:
        """Resolve a host and return the single address the caller must connect to."""
        host = normalize_host(host)
        allow_private = self._is_unsafe_allowed(host, port)
        if not allow_private:
            check_hostname_rules(host)
            if port not in self.config.allowed_ports:
                raise BlockedDestinationError(f"Port {port} is not allowed.")

        literal = _parse_ip(host)
        if literal is not None:
            if not allow_private and is_prohibited_address(literal):
                raise BlockedDestinationError("Private, local, or reserved addresses are blocked.")
            return AllowedDestination(host, port, str(literal))

        try:
            addresses = await asyncio.wait_for(
                self._resolver(host, port), timeout=self.config.dns_timeout_seconds
            )
        except (OSError, TimeoutError) as error:
            raise UnresolvableHostError("The host name could not be resolved.") from error
        if not addresses:
            raise UnresolvableHostError("The host name could not be resolved.")

        parsed = [ipaddress.ip_address(address.split("%", 1)[0]) for address in addresses]
        if not allow_private and any(is_prohibited_address(address) for address in parsed):
            # Rejecting on ANY prohibited answer stops mixed public/private DNS responses.
            raise BlockedDestinationError(
                "The host resolves to a private, local, or reserved address."
            )
        return AllowedDestination(host, port, str(parsed[0]))

    async def check_url(self, url: str) -> AllowedDestination:
        _parts, host, port = split_http_url(url)
        return await self.check_destination(host, port)
