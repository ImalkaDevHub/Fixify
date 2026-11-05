import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User, UserSession, UserToken


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email))


async def add_user(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.flush()
    return user


async def get_session(session: AsyncSession, session_id: uuid.UUID) -> UserSession | None:
    return await session.get(UserSession, session_id)


async def get_session_by_refresh_hash(session: AsyncSession, token_hash: str) -> UserSession | None:
    return await session.scalar(
        select(UserSession).where(UserSession.refresh_token_hash == token_hash).with_for_update()
    )


async def get_session_by_previous_hash(
    session: AsyncSession, token_hash: str
) -> UserSession | None:
    return await session.scalar(
        select(UserSession).where(UserSession.previous_token_hash == token_hash)
    )


async def list_active_sessions(
    session: AsyncSession, user_id: uuid.UUID, now: datetime
) -> list[UserSession]:
    result = await session.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.last_used_at.desc())
    )
    return list(result)


async def revoke_sessions(
    session: AsyncSession,
    user_id: uuid.UUID,
    now: datetime,
    reason: str,
    *,
    except_session_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> int:
    conditions = [UserSession.user_id == user_id, UserSession.revoked_at.is_(None)]
    if except_session_id is not None:
        conditions.append(UserSession.id != except_session_id)
    if session_id is not None:
        conditions.append(UserSession.id == session_id)
    result = await session.execute(
        update(UserSession).where(*conditions).values(revoked_at=now, revoke_reason=reason)
    )
    return result.rowcount or 0


async def get_token(session: AsyncSession, token_hash: str, purpose: str) -> UserToken | None:
    return await session.scalar(
        select(UserToken)
        .where(UserToken.token_hash == token_hash, UserToken.purpose == purpose)
        .with_for_update()
    )


async def invalidate_tokens(
    session: AsyncSession, user_id: uuid.UUID, purpose: str, now: datetime
) -> None:
    await session.execute(
        update(UserToken)
        .where(
            UserToken.user_id == user_id,
            UserToken.purpose == purpose,
            UserToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
