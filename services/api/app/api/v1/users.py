import uuid
from typing import NoReturn

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import Auth, DatabaseSession, Limiter, enforce_limit
from app.api.v1.auth import clear_auth_cookies
from app.core.artifacts import delete_run_artifacts
from app.core.config import settings
from app.schemas.auth import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    MessageResponse,
    ProfileUpdate,
    SessionRead,
    UserRead,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/users/me", tags=["account"])


def _raise(error: auth_service.AuthError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from error


async def _limit_password_checks(limiter: Limiter, auth: Auth) -> None:
    await enforce_limit(
        limiter,
        f"account:password:{auth.user.id}",
        settings.auth_rate_limit_per_account,
        settings.auth_rate_limit_window_seconds,
        "Too many attempts. Please wait a few minutes and try again.",
    )


@router.patch("", response_model=UserRead)
async def update_profile(data: ProfileUpdate, auth: Auth, session: DatabaseSession) -> UserRead:
    user = await auth_service.update_profile(session, auth.user, data.display_name)
    return auth_service.user_read(user)


@router.post("/password", response_model=MessageResponse)
async def change_password(
    data: ChangePasswordRequest, auth: Auth, session: DatabaseSession, limiter: Limiter
) -> MessageResponse:
    """Change the password and sign out every other session."""
    await _limit_password_checks(limiter, auth)
    try:
        await auth_service.change_password(
            session,
            auth.user,
            auth.session,
            current_password=data.current_password,
            new_password=data.new_password,
            config=settings,
        )
    except auth_service.AuthError as error:
        _raise(error)
    return MessageResponse(message="Password changed. Other sessions were signed out.")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    data: DeleteAccountRequest, auth: Auth, session: DatabaseSession, limiter: Limiter
) -> Response:
    """Permanently delete the account and all projects, scans, and findings it owns."""
    await _limit_password_checks(limiter, auth)
    try:
        run_ids = await auth_service.delete_account(session, auth.user, data.password, settings)
    except auth_service.AuthError as error:
        _raise(error)
    for run_id in run_ids:
        delete_run_artifacts(settings.artifact_dir, run_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(auth: Auth, session: DatabaseSession) -> list[SessionRead]:
    return await auth_service.list_sessions(session, auth.user, auth.session)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: uuid.UUID, auth: Auth, session: DatabaseSession) -> Response:
    if not await auth_service.revoke_session(session, auth.user, session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/revoke-others", response_model=MessageResponse)
async def revoke_other_sessions(auth: Auth, session: DatabaseSession) -> MessageResponse:
    count = await auth_service.revoke_other_sessions(session, auth.user, auth.session)
    return MessageResponse(message=f"Signed out {count} other session(s).")
