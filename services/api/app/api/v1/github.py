import uuid
from typing import Annotated, NoReturn

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Auth, DatabaseSession, Limiter, VerifiedAuth, enforce_limit
from app.core.config import settings
from app.integrations.github import GitHubError
from app.schemas.platform import (
    GitHubAuthorize,
    GitHubStatus,
    RepositoryConnect,
    RepositoryFile,
    RepositoryRead,
    RepositoryTree,
)
from app.schemas.project import ProjectRead
from app.services import github as github_service
from app.services import project as project_service

router = APIRouter(tags=["github"])
NONCE_COOKIE = "fixify_gh_oauth"


class OAuthComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=200)
    state: str = Field(min_length=1, max_length=400)


def _raise(error: github_service.GitHubServiceError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from error


@router.get("/github/status", response_model=GitHubStatus)
async def github_status(auth: Auth, session: DatabaseSession) -> GitHubStatus:
    connection = await github_service.get_connection(session, auth.user.id)
    if connection is None:
        return GitHubStatus(configured=settings.github_configured, connected=False)
    return GitHubStatus(
        configured=settings.github_configured,
        connected=connection.status == "active",
        status=connection.status,
        login=connection.login,
        avatar_url=connection.avatar_url,
        scopes=[scope.strip() for scope in connection.scopes.split(",") if scope.strip()],
        connected_at=connection.created_at,
    )


@router.post("/github/connect", response_model=GitHubAuthorize)
async def start_connect(
    auth: VerifiedAuth, response: Response, limiter: Limiter
) -> GitHubAuthorize:
    """Begin the OAuth flow. The browser is sent to GitHub, then back to /github/callback."""
    await enforce_limit(limiter, f"github:connect:{auth.user.id}", 20, 3_600, "Too many attempts.")
    try:
        url, nonce = github_service.start_oauth(auth.user.id, settings)
    except github_service.GitHubServiceError as error:
        _raise(error)
    response.set_cookie(
        NONCE_COOKIE,
        nonce,
        max_age=github_service.STATE_TTL_SECONDS,
        path="/api/v1/github",
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
    )
    return GitHubAuthorize(authorize_url=url)


@router.post("/github/complete", response_model=GitHubStatus)
async def complete_connect(
    data: OAuthComplete,
    request: Request,
    response: Response,
    auth: VerifiedAuth,
    session: DatabaseSession,
) -> GitHubStatus:
    try:
        await github_service.complete_oauth(
            session,
            auth.user.id,
            code=data.code,
            state=data.state,
            nonce_cookie=request.cookies.get(NONCE_COOKIE),
            config=settings,
        )
    except github_service.GitHubServiceError as error:
        _raise(error)
    finally:
        response.delete_cookie(NONCE_COOKIE, path="/api/v1/github")
    return await github_status(auth, session)


@router.delete("/github/connection", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(auth: Auth, session: DatabaseSession) -> Response:
    """Delete the stored token and revoke Fixify's grant on GitHub (best effort)."""
    if not await github_service.disconnect(session, auth.user.id, settings):
        raise HTTPException(status_code=404, detail="No GitHub account is connected.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/github/repositories", response_model=list[RepositoryRead])
async def repositories(auth: Auth, session: DatabaseSession) -> list[RepositoryRead]:
    try:
        repos = await github_service.list_repositories(session, auth.user.id, settings)
    except github_service.GitHubServiceError as error:
        _raise(error)
    return [RepositoryRead(**repo) for repo in repos]


@router.get("/github/repositories/{owner}/{name}/branches", response_model=list[str])
async def branches(owner: str, name: str, auth: Auth, session: DatabaseSession) -> list[str]:
    try:
        return await github_service.list_branches(
            session, auth.user.id, f"{owner}/{name}", settings
        )
    except github_service.GitHubServiceError as error:
        _raise(error)


async def _owned_project(session: DatabaseSession, auth: Auth, project_id: uuid.UUID):
    try:
        return await project_service.require_project(session, auth.user.id, project_id)
    except project_service.ProjectError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error


@router.put("/projects/{project_id}/repository", response_model=ProjectRead)
async def connect_repository(
    project_id: uuid.UUID, data: RepositoryConnect, auth: VerifiedAuth, session: DatabaseSession
) -> ProjectRead:
    """Link a repository the user's GitHub account can access (checked with GitHub)."""
    project = await _owned_project(session, auth, project_id)
    try:
        project, _ = await github_service.connect_repository(
            session,
            auth.user.id,
            project,
            data.repo_full_name.strip(),
            (data.branch or "").strip() or None,
            settings,
        )
    except github_service.GitHubServiceError as error:
        _raise(error)
    return ProjectRead.model_validate(project)


@router.delete("/projects/{project_id}/repository", response_model=ProjectRead)
async def disconnect_repository(
    project_id: uuid.UUID, auth: Auth, session: DatabaseSession
) -> ProjectRead:
    project = await _owned_project(session, auth, project_id)
    return ProjectRead.model_validate(await github_service.disconnect_repository(session, project))


@router.get("/projects/{project_id}/repository/tree", response_model=RepositoryTree)
async def repository_tree(
    project_id: uuid.UUID,
    auth: Auth,
    session: DatabaseSession,
    query: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> RepositoryTree:
    """Files Fixify is allowed to read from the project's repository (for choosing fix files)."""
    project = await _owned_project(session, auth, project_id)
    try:
        connected = await github_service.open_client(session, auth.user.id, settings)
        async with connected.client as client:
            snap = await github_service.snapshot(client, project, settings)
    except github_service.GitHubServiceError as error:
        _raise(error)
    except GitHubError as error:
        await github_service.handle_auth_failure(session, auth.user.id, error)
        _raise(github_service.from_github_error(error))
    needle = (query or "").strip().lower()
    files = [e for e in snap.entries if not needle or needle in e.path.lower()][:limit]
    return RepositoryTree(
        repo_full_name=snap.full_name,
        branch=snap.branch,
        commit_sha=snap.commit_sha,
        truncated=snap.truncated,
        files=[RepositoryFile(path=e.path, size=e.size) for e in files],
    )
