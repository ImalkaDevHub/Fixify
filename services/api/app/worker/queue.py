"""Scan job queue.

PostgreSQL is the source of truth: a run is a job while its status is "queued", and a worker
owns it only after an atomic queued -> running update succeeds. The queue only delivers run IDs
promptly. Lost or duplicated messages are therefore harmless: duplicates fail to claim the run,
and the worker's periodic database sweep picks up anything a message never announced.
"""

import uuid
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings


class QueueUnavailableError(RuntimeError):
    pass


class ScanQueue(Protocol):
    async def enqueue(self, run_id: uuid.UUID) -> None: ...

    async def dequeue(self, timeout_seconds: int) -> uuid.UUID | None: ...

    async def ping(self) -> None: ...

    async def close(self) -> None: ...


class RedisScanQueue:
    def __init__(self, url: str, name: str) -> None:
        self._redis = Redis.from_url(url, socket_connect_timeout=2, socket_timeout=None)
        self._name = name

    async def enqueue(self, run_id: uuid.UUID) -> None:
        try:
            await self._redis.rpush(self._name, str(run_id))
        except (RedisError, OSError) as error:
            raise QueueUnavailableError("The scan queue is unavailable.") from error

    async def dequeue(self, timeout_seconds: int) -> uuid.UUID | None:
        item = await self._redis.blpop([self._name], timeout=timeout_seconds)
        if item is None:
            return None
        try:
            return uuid.UUID(item[1].decode())
        except ValueError:
            return None  # ignore malformed messages; they cannot name a run

    async def ping(self) -> None:
        await self._redis.ping()

    async def close(self) -> None:
        await self._redis.aclose()


class DatabaseScanQueue:
    """No broker: the worker discovers queued runs by polling PostgreSQL."""

    async def enqueue(self, run_id: uuid.UUID) -> None:
        return None

    async def dequeue(self, timeout_seconds: int) -> uuid.UUID | None:
        return None

    async def ping(self) -> None:
        return None

    async def close(self) -> None:
        return None


def create_queue(settings: Settings) -> ScanQueue:
    if settings.queue_backend == "redis":
        return RedisScanQueue(settings.redis_url, settings.scan_queue_name)
    return DatabaseScanQueue()
