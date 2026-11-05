"""GitHub account connection, repository selection, and controlled file access."""

import hashlib
import hmac
import logging
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import (
    DecryptionError,
    EncryptionUnavailableError,
    decrypt_secret,
    encrypt_secret,
)
from app.db.models.platform import GitHubConnection
from app.db.models.project import Project
from app.integrations.github import (
    FileContent,
    GitHubAuthError,
    GitHubClient,
    GitHubError,
    TreeEntry,
    exchange_oauth_code,
    revoke_oauth_grant,
    valid_branch_name,
    valid_repo_name,
)
from app.services.repository_files import readable_entries

logger = logging.getLogger(__name__)

STATE_TTL_SECONDS = 600
# Tests replace this with an httpx.MockTransport; production uses the network.
transport: httpx.AsyncBaseTransport | None = None


class GitHubServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def from_github_error(error: GitHubError) -> GitHubServiceError:
    return GitHubServiceError(error.public_message, error.status if error.status < 500 else 502)


def callback_url(config: Settings) -> str:
    # A web-app page: it posts the code to the API with the normal session and CSRF checks.
    return f"{config.public_app_url.rstrip('/')}/github/callback"


def _require_configured(config: Settings) -> None:
    if not config.github_configured:
        raise GitHubServiceError(
            "GitHub integration is not configured on this server "
            "(GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, TOKEN_ENCRYPTION_KEY).",
            503,
        )


# --- OAuth ----------------------------------------------------------------------------------


def _sign(payload: str, config: Settings) -> str:
    return hmac.new(
        config.secret_key.get_secret_value().encode(),
        f"github-oauth:{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()


def start_oauth(user_id: uuid.UUID, config: Settings) -> tuple[str, str]:
    """Returns (authorization URL, nonce). The nonce goes in an HttpOnly cookie, so a state
    value leaked or forged elsewhere cannot complete the flow in another browser."""
    _require_configured(config)
    nonce = secrets.token_urlsafe(24)
    expires = int(time.time()) + STATE_TTL_SECONDS
    payload = f"{user_id}.{nonce}.{expires}"
    state = f"{payload}.{_sign(payload, config)}"
    query = urlencode(
        {
            "client_id": config.github_client_id,
            "redirect_uri": callback_url(config),
            "scope": config.github_oauth_scopes,
            "state": state,
            "allow_signup": "false",
        }
    )
    return f"{config.github_web_url.rstrip('/')}/login/oauth/authorize?{query}", nonce


def verify_state(
    state: str, nonce_cookie: str | None, user_id: uuid.UUID, config: Settings
) -> None:
    parts = state.split(".")
    if len(parts) != 4 or not nonce_cookie:
        raise GitHubServiceError("The GitHub connection request is invalid. Start again.")
    state_user, nonce, expires, signature = parts
    payload = f"{state_user}.{nonce}.{expires}"
    if not hmac.compare_digest(signature, _sign(payload, config)):
        raise GitHubServiceError("The GitHub connection request is invalid. Start again.")
    if state_user != str(user_id) or not hmac.compare_digest(nonce, nonce_cookie):
        raise GitHubServiceError("The GitHub connection request belongs to another session.")
    if not expires.isdigit() or int(expires) < time.time():
        raise GitHubServiceError("The GitHub connection request expired. Start again.")


async def complete_oauth(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    code: str,
    state: str,
    nonce_cookie: str | None,
    config: Settings,
) -> GitHubConnection:
    _require_configured(config)
    verify_state(state, nonce_cookie, user_id, config)
    try:
        token = await exchange_oauth_code(code, callback_url(config), config, transport)
        async with GitHubClient(token, config, transport) as client:
            profile, scopes = await client.current_user()
    except GitHubError as error:
        raise from_github_error(error) from error
    try:
        encrypted = encrypt_secret(token, config)
    except EncryptionUnavailableError as error:
        raise GitHubServiceError(str(error), 503) from error

    connection = await get_connection(session, user_id)
    if connection is None:
        connection = GitHubConnection(user_id=user_id)
        session.add(connection)
    connection.github_user_id = str(profile.get("id", ""))[:32]
    connection.login = str(profile.get("login", ""))[:100]
    connection.avatar_url = str(profile.get("avatar_url") or "")[:500] or None
    connection.scopes = scopes[:200]
    connection.token_encrypted = encrypted
    connection.status = "active"
    connection.last_validated_at = datetime.now(UTC)
    await session.commit()
    return connection


async def get_connection(session: AsyncSession, user_id: uuid.UUID) -> GitHubConnection | None:
    return await session.scalar(select(GitHubConnection).where(GitHubConnection.user_id == user_id))


async def disconnect(session: AsyncSession, user_id: uuid.UUID, config: Settings) -> bool:
    connection = await get_connection(session, user_id)
    if connection is None:
        return False
    token = None
    try:
        token = decrypt_secret(connection.token_encrypted, config)
    except (DecryptionError, EncryptionUnavailableError):
        pass
    await session.delete(connection)
    await session.commit()
    if token and config.github_configured:
        await revoke_oauth_grant(token, config, transport)
    return True


@dataclass
class ConnectedClient:
    connection: GitHubConnection
    client: GitHubClient


async def open_client(
    session: AsyncSession, user_id: uuid.UUID, config: Settings
) -> ConnectedClient:
    """A GitHub client for the user's own connection. Use as `async with result.client`."""
    _require_configured(config)
    connection = await get_connection(session, user_id)
    if connection is None:
        raise GitHubServiceError("Connect your GitHub account first.", 409)
    if connection.status != "active":
        raise GitHubServiceError("GitHub access was revoked. Reconnect your GitHub account.", 409)
    try:
        token = decrypt_secret(connection.token_encrypted, config)
    except (DecryptionError, EncryptionUnavailableError) as error:
        raise GitHubServiceError(
            "The stored GitHub token cannot be decrypted. Reconnect your GitHub account.", 409
        ) from error
    return ConnectedClient(connection, GitHubClient(token, config, transport))


async def mark_revoked(session: AsyncSession, connection: GitHubConnection) -> None:
    connection.status = "revoked"
    await session.commit()
    logger.info("GitHub connection %s marked revoked", connection.id)


async def handle_auth_failure(
    session: AsyncSession, user_id: uuid.UUID, error: GitHubError
) -> None:
    if isinstance(error, GitHubAuthError):
        connection = await get_connection(session, user_id)
        if connection is not None:
            await mark_revoked(session, connection)


def repo_read(data: dict) -> dict:
    permissions = data.get("permissions") or {}
    return {
        "id": str(data.get("id", "")),
        "full_name": data.get("full_name", ""),
        "private": bool(data.get("private")),
        "default_branch": data.get("default_branch") or "main",
        "description": (data.get("description") or "")[:300] or None,
        "html_url": data.get("html_url"),
        "can_push": bool(permissions.get("push")),
        "updated_at": data.get("updated_at"),
    }


async def list_repositories(
    session: AsyncSession, user_id: uuid.UUID, config: Settings
) -> list[dict]:
    connected = await open_client(session, user_id, config)
    try:
        async with connected.client as client:
            repos = await client.list_repositories()
    except GitHubError as error:
        await handle_auth_failure(session, user_id, error)
        raise from_github_error(error) from error
    return [repo_read(repo) for repo in repos if valid_repo_name(repo.get("full_name", ""))]


async def list_branches(
    session: AsyncSession, user_id: uuid.UUID, full_name: str, config: Settings
) -> list[str]:
    if not valid_repo_name(full_name):
        raise GitHubServiceError("Use the owner/repository format.", 422)
    connected = await open_client(session, user_id, config)
    try:
        async with connected.client as client:
            return await client.branches(full_name)
    except GitHubError as error:
        await handle_auth_failure(session, user_id, error)
        raise from_github_error(error) from error


async def connect_repository(
    session: AsyncSession,
    user_id: uuid.UUID,
    project: Project,
    full_name: str,
    branch: str | None,
    config: Settings,
) -> tuple[Project, dict]:
    """Verify with the user's own token that the repository is accessible, then link it."""
    if not valid_repo_name(full_name):
        raise GitHubServiceError("Use the owner/repository format.", 422)
    if branch is not None and not valid_branch_name(branch):
        raise GitHubServiceError("That branch name is not valid.", 422)
    connected = await open_client(session, user_id, config)
    try:
        async with connected.client as client:
            repo = repo_read(await client.repository(full_name))
            branch = branch or repo["default_branch"]
            await client.branch_head(full_name, branch)
    except GitHubError as error:
        await handle_auth_failure(session, user_id, error)
        raise from_github_error(error) from error
    project.repo_full_name = repo["full_name"]
    project.github_repo_id = repo["id"]
    project.default_branch = branch
    await session.commit()
    await session.refresh(project)
    return project, repo


async def disconnect_repository(session: AsyncSession, project: Project) -> Project:
    project.repo_full_name = None
    project.github_repo_id = None
    project.default_branch = None
    await session.commit()
    await session.refresh(project)
    return project


@dataclass
class RepositorySnapshot:
    full_name: str
    branch: str
    commit_sha: str
    entries: list[TreeEntry]
    truncated: bool


async def snapshot(client: GitHubClient, project: Project, config: Settings) -> RepositorySnapshot:
    if not project.repo_full_name:
        raise GitHubServiceError("This project has no connected repository.", 409)
    branch = project.default_branch or "main"
    commit_sha = await client.branch_head(project.repo_full_name, branch)
    entries, truncated = await client.tree(project.repo_full_name, commit_sha)
    return RepositorySnapshot(
        full_name=project.repo_full_name,
        branch=branch,
        commit_sha=commit_sha,
        entries=readable_entries(entries, config.github_max_file_bytes),
        truncated=truncated,
    )


async def read_files(
    client: GitHubClient, snap: RepositorySnapshot, paths: list[str], config: Settings
) -> list[FileContent]:
    """Read at most GITHUB_MAX_FILES_PER_FIX allowed text files, within the byte budget."""
    by_path = {entry.path: entry for entry in snap.entries}
    files: list[FileContent] = []
    budget = config.github_max_context_bytes
    for path in paths:
        entry = by_path.get(path)  # only paths from the allow-listed tree are ever fetched
        if entry is None or entry.size > budget:
            continue
        content = await client.blob_text(snap.full_name, entry)
        if content is None:
            continue
        files.append(content)
        budget -= content.size
        if len(files) >= config.github_max_files_per_fix:
            break
    return files
