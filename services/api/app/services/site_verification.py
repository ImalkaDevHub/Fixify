"""Website ownership verification.

A project owner proves control of a website by publishing a token, either as
``<meta name="fixify-site-verification" content="TOKEN">`` on the home page or as the content of
``/.well-known/fixify-verification.txt``. The check goes through the scanner's egress proxy, so
it obeys exactly the same SSRF policy (private addresses, ports, DNS rebinding) as scans.
"""

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.project import Project
from app.repositories import project as project_repository
from app.scanner.egress_proxy import EgressProxy
from app.scanner.url_policy import BlockedDestinationError, UnresolvableHostError, UrlPolicy

logger = logging.getLogger(__name__)

META_NAME = "fixify-site-verification"
WELL_KNOWN_PATH = "/.well-known/fixify-verification.txt"
_MAX_BYTES = 256_000
_MAX_REDIRECTS = 3
_TIMEOUT_SECONDS = 8


class VerificationError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class VerificationState:
    required: bool
    verified: bool
    host: str
    verified_at: datetime | None
    method: str | None
    token: str
    meta_tag: str
    file_url: str


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def is_verified(project: Project) -> bool:
    return bool(project.verified_at and project.verified_host == host_of(project.website_url))


def reset_if_host_changed(project: Project) -> None:
    if project.verified_host and project.verified_host != host_of(project.website_url):
        project.verified_at = None
        project.verified_host = None
        project.verification_method = None


def state_for(project: Project, config: Settings) -> VerificationState:
    assert project.verification_token
    parts = urlsplit(project.website_url)
    return VerificationState(
        required=config.site_verification_required,
        verified=is_verified(project),
        host=host_of(project.website_url),
        verified_at=project.verified_at if is_verified(project) else None,
        method=project.verification_method if is_verified(project) else None,
        token=project.verification_token,
        meta_tag=f'<meta name="{META_NAME}" content="{project.verification_token}">',
        file_url=f"{parts.scheme}://{parts.netloc}{WELL_KNOWN_PATH}",
    )


async def get_state(
    session: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID, config: Settings
) -> VerificationState:
    project = await project_repository.get_project(session, project_id, owner_id)
    if project is None:
        raise VerificationError("Project not found.", 404)
    if not project.verification_token:
        project.verification_token = "fixify-" + secrets.token_urlsafe(24)
        await session.commit()
    return state_for(project, config)


class _MetaFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        attributes = {key.lower(): (value or "") for key, value in attrs}
        if attributes.get("name", "").lower() == META_NAME:
            self.values.append(attributes.get("content", "").strip())


def meta_tokens(html: str) -> list[str]:
    finder = _MetaFinder()
    try:
        finder.feed(html)
        finder.close()
    except Exception:  # noqa: BLE001 - malformed third-party HTML simply has no token
        return []
    return finder.values


async def _fetch(client: httpx.AsyncClient, url: str, host: str) -> tuple[int, str] | None:
    """GET with manual, same-host redirects and a bounded body. None if unreachable."""
    for _ in range(_MAX_REDIRECTS + 1):
        try:
            async with client.stream("GET", url) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    target = urljoin(url, response.headers.get("location", ""))
                    if host_of(target) != host or urlsplit(target).scheme not in ("http", "https"):
                        return None  # verification never follows a redirect to another host
                    url = target
                    continue
                body = b""
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) >= _MAX_BYTES:
                        break
                return response.status_code, body[:_MAX_BYTES].decode("utf-8", "replace")
        except httpx.HTTPError:
            return None
    return None


async def check(
    session: AsyncSession,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    policy: UrlPolicy,
    config: Settings,
) -> VerificationState:
    state = await get_state(session, owner_id, project_id, config)
    project = await project_repository.get_project(session, project_id, owner_id)
    assert project is not None
    try:
        await policy.check_url(project.website_url)
    except BlockedDestinationError as error:
        raise VerificationError(f"This URL cannot be checked: {error}", 422) from error
    except UnresolvableHostError as error:
        raise VerificationError("The website's host name could not be resolved.", 422) from error

    proxy = EgressProxy(policy)
    await proxy.start()
    method = None
    try:
        async with httpx.AsyncClient(
            proxy=proxy.url,
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "FixifyVerification/1.0"},
        ) as client:
            fetched = await _fetch(client, state.file_url, state.host)
            if (
                fetched
                and fetched[0] == 200
                and fetched[1].strip().splitlines()[:1] == [state.token]
            ):
                method = "file"
            else:
                page = await _fetch(client, project.website_url, state.host)
                if page and page[0] < 400 and state.token in meta_tokens(page[1]):
                    method = "meta"
    finally:
        await proxy.close()

    if method is None:
        raise VerificationError(
            "The verification token was not found. Add the meta tag to the home page or "
            f"publish the token at {state.file_url}, then check again.",
            422,
        )
    project.verified_at = datetime.now(UTC)
    project.verified_host = state.host
    project.verification_method = method
    await session.commit()
    logger.info("Project %s verified %s via %s", project.id, state.host, method)
    return state_for(project, config)
