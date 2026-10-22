import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services import project as project_service


@pytest.mark.asyncio
async def test_create_project(client):
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Demo Website", "website_url": "https://example.com"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Demo Website"
    assert body["website_url"] == "https://example.com/"
    assert uuid.UUID(body["id"])
    assert body["repo_full_name"] is None
    assert body["created_at"]
    assert body["updated_at"]


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["ftp://example.com", "not-a-url", "javascript:alert(1)"])
async def test_reject_invalid_website_url(client, url):
    response = await client.post(
        "/api/v1/projects", json={"name": "Invalid URL", "website_url": url}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", "   "])
async def test_reject_empty_project_name(client, name):
    response = await client.post(
        "/api/v1/projects", json={"name": name, "website_url": "https://example.com"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reject_invalid_repository_name(client):
    response = await client.post(
        "/api/v1/projects",
        json={
            "name": "Demo",
            "website_url": "https://example.com",
            "repo_full_name": "not-a-valid-path",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_projects_with_pagination(client):
    for name in ("One", "Two", "Three"):
        created = await client.post(
            "/api/v1/projects",
            json={"name": name, "website_url": "https://example.com"},
        )
        assert created.status_code == 201

    response = await client.get("/api/v1/projects?limit=2&offset=1")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_project_count(client):
    for name in ("One", "Two"):
        await client.post(
            "/api/v1/projects",
            json={"name": name, "website_url": "https://example.com"},
        )
    response = await client.get("/api/v1/projects/count")
    assert response.status_code == 200
    assert response.json() == {"total": 2}


@pytest.mark.asyncio
async def test_project_detail_and_not_found(client):
    created = await client.post(
        "/api/v1/projects",
        json={"name": "Detail", "website_url": "https://example.com"},
    )
    project_id = created.json()["id"]
    found = await client.get(f"/api/v1/projects/{project_id}")
    missing = await client.get(f"/api/v1/projects/{uuid.uuid4()}")
    assert found.status_code == 200
    assert found.json()["id"] == project_id
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_delete_project_and_not_found(client):
    created = await client.post(
        "/api/v1/projects",
        json={"name": "Delete", "website_url": "https://example.com"},
    )
    project_id = created.json()["id"]
    deleted = await client.delete(f"/api/v1/projects/{project_id}")
    missing = await client.delete(f"/api/v1/projects/{project_id}")
    assert deleted.status_code == 204
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_list_projects_rejects_unsafe_limit(client):
    response = await client.get("/api/v1/projects?limit=101")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_project_returns_generic_error_on_database_failure(client, monkeypatch):
    monkeypatch.setattr(
        project_service,
        "create_project",
        AsyncMock(side_effect=SQLAlchemyError("database details must not reach clients")),
    )
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Demo", "website_url": "https://example.com"},
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to create project."}
    assert "database details" not in response.text
