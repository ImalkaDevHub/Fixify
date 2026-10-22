import ipaddress

import pytest

from app.scanner.url_policy import (
    BlockedDestinationError,
    UnresolvableHostError,
    is_prohibited_address,
    split_http_url,
)
from tests.conftest import fake_policy


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "gopher://example.com/",
        "https://user:pass@example.com/",
        "https://user@example.com/",
        "http://localhost/",
        "http://LOCALHOST./",
        "http://app.localhost/",
        "http://printer.local/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://postgres:5432/",
        "http://redis/",
        "http://127.0.0.1/",
        "http://127.1/",
        "http://2130706433/",
        "http://0x7f000001/",
        "http://0.0.0.0/",
        "http://10.1.2.3/",
        "http://172.16.0.1/",
        "http://192.168.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://224.0.0.1/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fd00::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::]/",
        "https://example.com:22/",
        "https://example.com:6379/",
        "http://internal.example.org/",
        "http://mixed.example.org/",
        "http://rebind.example.org/",
        "http://metadata.example.org/",
        "http://v6private.example.org/",
        "http://mapped.example.org/",
    ],
)
async def test_prohibited_targets_are_blocked(url):
    with pytest.raises(BlockedDestinationError):
        await fake_policy().check_url(url)


@pytest.mark.parametrize(
    "url", ["https://example.com/", "http://www.example.com:8080/path?q=1", "https://93.184.215.14/"]
)
async def test_public_targets_are_allowed(url):
    destination = await fake_policy().check_url(url)
    assert not is_prohibited_address(ipaddress.ip_address(destination.address))


async def test_connection_address_is_the_validated_address():
    destination = await fake_policy().check_url("https://example.com/")
    assert destination.address == "93.184.215.14"


async def test_unresolvable_host_is_not_a_policy_block():
    with pytest.raises(UnresolvableHostError):
        await fake_policy().check_url("https://does-not-exist.example.net/")


async def test_unsafe_allowlist_is_exact_host_and_port():
    policy = fake_policy(unsafe_allowed_hosts=frozenset({"127.0.0.1:4100"}))
    assert (await policy.check_url("http://127.0.0.1:4100/")).address == "127.0.0.1"
    with pytest.raises(BlockedDestinationError):
        await policy.check_url("http://127.0.0.1:4101/")
    with pytest.raises(BlockedDestinationError):
        await policy.check_url("http://localhost:4100/")


async def test_dns_timeout_is_treated_as_unresolvable():
    import asyncio

    from app.scanner.contract import PolicyConfig
    from app.scanner.url_policy import UrlPolicy

    async def slow(_host: str, _port: int) -> list[str]:
        await asyncio.sleep(5)
        return ["93.184.215.14"]

    policy = UrlPolicy(PolicyConfig(dns_timeout_seconds=0.05), resolver=slow)
    with pytest.raises(UnresolvableHostError):
        await policy.check_url("https://slow.example.com/")


def test_url_syntax_rules():
    _parts, host, port = split_http_url("HTTPS://Example.COM./a")
    assert (host, port) == ("example.com", 443)
    with pytest.raises(BlockedDestinationError):
        split_http_url("https://example.com:99999/")
    with pytest.raises(BlockedDestinationError):
        split_http_url("https://example.com/" + "a" * 2100)
