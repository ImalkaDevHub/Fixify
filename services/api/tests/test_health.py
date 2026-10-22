from unittest.mock import AsyncMock

import pytest

from app.api.v1 import health


@pytest.mark.asyncio
async def test_health_is_ok(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_is_ready_when_dependencies_are_available(client, monkeypatch):
    monkeypatch.setattr(health, "check_redis", AsyncMock(return_value=True))
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_readiness_returns_503_when_redis_is_unavailable(client, monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError

    monkeypatch.setattr(
        health,
        "check_redis",
        AsyncMock(side_effect=RedisConnectionError("private connection detail")),
    )
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "private connection detail" not in response.text


@pytest.mark.asyncio
async def test_readiness_returns_503_when_database_is_unavailable(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(
        health,
        "check_database",
        AsyncMock(side_effect=OperationalError("SELECT 1", {}, Exception("unavailable"))),
    )
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "SELECT 1" not in response.text
    assert "builtins.Exception" not in response.text
