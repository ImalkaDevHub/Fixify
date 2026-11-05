import os

# Must run before any application import: tests never read a developer's .env, and password
# hashing uses the cheapest Argon2 parameters so the suite stays fast.
os.environ["FIXIFY_IGNORE_ENV_FILE"] = "1"
os.environ.setdefault("PASSWORD_HASH_MEMORY_KIB", "1024")
os.environ.setdefault("PASSWORD_HASH_TIME_COST", "1")
os.environ.setdefault("EMAIL_BACKEND", "disabled")

import uuid  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.api.v1.scans import get_queue, get_url_policy  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.email import EmailMessage, get_email_sender  # noqa: E402
from app.core.rate_limit import MemoryRateLimiter, get_rate_limiter  # noqa: E402
from app.db import models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.scanner.contract import PolicyConfig  # noqa: E402
from app.scanner.url_policy import UrlPolicy  # noqa: E402
from app.services import auth as auth_service  # noqa: E402
from app.worker.queue import QueueUnavailableError  # noqa: E402

PASSWORD = "correct horse battery"

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


class Outbox:
    """Captures outgoing email instead of sending it."""

    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.messages.append(message)

    def token(self, subject_part: str) -> str:
        for message in reversed(self.messages):
            if subject_part.lower() in message.subject.lower():
                return message.text.split("#token=", 1)[1].split()[0]
        raise AssertionError(f"No email with {subject_part!r} in the subject")


@pytest.fixture
def outbox() -> Outbox:
    return Outbox()


@pytest.fixture
def rate_limiter() -> MemoryRateLimiter:
    return MemoryRateLimiter()


@pytest.fixture
def app_overrides(session_factory, fake_queue, artifact_dir, outbox, rate_limiter):
    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_queue():
        yield fake_queue

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_queue] = override_queue
    app.dependency_overrides[get_url_policy] = lambda: fake_policy()
    app.dependency_overrides[get_email_sender] = lambda: outbox
    app.dependency_overrides[get_rate_limiter] = lambda: rate_limiter
    yield
    app.dependency_overrides.clear()


async def create_user(
    session_factory, email: str, *, verified: bool = True, password: str = PASSWORD
) -> User:
    async with session_factory() as session:
        user = await auth_service.register(
            session,
            email=email,
            password=password,
            display_name=email.split("@")[0],
            config=settings,
        )
        if verified:
            user.email_verified_at = datetime.now(UTC)
            await session.commit()
        return user


async def sign_in(test_client: AsyncClient, email: str, password: str = PASSWORD) -> None:
    response = await test_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    test_client.headers["X-CSRF-Token"] = test_client.cookies["fixify_csrf"]


def new_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def anon_client(app_overrides):
    async with new_client() as test_client:
        yield test_client


async def _signed_in(session_factory, email: str, verified: bool = True):
    user = await create_user(session_factory, email, verified=verified)
    test_client = new_client()
    await sign_in(test_client, email)
    test_client.user_id = user.id  # type: ignore[attr-defined]
    return test_client


@pytest.fixture
async def client(app_overrides, session_factory):
    """Signed in as a verified user; sends the CSRF header automatically."""
    test_client = await _signed_in(session_factory, "owner@example.com")
    try:
        yield test_client
    finally:
        await test_client.aclose()


@pytest.fixture
async def other_client(app_overrides, session_factory):
    """A second, unrelated verified user (for ownership-isolation tests)."""
    test_client = await _signed_in(session_factory, "intruder@example.com")
    try:
        yield test_client
    finally:
        await test_client.aclose()


@pytest.fixture
async def unverified_client(app_overrides, session_factory):
    test_client = await _signed_in(session_factory, "new@example.com", verified=False)
    try:
        yield test_client
    finally:
        await test_client.aclose()
