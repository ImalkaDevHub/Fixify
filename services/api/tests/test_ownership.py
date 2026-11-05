"""Users can only see and change what they own. Foreign objects look exactly like missing ones."""

import uuid

from app.cli import assign_orphans
from app.db.models import Project
from app.repositories import project as project_repository
from tests.scan_helpers import complete_run, finding, scan_result


async def _project(client, name: str = "Site") -> str:
    response = await client.post(
        "/api/v1/projects", json={"name": name, "website_url": "https://example.com"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _completed_scan(client, session_factory, artifact_dir, tmp_path) -> tuple[str, str]:
    project_id = await _project(client)
    run_id = (await client.post(f"/api/v1/projects/{project_id}/scans")).json()["id"]
    await complete_run(
        session_factory,
        uuid.UUID(run_id),
        scan_result([finding("broken", artifact_key="screenshot")]),
        tmp_path / "work",
        artifact_dir,
    )
    return project_id, run_id


async def test_projects_are_isolated(client, other_client):
    mine = await _project(client, "Mine")
    theirs = await _project(other_client, "Theirs")

    names = [project["name"] for project in (await client.get("/api/v1/projects")).json()]
    assert names == ["Mine"]
    assert (await client.get("/api/v1/projects/count")).json() == {"total": 1}
    assert (await client.get(f"/api/v1/projects/{theirs}")).status_code == 404
    assert (
        await client.patch(f"/api/v1/projects/{theirs}", json={"name": "Hijacked"})
    ).status_code == 404
    assert (await client.delete(f"/api/v1/projects/{theirs}")).status_code == 404
    assert (await other_client.get(f"/api/v1/projects/{theirs}")).json()["name"] == "Theirs"
    assert (await other_client.get(f"/api/v1/projects/{mine}")).status_code == 404


async def test_scans_findings_and_artifacts_are_isolated(
    client, other_client, session_factory, artifact_dir, tmp_path, fake_queue
):
    project_id, run_id = await _completed_scan(client, session_factory, artifact_dir, tmp_path)
    detail = (await client.get(f"/api/v1/scans/{run_id}")).json()
    artifact_url = detail["artifacts"][0]["url"]
    finding_id = (await client.get(f"/api/v1/scans/{run_id}/findings")).json()[0]["id"]

    assert (await client.get(artifact_url)).status_code == 200
    for path in (
        f"/api/v1/scans/{run_id}",
        f"/api/v1/scans/{run_id}/findings",
        f"/api/v1/scans/{run_id}/comparison",
        artifact_url,
        f"/api/v1/findings/{finding_id}",
        f"/api/v1/projects/{project_id}/scans",
        f"/api/v1/projects/{project_id}/findings",
    ):
        assert (await other_client.get(path)).status_code == 404, path

    queued_before = len(fake_queue.items)
    assert (await other_client.post(f"/api/v1/projects/{project_id}/scans")).status_code == 404
    assert len(fake_queue.items) == queued_before

    summary = (await other_client.get("/api/v1/scans/summary")).json()
    assert summary == {
        "project_count": 0, "scan_count": 0, "active_scan_count": 0, "latest_findings_count": 0
    }
    assert (await client.get("/api/v1/scans/summary")).json()["scan_count"] == 1


async def test_cancel_is_isolated(client, other_client):
    project_id = await _project(client)
    run_id = (await client.post(f"/api/v1/projects/{project_id}/scans")).json()["id"]
    assert (await other_client.post(f"/api/v1/scans/{run_id}/cancel")).status_code == 404
    assert (await client.post(f"/api/v1/scans/{run_id}/cancel")).json()["status"] == "cancelled"


async def test_project_update(client):
    project_id = await _project(client)
    response = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": " Renamed ", "repo_full_name": "octo/site", "default_branch": "main"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["repo_full_name"], body["default_branch"]) == (
        "Renamed", "octo/site", "main"
    )
    cleared = await client.patch(f"/api/v1/projects/{project_id}", json={"repo_full_name": ""})
    assert cleared.json()["repo_full_name"] is None
    for bad in ({"website_url": "ftp://x"}, {"repo_full_name": "../.."}, {"owner_id": "x"}):
        assert (await client.patch(f"/api/v1/projects/{project_id}", json=bad)).status_code == 422


async def test_per_user_project_limit(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_projects_per_user", 2)
    await _project(client, "One")
    await _project(client, "Two")
    response = await client.post(
        "/api/v1/projects", json={"name": "Three", "website_url": "https://example.com"}
    )
    assert response.status_code == 429


async def test_per_user_active_scan_limit(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_active_scans_per_user", 1)
    first = await _project(client, "One")
    second = await _project(client, "Two")
    assert (await client.post(f"/api/v1/projects/{first}/scans")).status_code == 202
    assert (await client.post(f"/api/v1/projects/{second}/scans")).status_code == 429


async def test_project_search(client):
    await _project(client, "Marketing site")
    await _project(client, "Docs")
    found = (await client.get("/api/v1/projects?search=MARKET")).json()
    assert [project["name"] for project in found] == ["Marketing site"]


async def test_orphan_projects_are_hidden_until_assigned(client, session_factory, monkeypatch):
    async with session_factory() as session:
        session.add(Project(name="Legacy", website_url="https://example.com/"))
        await session.commit()
    assert (await client.get("/api/v1/projects")).json() == []

    monkeypatch.setattr("app.cli.SessionFactory", session_factory)
    assert await assign_orphans("owner@example.com") == 0
    names = [project["name"] for project in (await client.get("/api/v1/projects")).json()]
    assert names == ["Legacy"]
    assert await assign_orphans("nobody@example.com") == 1


async def test_unscoped_lookup_is_only_for_workers(session_factory, client):
    project_id = uuid.UUID(await _project(client))
    async with session_factory() as session:
        assert await project_repository.get_project(session, project_id, uuid.uuid4()) is None
        assert await project_repository.get_project_unscoped(session, project_id) is not None
