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
    if not settings.redis_required:
        return True
    client = Redis.from_url(settings.redis_url)
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
