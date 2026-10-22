import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.scans import get_queue, get_url_policy
from app.core.config import settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.scanner.contract import PolicyConfig
from app.scanner.url_policy import UrlPolicy
from app.worker.queue import QueueUnavailableError

# Fake DNS used by every test: no test depends on real DNS or internet access.
FAKE_DNS = {
    "example.com": ["93.184.215.14"],
    "www.example.com": ["93.184.215.14"],
    "public.example.org": ["93.184.215.20"],
    "internal.example.org": ["10.0.0.5"],
    "mixed.example.org": ["93.184.215.21", "192.168.1.10"],
    "rebind.example.org": ["127.0.0.1"],
    "metadata.example.org": ["169.254.169.254"],
    "v6private.example.org": ["fd12::1"],
    "mapped.example.org": ["::ffff:10.0.0.1"],
}


async def fake_resolver(host: str, _port: int) -> list[str]:
    if host in FAKE_DNS:
        return FAKE_DNS[host]
    raise OSError("Name or service not known")


def fake_policy(**config: object) -> UrlPolicy:
    return UrlPolicy(PolicyConfig(**config), resolver=fake_resolver)  # type: ignore[arg-type]


class FakeQueue:
    def __init__(self) -> None:
        self.items: list[uuid.UUID] = []
        self.fail = False

    async def enqueue(self, run_id: uuid.UUID) -> None:
        if self.fail:
            raise QueueUnavailableError("The scan queue is unavailable.")
        self.items.append(run_id)

    async def dequeue(self, timeout_seconds: int) -> uuid.UUID | None:
        return self.items.pop(0) if self.items else None

    async def ping(self) -> None:
        if self.fail:
            raise ConnectionError("down")

    async def close(self) -> None:
        return None


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(connection, _record):  # noqa: ANN001
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def fake_queue() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
def artifact_dir(tmp_path, monkeypatch):
    directory = tmp_path / "artifacts"
    monkeypatch.setattr(settings, "artifact_dir", directory)
    return directory


@pytest.fixture
async def client(session_factory, fake_queue, artifact_dir):
    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_queue():
        yield fake_queue

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_queue] = override_queue
    app.dependency_overrides[get_url_policy] = lambda: fake_policy()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()
