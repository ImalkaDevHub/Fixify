"""Link extraction and validation through the policy-enforcing egress proxy."""

import asyncio
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.scanner.egress_proxy import PROXY_HEADER
from app.scanner.url_policy import BlockedDestinationError, split_http_url

LinkVerdict = Literal["ok", "broken", "suspected", "inconclusive", "blocked"]

_MAX_REDIRECTS = 5
_CONFIRMED_BROKEN = frozenset({404, 410})
# Statuses that usually mean "the server refused a robot", not "the page is gone".
_INCONCLUSIVE = frozenset({400, 401, 403, 405, 406, 429, 451, 999})
USER_AGENT = "FixifyScanner/0.1 (+link check)"


@dataclass(frozen=True)
class LinkCheck:
    url: str
    verdict: LinkVerdict
    status: int | None = None
    final_url: str | None = None
    reason: str | None = None


def normalize_link(href: str, base_url: str) -> str | None:
    """Absolute HTTP(S) URL without fragment, or None for links that are not checked."""
    href = href.strip()
    if not href or href.startswith("#"):
        return None
    try:
        absolute = urljoin(base_url, href)
        parts = urlsplit(absolute)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None  # mailto:, tel:, javascript:, data:, ...
    if parts.username or parts.password:
        return None
    netloc = parts.hostname.lower()
    if parts.port and parts.port != (443 if parts.scheme == "https" else 80):
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))


def select_links(hrefs: list[str], base_url: str, limit: int) -> tuple[list[str], int]:
    """Deduplicated links to check (up to limit) and the number of unique links found."""
    unique: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        link = normalize_link(href, base_url)
        if link is not None and link not in seen:
            seen.add(link)
            unique.append(link)
    return unique[:limit], len(unique)


def classify_status(status: int) -> LinkVerdict:
    if status < 400:
        return "ok"
    if status in _CONFIRMED_BROKEN:
        return "broken"
    if status in _INCONCLUSIVE:
        return "inconclusive"
    if 500 <= status <= 599:
        return "suspected"  # may be temporary; reported as suspected, not confirmed
    return "inconclusive"


class LinkChecker:
    def __init__(self, proxy_url: str, *, timeout_seconds: int, concurrency: int) -> None:
        self._client = httpx.AsyncClient(
            proxy=proxy_url,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,  # every hop is followed manually and goes through the proxy
            trust_env=False,
            headers={"User-Agent": USER_AGENT},
        )
        self._semaphore = asyncio.Semaphore(concurrency)

    async def __aenter__(self) -> "LinkChecker":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self._client.aclose()

    async def check_all(self, urls: list[str]) -> list[LinkCheck]:
        return list(await asyncio.gather(*(self.check(url) for url in urls)))

    async def check(self, url: str) -> LinkCheck:
        async with self._semaphore:
            try:
                return await self._follow(url)
            except httpx.TimeoutException:
                return LinkCheck(url, "inconclusive", reason="timeout")
            except httpx.ProxyError as error:
                return self._proxy_failure(url, str(error))
            except httpx.HTTPError as error:
                return LinkCheck(url, "inconclusive", reason=type(error).__name__)

    async def _follow(self, url: str) -> LinkCheck:
        current = url
        for _hop in range(_MAX_REDIRECTS + 1):
            try:
                split_http_url(current)
            except BlockedDestinationError:
                return LinkCheck(url, "blocked", final_url=current, reason="blocked_by_policy")
            response = await self._request(current)
            proxy_reason = response.headers.get(PROXY_HEADER)
            if proxy_reason:
                return self._proxy_failure(url, proxy_reason, final_url=current)
            location = response.headers.get("location")
            if response.status_code in (301, 302, 303, 307, 308) and location:
                current = urljoin(current, location)
                continue
            verdict = classify_status(response.status_code)
            return LinkCheck(url, verdict, status=response.status_code, final_url=current)
        return LinkCheck(url, "inconclusive", final_url=current, reason="too_many_redirects")

    async def _request(self, url: str) -> httpx.Response:
        response = await self._client.head(url)
        if response.status_code in (403, 405, 501) and not response.headers.get(PROXY_HEADER):
            # Some servers reject HEAD; retry with GET but never read the body.
            async with self._client.stream("GET", url) as streamed:
                return streamed
        return response

    @staticmethod
    def _proxy_failure(url: str, reason: str, final_url: str | None = None) -> LinkCheck:
        if "blocked_by_policy" in reason or "403" in reason:
            return LinkCheck(url, "blocked", final_url=final_url, reason="blocked_by_policy")
        if "dns_failure" in reason:
            # The domain does not resolve: strong evidence, but DNS can fail transiently.
            return LinkCheck(url, "suspected", final_url=final_url, reason="dns_failure")
        return LinkCheck(url, "inconclusive", final_url=final_url, reason="connection_failed")
