from typing import NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    SESSION_HINT_COOKIE,
    Auth,
    DatabaseSession,
    Limiter,
    check_origin,
    client_ip,
    enforce_limit,
)
from app.core.config import settings
from app.core.email import EmailSender, get_email_sender
from app.schemas.auth import (
    EmailRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenRequest,
    UserRead,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(check_origin)])

_TOO_MANY = "Too many attempts. Please wait a few minutes and try again."


def _raise(error: auth_service.AuthError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.message) from error


def set_auth_cookies(response: Response, issued: auth_service.IssuedSession) -> None:
    secure = settings.secure_cookies
    refresh_age = max(0, int((issued.refresh_expires_at - auth_service.utcnow()).total_seconds()))
    response.set_cookie(
        ACCESS_COOKIE,
        issued.access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        path="/api",
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        issued.refresh_token,
        max_age=refresh_age,
        path="/api/v1/auth",
        httponly=True,
        secure=secure,
        samesite="strict",
    )
    response.set_cookie(
        CSRF_COOKIE,
        issued.csrf_token,
        max_age=refresh_age,
        path="/",
        httponly=False,  # read by the web app and echoed in the X-CSRF-Token header
        secure=secure,
        samesite="lax",
    )
    response.set_cookie(
        SESSION_HINT_COOKIE, "1", max_age=refresh_age, path="/", httponly=True,
        secure=secure, samesite="lax",
    )


def clear_auth_cookies(response: Response) -> None:
    for name, path in (
        (ACCESS_COOKIE, "/api"),
        (REFRESH_COOKIE, "/api/v1/auth"),
        (CSRF_COOKIE, "/"),
        (SESSION_HINT_COOKIE, "/"),
    ):
        response.delete_cookie(name, path=path, secure=settings.secure_cookies, httponly=True)


async def _limit_ip(limiter: Limiter, request: Request, action: str, factor: int = 1) -> None:
    await enforce_limit(
        limiter,
        f"auth:{action}:ip:{client_ip(request)}",
        settings.auth_rate_limit_per_ip * factor,
        settings.auth_rate_limit_window_seconds,
        _TOO_MANY,
    )


async def _limit_account(limiter: Limiter, action: str, email: str) -> None:
    await enforce_limit(
        limiter,
        f"auth:{action}:account:{auth_service.normalize_email(email)}",
        settings.auth_rate_limit_per_account,
        settings.auth_rate_limit_window_seconds,
        _TOO_MANY,
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
    limiter: Limiter,
    background: BackgroundTasks,
    mailer: EmailSender = Depends(get_email_sender),  # noqa: B008
) -> UserRead:
    """Create an account, sign in, and email a verification link."""
    await _limit_ip(limiter, request, "register")
    try:
        user = await auth_service.register(
            session,
            email=data.email,
            password=data.password,
            display_name=data.display_name,
            config=settings,
        )
    except auth_service.AuthError as error:
        _raise(error)
    issued = await auth_service.start_session(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
        config=settings,
    )
    message = await auth_service.verification_email(session, user, settings)
    background.add_task(mailer.send, message)
    set_auth_cookies(response, issued)
    return auth_service.user_read(user)


@router.post("/login", response_model=UserRead)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
    limiter: Limiter,
) -> UserRead:
    await _limit_ip(limiter, request, "login")
    await _limit_account(limiter, "login", data.email)
    try:
        user = await auth_service.authenticate(
            session, email=data.email, password=data.password, config=settings
        )
    except auth_service.AuthError as error:
        _raise(error)
    issued = await auth_service.start_session(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
        config=settings,
    )
    set_auth_cookies(response, issued)
    return auth_service.user_read(user)


@router.post("/refresh", response_model=UserRead)
async def refresh(
    request: Request, response: Response, session: DatabaseSession, limiter: Limiter
) -> UserRead | JSONResponse:
    """Rotate the refresh token and issue a new access token."""
    await _limit_ip(limiter, request, "refresh", factor=10)
    try:
        issued = await auth_service.refresh_session(
            session, request.cookies.get(REFRESH_COOKIE), settings
        )
    except auth_service.AuthError as error:
        failed = JSONResponse({"detail": error.message}, status_code=error.status_code)
        clear_auth_cookies(failed)  # stale cookies must not keep the UI looking signed in
        return failed
    resolved = await auth_service.resolve_access_token(session, issued.access_token, settings)
    assert resolved is not None
    set_auth_cookies(response, issued)
    return auth_service.user_read(resolved[0])


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, session: DatabaseSession) -> Response:
    await auth_service.end_session_by_refresh(session, request.cookies.get(REFRESH_COOKIE))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=UserRead)
async def me(auth: Auth) -> UserRead:
    return auth_service.user_read(auth.user)


@router.post("/verify-email", response_model=UserRead)
async def verify_email(
    data: TokenRequest, request: Request, session: DatabaseSession, limiter: Limiter
) -> UserRead:
    await _limit_ip(limiter, request, "verify")
    try:
        user = await auth_service.verify_email(session, data.token)
    except auth_service.AuthError as error:
        _raise(error)
    return auth_service.user_read(user)


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    auth: Auth,
    session: DatabaseSession,
    limiter: Limiter,
    background: BackgroundTasks,
    mailer: EmailSender = Depends(get_email_sender),  # noqa: B008
) -> MessageResponse:
    if auth.user.email_verified_at is not None:
        return MessageResponse(message="Your email address is already verified.")
    await enforce_limit(
        limiter, f"auth:resend:{auth.user.id}", 5, 3_600, "Too many emails. Try again later."
    )
    message = await auth_service.verification_email(session, auth.user, settings)
    background.add_task(mailer.send, message)
    return MessageResponse(message="A new verification link is on its way.")


@router.post("/forgot-password", response_model=MessageResponse, status_code=202)
async def forgot_password(
    data: EmailRequest,
    request: Request,
    session: DatabaseSession,
    limiter: Limiter,
    background: BackgroundTasks,
    mailer: EmailSender = Depends(get_email_sender),  # noqa: B008
) -> MessageResponse:
    """Always answers the same way, whether or not the account exists."""
    await _limit_ip(limiter, request, "forgot")
    await _limit_account(limiter, "forgot", data.email)
    message = await auth_service.password_reset_email(session, data.email, settings)
    if message is not None:
        background.add_task(mailer.send, message)
    return MessageResponse(
        message="If an account exists for that address, a reset link is on its way."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest, request: Request, session: DatabaseSession, limiter: Limiter
) -> MessageResponse:
    await _limit_ip(limiter, request, "reset")
    try:
        await auth_service.reset_password(session, data.token, data.password, settings)
    except auth_service.AuthError as error:
        _raise(error)
    return MessageResponse(message="Your password was changed. Sign in with the new password.")
