"""Fixed-window rate limiting.

Redis is used when it is part of the deployment, so limits are shared by every API process.
Without Redis (QUEUE_BACKEND=database) the limiter is in-memory, which only limits a single
API process; this is documented in docs/security.md. If Redis fails mid-request, the
in-memory limiter takes over instead of failing open.
"""

import asyncio
import logging
import time
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        """Count one event. Returns seconds to wait if the limit is exceeded, else None."""
        ...


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        now = time.monotonic()
        async with self._lock:
            if len(self._windows) > 50_000:  # bounded memory under abuse
                self._windows = {
                    k: v for k, v in self._windows.items() if now - v[0] < window_seconds
                }
            started, count = self._windows.get(key, (now, 0))
            if now - started >= window_seconds:
                started, count = now, 0
            count += 1
            self._windows[key] = (started, count)
        if count > limit:
            return max(1, int(window_seconds - (now - started)))
        return None


class RedisRateLimiter:
    def __init__(self, url: str, fallback: MemoryRateLimiter) -> None:
        self._redis = Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        self._fallback = fallback

    async def hit(self, key: str, limit: int, window_seconds: int) -> int | None:
        name = f"fixify:rl:{key}"
        try:
            count = await self._redis.incr(name)
            if count == 1:
                await self._redis.expire(name, window_seconds)
            if count > limit:
                ttl = await self._redis.ttl(name)
                return max(1, ttl if ttl and ttl > 0 else window_seconds)
            return None
        except (RedisError, OSError):
            logger.warning("Rate limiter: Redis unavailable, using in-memory limits")
            return await self._fallback.hit(key, limit, window_seconds)


_limiter: RateLimiter | None = None


def create_rate_limiter(config: Settings = settings) -> RateLimiter:
    memory = MemoryRateLimiter()
    if config.redis_needed:
        return RedisRateLimiter(config.redis_url, memory)
    return memory


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = create_rate_limiter()
    return _limiter
