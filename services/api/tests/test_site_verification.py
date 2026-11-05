"""Website ownership verification through the scanner's egress proxy (real local HTTP server)."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.api.v1.scans import get_url_policy
from app.core.config import Settings, settings
from app.main import app
from app.scanner.contract import PolicyConfig
from app.scanner.url_policy import UrlPolicy
from app.services.site_verification import meta_tokens


class _Site:
    """Responses are set per test: path -> (status, headers, body)."""

    routes: dict[str, tuple[int, dict[str, str], str]] = {}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        status, headers, body = _Site.routes.get(self.path, (404, {}, "not found"))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())


@contextmanager
def _serve() -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()


@pytest.fixture
def site(client):
    _Site.routes = {}
    with _serve() as port:
        policy = UrlPolicy(
            PolicyConfig(
                allowed_ports=frozenset({port}),
                unsafe_allowed_hosts=frozenset({f"127.0.0.1:{port}"}),
            )
        )
        app.dependency_overrides[get_url_policy] = lambda: policy
        yield f"http://127.0.0.1:{port}"


async def _project(client, url: str) -> str:
    response = await client.post("/api/v1/projects", json={"name": "Site", "website_url": url})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_meta_tag_verification_unlocks_scanning(client, site, monkeypatch, fake_queue):
    monkeypatch.setattr(settings, "require_site_verification", True)
    project_id = await _project(client, site)
    blocked = await client.post(f"/api/v1/projects/{project_id}/scans")
    assert blocked.status_code == 403 and "Verify that you control" in blocked.json()["detail"]

    state = (await client.get(f"/api/v1/projects/{project_id}/verification")).json()
    assert state["required"] is True and state["verified"] is False
    assert state["token"].startswith("fixify-") and state["token"] in state["meta_tag"]
    again = (await client.get(f"/api/v1/projects/{project_id}/verification")).json()
    assert again["token"] == state["token"]  # stable until verified

    _Site.routes["/"] = (200, {}, f"<html><head>{state['meta_tag']}</head><body>Hi</body></html>")
    checked = await client.post(f"/api/v1/projects/{project_id}/verification/check")
    assert checked.status_code == 200, checked.text
    assert checked.json()["verified"] is True and checked.json()["method"] == "meta"
    assert (await client.post(f"/api/v1/projects/{project_id}/scans")).status_code == 202


async def test_well_known_file_verification(client, site):
    project_id = await _project(client, site)
    token = (await client.get(f"/api/v1/projects/{project_id}/verification")).json()["token"]
    _Site.routes["/.well-known/fixify-verification.txt"] = (200, {}, f"{token}\n")
    checked = (await client.post(f"/api/v1/projects/{project_id}/verification/check")).json()
    assert checked["verified"] is True and checked["method"] == "file"
    project = (await client.get(f"/api/v1/projects/{project_id}")).json()
    assert project["verified_host"] == "127.0.0.1" and project["verified_at"]


async def test_wrong_or_missing_token_is_rejected(client, site):
    project_id = await _project(client, site)
    _Site.routes["/"] = (200, {}, '<meta name="fixify-site-verification" content="fixify-wrong">')
    _Site.routes["/.well-known/fixify-verification.txt"] = (200, {}, "fixify-also-wrong")
    response = await client.post(f"/api/v1/projects/{project_id}/verification/check")
    assert response.status_code == 422 and "not found" in response.json()["detail"]


async def test_redirects_to_another_host_are_not_followed(client, site):
    project_id = await _project(client, site)
    token = (await client.get(f"/api/v1/projects/{project_id}/verification")).json()["token"]
    elsewhere = {"Location": f"http://attacker.example.org/?{token}"}
    _Site.routes["/"] = (302, elsewhere, "")
    _Site.routes["/.well-known/fixify-verification.txt"] = (302, elsewhere, "")
    response = await client.post(f"/api/v1/projects/{project_id}/verification/check")
    assert response.status_code == 422


async def test_changing_the_host_resets_verification(client, site, monkeypatch):
    project_id = await _project(client, site)
    token = (await client.get(f"/api/v1/projects/{project_id}/verification")).json()["token"]
    _Site.routes["/.well-known/fixify-verification.txt"] = (200, {}, token)
    await client.post(f"/api/v1/projects/{project_id}/verification/check")
    path_change = await client.patch(
        f"/api/v1/projects/{project_id}", json={"website_url": f"{site}/shop"}
    )
    assert path_change.json()["verified_host"] == "127.0.0.1"  # same host: still verified
    moved = await client.patch(
        f"/api/v1/projects/{project_id}", json={"website_url": "https://example.com"}
    )
    assert moved.json()["verified_host"] is None and moved.json()["verified_at"] is None
    monkeypatch.setattr(settings, "require_site_verification", True)
    assert (await client.post(f"/api/v1/projects/{project_id}/scans")).status_code == 403


async def test_verification_is_owner_only(client, other_client, site):
    project_id = await _project(client, site)
    assert (
        await other_client.get(f"/api/v1/projects/{project_id}/verification")
    ).status_code == 404
    response = await other_client.post(f"/api/v1/projects/{project_id}/verification/check")
    assert response.status_code == 404


async def test_internal_addresses_cannot_be_checked(client):
    project_id = await _project(client, "http://internal.example.org")  # fake DNS: 10.0.0.5
    response = await client.post(f"/api/v1/projects/{project_id}/verification/check")
    assert response.status_code == 422 and "cannot be checked" in response.json()["detail"]


def test_required_by_default_in_production_only():
    assert Settings().site_verification_required is False
    production = Settings(app_env="production", secret_key="k" * 40, email_backend="smtp")
    assert production.site_verification_required is True
    assert Settings(require_site_verification=True).site_verification_required is True


def test_meta_parser_tolerates_attribute_order_and_case():
    html = (
        '<META content="fixify-abc" NAME="Fixify-Site-Verification"><meta name="other" content="x">'
    )
    assert meta_tokens(html) == ["fixify-abc"]
    assert meta_tokens("<<<not html") == []
