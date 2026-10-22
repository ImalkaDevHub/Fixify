import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.db.models.project import Project
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


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["bad\x00name", "tab\tname", "line\nbreak"])
async def test_reject_control_characters_in_name(client, name):
    response = await client.post(
        "/api/v1/projects", json={"name": name, "website_url": "https://example.com"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reject_control_characters_in_branch(client):
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Demo", "website_url": "https://example.com", "default_branch": "ma\x00in"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("repository", ["../..", "./..", "owner/..", "./repo", "a/b/c", "owner"])
async def test_reject_path_like_repository_names(client, repository):
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Demo", "website_url": "https://example.com", "repo_full_name": repository},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_input_is_trimmed_and_blank_optionals_become_null(client):
    response = await client.post(
        "/api/v1/projects",
        json={
            "name": "  Spaced  ",
            "website_url": "https://example.com",
            "repo_full_name": " octo/hello ",
            "default_branch": "   ",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Spaced"
    assert body["repo_full_name"] == "octo/hello"
    assert body["default_branch"] is None


@pytest.mark.asyncio
async def test_reject_overlong_name_and_url(client):
    long_name = await client.post(
        "/api/v1/projects", json={"name": "n" * 101, "website_url": "https://example.com"}
    )
    long_url = await client.post(
        "/api/v1/projects",
        json={"name": "Demo", "website_url": "https://example.com/" + "a" * 2100},
    )
    assert long_name.status_code == 422
    assert long_url.status_code == 422


@pytest.mark.asyncio
async def test_invalid_project_id_is_rejected(client):
    assert (await client.get("/api/v1/projects/not-a-uuid")).status_code == 422
    assert (await client.delete("/api/v1/projects/not-a-uuid")).status_code == 422


@pytest.mark.asyncio
async def test_empty_list_is_valid(client):
    response = await client.get("/api/v1/projects")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_is_newest_first(client, session_factory):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with session_factory() as session:
        for index, name in enumerate(("First", "Second", "Third")):
            session.add(
                Project(
                    name=name,
                    website_url="https://example.com/",
                    created_at=base + timedelta(minutes=index),
                )
            )
        await session.commit()
    names = [project["name"] for project in (await client.get("/api/v1/projects")).json()]
    assert names == ["Third", "Second", "First"]


@pytest.mark.asyncio
async def test_updated_at_changes_when_a_project_is_modified(session_factory):
    old = datetime(2020, 1, 1, tzinfo=UTC)
    async with session_factory() as session:
        project = Project(
            name="Old", website_url="https://example.com/", created_at=old, updated_at=old
        )
        session.add(project)
        await session.commit()
        project.name = "Renamed"
        await session.commit()
        await session.refresh(project)
        assert project.updated_at.replace(tzinfo=UTC) > old


@pytest.mark.asyncio
async def test_list_rejects_negative_offset(client):
    assert (await client.get("/api/v1/projects?offset=-1")).status_code == 422


@pytest.mark.asyncio
async def test_read_endpoints_return_503_json_when_database_is_down(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(
        project_service,
        "list_projects",
        AsyncMock(side_effect=OperationalError("SELECT secret", {}, Exception("password=hunter2"))),
    )
    response = await client.get("/api/v1/projects")
    assert response.status_code == 503
    assert response.json() == {"detail": "The database is currently unavailable."}
    assert "hunter2" not in response.text
    assert "SELECT secret" not in response.text
