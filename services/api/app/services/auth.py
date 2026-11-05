"""Authentication and account business logic. Routers only translate HTTP <-> these calls."""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import Settings
from app.core.email import EmailMessage
from app.db.models.user import User, UserSession, UserToken
from app.repositories import project as project_repository
from app.repositories import user as user_repository
from app.schemas.auth import SessionRead, UserRead

logger = logging.getLogger(__name__)

EMAIL_VERIFICATION = "email_verification"
PASSWORD_RESET = "password_reset"


class AuthError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidCredentialsError(AuthError):
    status_code = 401


class NotAuthenticatedError(AuthError):
    status_code = 401


class EmailTakenError(AuthError):
    status_code = 409


class InvalidTokenError(AuthError):
    status_code = 400


@dataclass(frozen=True)
class IssuedSession:
    session_id: uuid.UUID
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    csrf_token: str


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes; everything stored is UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


async def _hash(password: str, config: Settings) -> str:
    return await asyncio.to_thread(security.hash_password, password, config)


async def _verify(password_hash: str, password: str, config: Settings) -> bool:
    return await asyncio.to_thread(security.verify_password, password_hash, password, config)


def _check_password_differs_from_email(password: str, email: str) -> None:
    local = email.split("@", 1)[0]
    if password.lower() in {email.lower(), local.lower()}:
        raise AuthError("The password cannot be your email address.")


# --- Registration and login ----------------------------------------------------------------


async def register(
    session: AsyncSession, *, email: str, password: str, display_name: str, config: Settings
) -> User:
    email = normalize_email(email)
    _check_password_differs_from_email(password, email)
    if await user_repository.get_user_by_email(session, email) is not None:
        raise EmailTakenError("An account with this email address already exists.")
    user = User(
        email=email,
        display_name=display_name,
        password_hash=await _hash(password, config),
        is_active=True,
        password_changed_at=utcnow(),
    )
    try:
        await user_repository.add_user(session, user)
        await session.commit()
    except IntegrityError as error:  # concurrent registration with the same email
        await session.rollback()
        raise EmailTakenError("An account with this email address already exists.") from error
    await session.refresh(user)
    return user


async def authenticate(
    session: AsyncSession, *, email: str, password: str, config: Settings
) -> User:
    user = await user_repository.get_user_by_email(session, normalize_email(email))
    if user is None:
        await asyncio.to_thread(security.burn_password_check, password, config)
        raise InvalidCredentialsError("Incorrect email address or password.")
    if not await _verify(user.password_hash, password, config) or not user.is_active:
        raise InvalidCredentialsError("Incorrect email address or password.")
    if security.password_needs_rehash(user.password_hash, config):
        user.password_hash = await _hash(password, config)
    return user


async def start_session(
    session: AsyncSession,
    user: User,
    *,
    user_agent: str | None,
    ip_address: str | None,
    config: Settings,
) -> IssuedSession:
    now = utcnow()
    refresh = security.new_opaque_token()
    record = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash=security.hash_token(refresh),
        user_agent=(user_agent or "")[:255] or None,
        ip_address=(ip_address or "")[:64] or None,
        last_used_at=now,
        expires_at=now + timedelta(days=config.refresh_token_ttl_days),
    )
    session.add(record)
    user.last_login_at = now
    await session.commit()
    return _issue(record, refresh, config)


def _issue(record: UserSession, refresh: str, config: Settings) -> IssuedSession:
    access, access_expires = security.create_access_token(record.user_id, record.id, config)
    return IssuedSession(
        session_id=record.id,
        access_token=access,
        access_expires_at=access_expires,
        refresh_token=refresh,
        refresh_expires_at=aware(record.expires_at),
        csrf_token=security.csrf_token_for(record.id, config),
    )


async def refresh_session(
    session: AsyncSession, refresh_token: str | None, config: Settings
) -> IssuedSession:
    """Rotate the refresh token. Presenting an already-rotated token revokes the session."""
    if not refresh_token or len(refresh_token) > 200:
        raise NotAuthenticatedError("Please sign in again.")
    now = utcnow()
    token_hash = security.hash_token(refresh_token)
    record = await user_repository.get_session_by_refresh_hash(session, token_hash)
    if record is None:
        reused = await user_repository.get_session_by_previous_hash(session, token_hash)
        if reused is not None and reused.revoked_at is None:
            logger.warning("Refresh token reuse detected; revoking session %s", reused.id)
            await user_repository.revoke_sessions(
                session, reused.user_id, now, "refresh_token_reuse", session_id=reused.id
            )
            await session.commit()
        raise NotAuthenticatedError("Please sign in again.")
    if record.revoked_at is not None or aware(record.expires_at) <= now:
        raise NotAuthenticatedError("Please sign in again.")
    user = await user_repository.get_user(session, record.user_id)
    if user is None or not user.is_active:
        raise NotAuthenticatedError("Please sign in again.")

    new_refresh = security.new_opaque_token()
    record.previous_token_hash = token_hash
    record.refresh_token_hash = security.hash_token(new_refresh)
    record.last_used_at = now
    await session.commit()
    return _issue(record, new_refresh, config)


async def resolve_access_token(
    session: AsyncSession, token: str | None, config: Settings
) -> tuple[User, UserSession] | None:
    if not token or len(token) > 2_000:
        return None
    claims = security.decode_access_token(token, config)
    if claims is None:
        return None
    record = await user_repository.get_session(session, claims.session_id)
    if (
        record is None
        or record.user_id != claims.user_id
        or record.revoked_at is not None
        or aware(record.expires_at) <= utcnow()
    ):
        return None
    user = await user_repository.get_user(session, claims.user_id)
    if user is None or not user.is_active:
        return None
    return user, record


async def end_session(session: AsyncSession, record: UserSession) -> None:
    await user_repository.revoke_sessions(
        session, record.user_id, utcnow(), "logout", session_id=record.id
    )
    await session.commit()


async def end_session_by_refresh(session: AsyncSession, refresh_token: str | None) -> None:
    if not refresh_token or len(refresh_token) > 200:
        return
    record = await user_repository.get_session_by_refresh_hash(
        session, security.hash_token(refresh_token)
    )
    if record is not None:
        await end_session(session, record)


# --- Sessions ------------------------------------------------------------------------------


async def list_sessions(
    session: AsyncSession, user: User, current: UserSession
) -> list[SessionRead]:
    records = await user_repository.list_active_sessions(session, user.id, utcnow())
    return [
        SessionRead(
            id=record.id,
            user_agent=record.user_agent,
            ip_address=record.ip_address,
            created_at=record.created_at,
            last_used_at=record.last_used_at,
            expires_at=record.expires_at,
            current=record.id == current.id,
        )
        for record in records
    ]


async def revoke_session(session: AsyncSession, user: User, session_id: uuid.UUID) -> bool:
    revoked = await user_repository.revoke_sessions(
        session, user.id, utcnow(), "revoked_by_user", session_id=session_id
    )
    await session.commit()
    return revoked == 1


async def revoke_other_sessions(session: AsyncSession, user: User, current: UserSession) -> int:
    revoked = await user_repository.revoke_sessions(
        session, user.id, utcnow(), "revoked_by_user", except_session_id=current.id
    )
    await session.commit()
    return revoked


# --- Single-use email tokens ---------------------------------------------------------------


async def _create_token(
    session: AsyncSession, user: User, purpose: str, ttl: timedelta
) -> str:
    now = utcnow()
    await user_repository.invalidate_tokens(session, user.id, purpose, now)
    raw = security.new_opaque_token()
    session.add(
        UserToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=security.hash_token(raw),
            expires_at=now + ttl,
        )
    )
    await session.commit()
    return raw


async def _consume_token(session: AsyncSession, raw: str, purpose: str) -> User:
    now = utcnow()
    token = await user_repository.get_token(session, security.hash_token(raw), purpose)
    if token is None or token.used_at is not None or aware(token.expires_at) <= now:
        raise InvalidTokenError("This link is invalid or has expired. Request a new one.")
    user = await user_repository.get_user(session, token.user_id)
    if user is None or not user.is_active:
        raise InvalidTokenError("This link is invalid or has expired. Request a new one.")
    token.used_at = now
    return user


def _link(config: Settings, path: str, token: str) -> str:
    # The token is in the fragment, so it is never sent to a server or written to access logs.
    return f"{config.public_app_url.rstrip('/')}{path}#token={token}"


async def verification_email(session: AsyncSession, user: User, config: Settings) -> EmailMessage:
    token = await _create_token(
        session, user, EMAIL_VERIFICATION, timedelta(hours=config.email_verification_ttl_hours)
    )
    return EmailMessage(
        to=user.email,
        subject="Verify your Fixify email address",
        text=(
            f"Hi {user.display_name},\n\n"
            "Confirm your email address to start scanning websites with Fixify:\n\n"
            f"{_link(config, '/verify-email', token)}\n\n"
            f"The link expires in {config.email_verification_ttl_hours} hours. If you did not "
            "create a Fixify account, you can ignore this email."
        ),
    )


async def verify_email(session: AsyncSession, raw_token: str) -> User:
    user = await _consume_token(session, raw_token, EMAIL_VERIFICATION)
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    await session.commit()
    return user


async def password_reset_email(
    session: AsyncSession, email: str, config: Settings
) -> EmailMessage | None:
    """Returns None for unknown accounts; the caller responds identically either way."""
    user = await user_repository.get_user_by_email(session, normalize_email(email))
    if user is None or not user.is_active:
        return None
    token = await _create_token(
        session, user, PASSWORD_RESET, timedelta(minutes=config.password_reset_ttl_minutes)
    )
    return EmailMessage(
        to=user.email,
        subject="Reset your Fixify password",
        text=(
            f"Hi {user.display_name},\n\n"
            "Someone asked to reset the password for your Fixify account. To choose a new "
            "password, open:\n\n"
            f"{_link(config, '/reset-password', token)}\n\n"
            f"The link expires in {config.password_reset_ttl_minutes} minutes and works once. "
            "If you did not ask for this, ignore this email; your password is unchanged."
        ),
    )


async def reset_password(
    session: AsyncSession, raw_token: str, new_password: str, config: Settings
) -> None:
    user = await _consume_token(session, raw_token, PASSWORD_RESET)
    _check_password_differs_from_email(new_password, user.email)
    now = utcnow()
    user.password_hash = await _hash(new_password, config)
    user.password_changed_at = now
    # Whoever had the old password must not stay signed in.
    await user_repository.revoke_sessions(session, user.id, now, "password_reset")
    await user_repository.invalidate_tokens(session, user.id, PASSWORD_RESET, now)
    if user.email_verified_at is None:
        user.email_verified_at = now  # the reset link proved ownership of the mailbox
    await session.commit()


# --- Account management --------------------------------------------------------------------


async def update_profile(session: AsyncSession, user: User, display_name: str) -> User:
    user.display_name = display_name
    await session.commit()
    await session.refresh(user)
    return user


async def change_password(
    session: AsyncSession,
    user: User,
    current: UserSession,
    *,
    current_password: str,
    new_password: str,
    config: Settings,
) -> None:
    if not await _verify(user.password_hash, current_password, config):
        raise InvalidCredentialsError("The current password is incorrect.")
    _check_password_differs_from_email(new_password, user.email)
    now = utcnow()
    user.password_hash = await _hash(new_password, config)
    user.password_changed_at = now
    await user_repository.revoke_sessions(
        session, user.id, now, "password_changed", except_session_id=current.id
    )
    await session.commit()


async def delete_account(
    session: AsyncSession, user: User, password: str, config: Settings
) -> list[uuid.UUID]:
    """Delete the user and, by cascade, everything they own. Returns run IDs to clean up."""
    if not await _verify(user.password_hash, password, config):
        raise InvalidCredentialsError("The password is incorrect.")
    run_ids = await project_repository.run_ids_for_owner(session, user.id)
    await session.delete(user)
    await session.commit()
    return run_ids
