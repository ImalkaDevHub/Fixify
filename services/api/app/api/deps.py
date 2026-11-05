"""Shared request dependencies: database session, authentication, CSRF, and rate limits."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.db.models.user import User, UserSession
from app.db.session import get_session
from app.services import auth as auth_service

ACCESS_COOKIE = "fixify_access"
REFRESH_COOKIE = "fixify_refresh"
CSRF_COOKIE = "fixify_csrf"
# Not a credential: lets the Next.js proxy redirect signed-out visitors before rendering.
SESSION_HINT_COOKIE = "fixify_session"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession


def client_ip(request: Request) -> str:
    # Uvicorn applies X-Forwarded-For only from trusted proxies (--forwarded-allow-ips), so
    # request.client is already the real client when running behind the Next.js proxy.
    return request.client.host if request.client else "unknown"


def check_origin(request: Request) -> None:
    """Reject cross-site state-changing requests. Non-browser clients send no Origin header."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is not None and origin.rstrip("/") not in settings.trusted_origins:
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")


async def current_auth(request: Request, session: DatabaseSession) -> AuthContext:
    resolved = await auth_service.resolve_access_token(
        session, request.cookies.get(ACCESS_COOKIE), settings
    )
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in or the session has expired.",
        )
    user, user_session = resolved
    if request.method not in SAFE_METHODS:
        check_origin(request)
        if not security.csrf_matches(user_session.id, request.headers.get(CSRF_HEADER)):
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token.")
    return AuthContext(user=user, session=user_session)


Auth = Annotated[AuthContext, Depends(current_auth)]


async def verified_auth(auth: Auth) -> AuthContext:
    if settings.require_email_verification and auth.user.email_verified_at is None:
        raise HTTPException(
            status_code=403,
            detail="Verify your email address first. Check your inbox or resend the link.",
        )
    return auth


VerifiedAuth = Annotated[AuthContext, Depends(verified_auth)]


async def enforce_limit(
    limiter: RateLimiter, key: str, limit: int, window_seconds: int, message: str
) -> None:
    retry_after = await limiter.hit(key, limit, window_seconds)
    if retry_after is not None:
        raise HTTPException(
            status_code=429, detail=message, headers={"Retry-After": str(retry_after)}
        )
