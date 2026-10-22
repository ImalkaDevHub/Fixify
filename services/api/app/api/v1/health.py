import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


async def check_database(session: AsyncSession) -> bool:
    await session.execute(text("SELECT 1"))
    return True


async def check_redis() -> bool:
    """Redis is required for the scan queue when QUEUE_BACKEND=redis, or if REDIS_REQUIRED."""
    if not settings.redis_needed:
        return True
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        await client.ping()
        return True
    finally:
        await client.aclose()


@router.get("")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    try:
        await check_database(session)
    except SQLAlchemyError as error:
        logger.warning("Readiness check failed: PostgreSQL is unavailable: %s", error)
        raise HTTPException(status_code=503, detail="Required service unavailable.") from error

    try:
        await check_redis()
    except RedisError as error:
        logger.warning("Readiness check failed: Redis is unavailable: %s", error)
        raise HTTPException(status_code=503, detail="Required service unavailable.") from error

    return {"status": "ready"}
