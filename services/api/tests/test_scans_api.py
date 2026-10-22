import uuid
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.v1 import health
from app.core.config import settings
from tests.scan_helpers import PNG, complete_run, finding, scan_result


async def _project(client, url: str = "https://example.com") -> str:
    response = await client.post("/api/v1/projects", json={"name": "Site", "website_url": url})
    assert response.status_code == 201
    return response.json()["id"]


async def _scan(client, project_id: str, **body):
    return await client.post(f"/api/v1/projects/{project_id}/scans", json=body or None)


async def test_start_scan_returns_202_queued_and_enqueues(client, fake_queue):
    project_id = await _project(client)
    response = await _scan(client, project_id)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["target_url"] == "https://example.com/"
    assert fake_queue.items == [uuid.UUID(body["id"])]

    detail = await client.get(f"/api/v1/scans/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "queued"
    assert detail.json()["checks"] == []


async def test_start_scan_for_missing_project(client):
    response = await _scan(client, str(uuid.uuid4()))
    assert response.status_code == 404


@pytest.mark.parametrize(
    "url", ["http://internal.example.org", "http://127.0.0.1:8000", "http://localhost:3000"]
)
async def test_project_url_blocked_by_policy(client, fake_queue, url):
    project_id = await _project(client, url)
    response = await _scan(client, project_id)
    assert response.status_code == 422
    assert "cannot be scanned" in response.json()["detail"]
    assert fake_queue.items == []
    assert (await client.get(f"/api/v1/projects/{project_id}/scans")).json() == []


@pytest.mark.parametrize(
    "body",
    [
        {"target_url": "http://169.254.169.254/"},
        {"target_url": "ftp://example.com/"},
        {"max_links": 1000},
        {"max_links": -1},
        {"unknown_option": True},
    ],
)
async def test_invalid_scan_options(client, body):
    project_id = await _project(client)
    assert (await _scan(client, project_id, **body)).status_code == 422


async def test_max_links_is_capped_by_server_setting(client):
    project_id = await _project(client)
    response = await _scan(client, project_id, max_links=200)
    detail = await client.get(f"/api/v1/scans/{response.json()['id']}")
    assert detail.json()["max_links"] == settings.scanner_max_links


async def test_queue_failure_does_not_leave_a_queued_run(client, fake_queue):
    project_id = await _project(client)
    fake_queue.fail = True
    response = await _scan(client, project_id)
    assert response.status_code == 503
    runs = (await client.get(f"/api/v1/projects/{project_id}/scans")).json()
    assert [run["status"] for run in runs] == ["failed"]
    assert "queue" in runs[0]["failure_reason"]
    fake_queue.fail = False
    assert (await _scan(client, project_id)).status_code == 202  # a failed run does not block


async def test_only_one_active_scan_per_project(client):
    project_id = await _project(client)
    assert (await _scan(client, project_id)).status_code == 202
    assert (await _scan(client, project_id)).status_code == 409


async def test_scan_listing_and_pagination(client, session_factory, artifact_dir, tmp_path):
    project_id = await _project(client)
    ids = []
    for index in range(3):
        run_id = (await _scan(client, project_id)).json()["id"]
        ids.append(run_id)
        await complete_run(
            session_factory, uuid.UUID(run_id), scan_result([]), tmp_path / str(index),
            artifact_dir,
        )
    page = (await client.get(f"/api/v1/projects/{project_id}/scans?limit=2&offset=0")).json()
    assert len(page) == 2
    rest = (await client.get(f"/api/v1/projects/{project_id}/scans?limit=2&offset=2")).json()
    assert len(rest) == 1
    assert {run["id"] for run in page + rest} == set(ids)
    assert (await client.get(f"/api/v1/projects/{project_id}/scans?limit=101")).status_code == 422
    assert (await client.get(f"/api/v1/projects/{uuid.uuid4()}/scans")).status_code == 404


async def test_completed_scan_details_findings_and_filtering(
    client, session_factory, artifact_dir, tmp_path
):
    project_id = await _project(client)
    run_id = (await _scan(client, project_id)).json()["id"]
    result = scan_result(
        [finding("a", "high", artifact_key="screenshot"), finding("b", "low"), finding("c", "low")]
    )
    await complete_run(session_factory, uuid.UUID(run_id), result, tmp_path / "w", artifact_dir)

    detail = (await client.get(f"/api/v1/scans/{run_id}")).json()
    assert detail["status"] == "completed"
    assert detail["checks_total"] == 2 and detail["checks_passed"] == 1
    assert detail["findings_count"] == 3
    assert detail["severity_counts"] == {"critical": 0, "high": 1, "medium": 0, "low": 2,
                                         "info": 0}
    assert len(detail["artifacts"]) == 1

    findings = (await client.get(f"/api/v1/scans/{run_id}/findings")).json()
    assert [f["severity"] for f in findings] == ["high", "low", "low"]  # most severe first
    low = (await client.get(f"/api/v1/scans/{run_id}/findings?severity=low")).json()
    assert len(low) == 2
    assert (await client.get(f"/api/v1/scans/{run_id}/findings?severity=bad")).status_code == 422
    project_findings = (await client.get(f"/api/v1/projects/{project_id}/findings")).json()
    assert len(project_findings) == 3

    one = (await client.get(f"/api/v1/findings/{findings[0]['id']}")).json()
    assert one["evidence"] == {"message": "a"}
    assert one["artifact"]["url"] == detail["artifacts"][0]["url"]

    projects = (await client.get("/api/v1/projects")).json()
    assert projects[0]["latest_scan"]["status"] == "completed"
    assert projects[0]["latest_scan"]["findings_count"] == 3
    summary = (await client.get("/api/v1/scans/summary")).json()
    assert summary == {"project_count": 1, "scan_count": 1, "active_scan_count": 0,
                       "latest_findings_count": 3}


async def test_missing_run_and_finding(client):
    missing = uuid.uuid4()
    assert (await client.get(f"/api/v1/scans/{missing}")).status_code == 404
    assert (await client.get(f"/api/v1/scans/{missing}/findings")).status_code == 404
    assert (await client.get(f"/api/v1/scans/{missing}/comparison")).status_code == 404
    assert (await client.get(f"/api/v1/findings/{missing}")).status_code == 404
    assert (await client.get("/api/v1/scans/not-a-uuid")).status_code == 422


async def test_artifact_access_is_restricted_to_its_scan(
    client, session_factory, artifact_dir, tmp_path
):
    project_id = await _project(client)
    run_a = (await _scan(client, project_id)).json()["id"]
    await complete_run(session_factory, uuid.UUID(run_a), scan_result([]), tmp_path / "a",
                       artifact_dir)
    artifact = (await client.get(f"/api/v1/scans/{run_a}")).json()["artifacts"][0]

    served = await client.get(artifact["url"])
    assert served.status_code == 200
    assert served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"

    other_project = await _project(client, "https://public.example.org")
    run_b = (await _scan(client, other_project)).json()["id"]
    wrong_run = f"/api/v1/scans/{run_b}/artifacts/{artifact['id']}"
    assert (await client.get(wrong_run)).status_code == 404
    assert (await client.get(f"/api/v1/scans/{run_a}/artifacts/{uuid.uuid4()}")).status_code == 404
    traversal = f"/api/v1/scans/{run_a}/artifacts/..%2F..%2Fpyproject.toml"
    assert (await client.get(traversal)).status_code in (404, 422)

    for path in artifact_dir.rglob("*.png"):
        path.unlink()  # retention cleanup removed the file
    assert (await client.get(artifact["url"])).status_code == 404


async def test_comparison_with_previous_scan(client, session_factory, artifact_dir, tmp_path):
    project_id = await _project(client)
    first = (await _scan(client, project_id)).json()["id"]
    await complete_run(session_factory, uuid.UUID(first),
                       scan_result([finding("kept"), finding("fixed")]), tmp_path / "1",
                       artifact_dir)
    second = (await _scan(client, project_id)).json()["id"]
    await complete_run(session_factory, uuid.UUID(second),
                       scan_result([finding("kept"), finding("new")]), tmp_path / "2",
                       artifact_dir)

    comparison = (await client.get(f"/api/v1/scans/{second}/comparison")).json()
    assert comparison["previous_run_id"] == first
    assert [item["title"] for item in comparison["new"]] == ["Finding new"]
    assert [item["title"] for item in comparison["resolved"]] == ["Finding fixed"]
    assert comparison["unchanged_count"] == 1

    first_seen = {
        f["title"]: f["first_detected_at"]
        for f in (await client.get(f"/api/v1/scans/{second}/findings")).json()
    }
    original = {
        f["title"]: f["first_detected_at"]
        for f in (await client.get(f"/api/v1/scans/{first}/findings")).json()
    }
    assert first_seen["Finding kept"] == original["Finding kept"]


async def test_cancel_only_queued_scans(client, session_factory, artifact_dir, tmp_path):
    project_id = await _project(client)
    run_id = (await _scan(client, project_id)).json()["id"]
    cancelled = await client.post(f"/api/v1/scans/{run_id}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert (await client.post(f"/api/v1/scans/{run_id}/cancel")).status_code == 409


async def test_deleting_a_project_removes_its_scans_and_files(
    client, session_factory, artifact_dir, tmp_path
):
    project_id = await _project(client)
    run_id = (await _scan(client, project_id)).json()["id"]
    await complete_run(session_factory, uuid.UUID(run_id), scan_result([finding("x")]),
                       tmp_path / "w", artifact_dir)
    assert (artifact_dir / run_id).is_dir()
    assert (await client.delete(f"/api/v1/projects/{project_id}")).status_code == 204
    assert (await client.get(f"/api/v1/scans/{run_id}")).status_code == 404
    assert not (artifact_dir / run_id).exists()


async def test_readiness_fails_when_the_queue_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(settings, "queue_backend", "redis")
    monkeypatch.setattr(
        health, "check_redis", AsyncMock(side_effect=RedisConnectionError("redis://secret@x"))
    )
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "secret" not in response.text


async def test_readiness_ignores_redis_with_database_queue(client, monkeypatch):
    monkeypatch.setattr(settings, "queue_backend", "database")
    monkeypatch.setattr(settings, "redis_required", False)
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
