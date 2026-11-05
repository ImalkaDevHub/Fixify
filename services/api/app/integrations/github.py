"""Minimal GitHub REST client (OAuth token per user).

Only the endpoints Fixify needs. Repositories are read file by file through the API and written
only through the Git Data API on new branches; nothing is cloned or executed.
"""

import base64
import logging
import posixpath
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

_API_VERSION = "2022-11-28"
_MAX_RESPONSE_BYTES = 8_000_000
_BRANCH = re.compile(r"^(?!/)(?!.*//)(?!.*\.\.)(?!.*@\{)[A-Za-z0-9._/-]{1,255}(?<!/)(?<!\.lock)$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


class GitHubError(Exception):
    def __init__(self, public_message: str, *, status: int = 502, retryable: bool = False) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.status = status
        self.retryable = retryable


class GitHubAuthError(GitHubError):
    """The token was revoked or lacks access: the user must reconnect."""


class GitHubNotFoundError(GitHubError):
    pass


class GitHubConflictError(GitHubError):
    pass


def valid_repo_name(full_name: str) -> bool:
    owner, _, name = full_name.partition("/")
    return bool(_REPO.fullmatch(full_name)) and {owner, name}.isdisjoint({".", ".."})


def valid_branch_name(branch: str) -> bool:
    return bool(_BRANCH.fullmatch(branch)) and not branch.endswith(".")


def safe_repo_path(path: str) -> str | None:
    """Normalize a repository-relative path; None if it could escape the repository."""
    if not path or len(path) > 300 or "\\" in path or "\x00" in path or path.startswith("/"):
        return None
    normalized = posixpath.normpath(path)
    if normalized in (".", "") or normalized.startswith("../") or normalized == "..":
        return None
    if any(part in ("", ".", "..") for part in normalized.split("/")):
        return None
    if normalized.split("/", 1)[0] == ".git":
        return None
    return normalized


@dataclass(frozen=True)
class TreeEntry:
    path: str
    sha: str
    size: int
    mode: str


@dataclass(frozen=True)
class FileContent:
    path: str
    sha: str
    text: str
    size: int


class GitHubClient:
    def __init__(
        self,
        token: str,
        config: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=config.github_api_url.rstrip("/"),
            timeout=config.github_timeout_seconds,
            transport=transport,
            follow_redirects=False,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": _API_VERSION,
                "User-Agent": "Fixify",
            },
        )

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self._client.aclose()

    async def _request(
        self, method: str, path: str, *, json: Any = None, params: dict[str, Any] | None = None
    ) -> tuple[Any, httpx.Headers]:
        try:
            response = await self._client.request(method, path, json=json, params=params)
        except httpx.TimeoutException as error:
            raise GitHubError("GitHub did not respond in time.", retryable=True) from error
        except httpx.HTTPError as error:
            raise GitHubError("GitHub could not be reached.", retryable=True) from error
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise GitHubError("GitHub returned more data than Fixify accepts.")
        status = response.status_code
        if status == 401:
            raise GitHubAuthError(
                "GitHub rejected the stored token. Reconnect your GitHub account.", status=409
            )
        if status == 403 and response.headers.get("x-ratelimit-remaining") == "0":
            raise GitHubError(
                "GitHub's API rate limit was reached. Try again later.", status=429, retryable=True
            )
        if status == 429:
            raise GitHubError("GitHub is rate limiting requests.", status=429, retryable=True)
        if status in (403, 404):
            raise GitHubNotFoundError(
                "The repository or file was not found, or your GitHub account lacks access.",
                status=404,
            )
        if status in (409, 422):
            message = _github_message(response)
            raise GitHubConflictError(f"GitHub refused the change: {message}", status=409)
        if status >= 500:
            raise GitHubError("GitHub returned a server error.", retryable=True)
        if status >= 400:
            raise GitHubError(f"GitHub returned HTTP {status}.")
        if status == 204 or not response.content:
            return None, response.headers
        return response.json(), response.headers

    # --- Account and repositories -----------------------------------------------------------

    async def current_user(self) -> tuple[dict[str, Any], str]:
        data, headers = await self._request("GET", "/user")
        return data, headers.get("x-oauth-scopes", "")

    async def list_repositories(self, max_pages: int = 5) -> list[dict[str, Any]]:
        repos: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            data, _ = await self._request(
                "GET",
                "/user/repos",
                params={
                    "per_page": 100,
                    "page": page,
                    "sort": "updated",
                    "affiliation": "owner,collaborator,organization_member",
                },
            )
            repos.extend(data or [])
            if not data or len(data) < 100:
                break
        return repos

    async def repository(self, full_name: str) -> dict[str, Any]:
        data, _ = await self._request("GET", f"/repos/{_repo(full_name)}")
        return data

    async def branches(self, full_name: str, max_pages: int = 3) -> list[str]:
        names: list[str] = []
        for page in range(1, max_pages + 1):
            data, _ = await self._request(
                "GET", f"/repos/{_repo(full_name)}/branches", params={"per_page": 100, "page": page}
            )
            names.extend(item["name"] for item in data or [])
            if not data or len(data) < 100:
                break
        return names

    async def branch_head(self, full_name: str, branch: str) -> str:
        data, _ = await self._request(
            "GET", f"/repos/{_repo(full_name)}/git/ref/heads/{quote(branch, safe='/')}"
        )
        return data["object"]["sha"]

    # --- Reading files -----------------------------------------------------------------------

    async def tree(self, full_name: str, commit_sha: str) -> tuple[list[TreeEntry], bool]:
        data, _ = await self._request(
            "GET",
            f"/repos/{_repo(full_name)}/git/trees/{quote(commit_sha)}",
            params={"recursive": "1"},
        )
        entries = []
        for item in data.get("tree", [])[:20_000]:
            path = safe_repo_path(str(item.get("path", "")))
            if item.get("type") == "blob" and path:
                entries.append(
                    TreeEntry(
                        path=path,
                        sha=item["sha"],
                        size=int(item.get("size") or 0),
                        mode=str(item.get("mode", "100644")),
                    )
                )
        return entries, bool(data.get("truncated"))

    async def blob_text(self, full_name: str, entry: TreeEntry) -> FileContent | None:
        """UTF-8 text of a blob, or None if it is too large or binary."""
        if entry.size > self._config.github_max_file_bytes:
            return None
        data, _ = await self._request(
            "GET", f"/repos/{_repo(full_name)}/git/blobs/{quote(entry.sha)}"
        )
        if data.get("encoding") != "base64":
            return None
        raw = base64.b64decode(data.get("content", ""))
        if len(raw) > self._config.github_max_file_bytes or b"\x00" in raw:
            return None
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return FileContent(path=entry.path, sha=entry.sha, text=text, size=len(raw))

    # --- Writing (new branches and pull requests only) --------------------------------------

    async def commit_tree_sha(self, full_name: str, commit_sha: str) -> str:
        data, _ = await self._request(
            "GET", f"/repos/{_repo(full_name)}/git/commits/{quote(commit_sha)}"
        )
        return data["tree"]["sha"]

    async def create_blob(self, full_name: str, text: str) -> str:
        data, _ = await self._request(
            "POST",
            f"/repos/{_repo(full_name)}/git/blobs",
            json={"content": text, "encoding": "utf-8"},
        )
        return data["sha"]

    async def create_tree(
        self, full_name: str, base_tree: str, files: list[tuple[str, str, str]]
    ) -> str:
        data, _ = await self._request(
            "POST",
            f"/repos/{_repo(full_name)}/git/trees",
            json={
                "base_tree": base_tree,
                "tree": [
                    {"path": path, "mode": mode, "type": "blob", "sha": sha}
                    for path, mode, sha in files
                ],
            },
        )
        return data["sha"]

    async def create_commit(self, full_name: str, message: str, tree: str, parent: str) -> str:
        data, _ = await self._request(
            "POST",
            f"/repos/{_repo(full_name)}/git/commits",
            json={"message": message, "tree": tree, "parents": [parent]},
        )
        return data["sha"]

    async def create_branch(self, full_name: str, branch: str, sha: str) -> None:
        await self._request(
            "POST",
            f"/repos/{_repo(full_name)}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )

    async def branch_exists(self, full_name: str, branch: str) -> str | None:
        try:
            return await self.branch_head(full_name, branch)
        except GitHubNotFoundError:
            return None

    async def find_pull_request(self, full_name: str, head: str) -> dict[str, Any] | None:
        owner = full_name.split("/", 1)[0]
        data, _ = await self._request(
            "GET",
            f"/repos/{_repo(full_name)}/pulls",
            params={"head": f"{owner}:{head}", "state": "all", "per_page": 1},
        )
        return data[0] if data else None

    async def create_pull_request(
        self, full_name: str, *, title: str, body: str, head: str, base: str
    ) -> dict[str, Any]:
        data, _ = await self._request(
            "POST",
            f"/repos/{_repo(full_name)}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "maintainer_can_modify": True,
            },
        )
        return data

    async def pull_request(self, full_name: str, number: int) -> dict[str, Any]:
        data, _ = await self._request("GET", f"/repos/{_repo(full_name)}/pulls/{int(number)}")
        return data


def _repo(full_name: str) -> str:
    if not valid_repo_name(full_name):
        raise GitHubError("Invalid repository name.", status=422)
    owner, name = full_name.split("/", 1)
    return f"{quote(owner, safe='')}/{quote(name, safe='')}"


def _github_message(response: httpx.Response) -> str:
    try:
        message = str(response.json().get("message", ""))[:200]
    except ValueError:
        message = ""
    return message or f"HTTP {response.status_code}"


async def exchange_oauth_code(
    code: str,
    redirect_uri: str,
    config: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Exchange an authorization code for a user access token."""
    async with httpx.AsyncClient(
        timeout=config.github_timeout_seconds, transport=transport, follow_redirects=False
    ) as client:
        try:
            response = await client.post(
                f"{config.github_web_url.rstrip('/')}/login/oauth/access_token",
                data={
                    "client_id": config.github_client_id,
                    "client_secret": config.github_client_secret.get_secret_value(),
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json", "User-Agent": "Fixify"},
            )
        except httpx.HTTPError as error:
            raise GitHubError("GitHub could not be reached.", retryable=True) from error
    try:
        data = response.json()
    except ValueError as error:
        raise GitHubError("GitHub returned an unexpected response.") from error
    token = data.get("access_token") if isinstance(data, dict) else None
    if response.status_code != 200 or not token:
        raise GitHubAuthError("GitHub did not authorize the connection. Try again.", status=400)
    return str(token)


async def revoke_oauth_grant(
    token: str, config: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    """Best effort: remove Fixify's authorization from the user's GitHub account."""
    async with httpx.AsyncClient(
        base_url=config.github_api_url.rstrip("/"),
        timeout=config.github_timeout_seconds,
        transport=transport,
    ) as client:
        try:
            await client.request(
                "DELETE",
                f"/applications/{quote(config.github_client_id, safe='')}/grant",
                auth=(config.github_client_id, config.github_client_secret.get_secret_value()),
                json={"access_token": token},
                headers={"Accept": "application/vnd.github+json", "User-Agent": "Fixify"},
            )
        except httpx.HTTPError:
            logger.warning("Could not revoke the GitHub grant; the token is deleted locally")
