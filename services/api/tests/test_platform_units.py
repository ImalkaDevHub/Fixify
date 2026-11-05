"""Notifications, schedules, analytics, fix validation, redaction, encryption, and the
Anthropic request shape."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select

from app.ai.prompts import FixEdit, redact_secrets, untrusted
from app.ai.provider import AIError, AnthropicProvider
from app.core.config import Settings, settings
from app.core.crypto import DecryptionError, decrypt_secret, encrypt_secret
from app.db.models import Notification, ScanSchedule, TestRun, User
from app.integrations.github import safe_repo_path, valid_branch_name
from app.services import notifications as notification_service
from app.services.fix_validation import (
    EditError,
    FileChange,
    apply_edit,
    apply_edits,
    check_syntax,
    excerpt,
    validate,
)
from app.services.repository_files import is_readable_path
from app.services.scan_events import notify_run
from app.services.schedules import next_run, run_due_schedules
from tests.conftest import FakeQueue
from tests.scan_helpers import complete_run, finding, scan_result


async def _project(client) -> str:
    response = await client.post(
        "/api/v1/projects", json={"name": "Site", "website_url": "https://example.com"}
    )
    return response.json()["id"]


async def _scan(client, session_factory, artifact_dir, tmp_path, project_id, findings, name):
    run_id = (await client.post(f"/api/v1/projects/{project_id}/scans")).json()["id"]
    await complete_run(
        session_factory, uuid.UUID(run_id), scan_result(findings), tmp_path / name, artifact_dir
    )
    return run_id


# --- Notifications ------------------------------------------------------------------------------


async def test_scan_notifications_and_read_state(client, session_factory, artifact_dir, tmp_path):
    project_id = await _project(client)
    run_id = await _scan(
        client,
        session_factory,
        artifact_dir,
        tmp_path,
        project_id,
        [finding("boom", "critical")],
        "a",
    )
    await notify_run(session_factory, uuid.UUID(run_id), "started")
    await notify_run(session_factory, uuid.UUID(run_id), "finished")
    await notify_run(session_factory, uuid.UUID(run_id), "finished")  # duplicate delivery
    listing = (await client.get("/api/v1/notifications")).json()
    kinds = sorted(item["kind"] for item in listing["items"])
    # scan_started is off by default; completion and critical alerts are sent exactly once.
    assert kinds == ["critical_findings", "scan_completed"]
    assert listing["unread_count"] == 2

    first = listing["items"][0]["id"]
    assert (await client.post(f"/api/v1/notifications/{first}/read")).status_code == 204
    assert (await client.get("/api/v1/notifications")).json()["unread_count"] == 1
    assert (await client.post("/api/v1/notifications/read-all")).json() == {"updated": 1}
    unread = (await client.get("/api/v1/notifications?unread_only=true")).json()
    assert unread == {"items": [], "unread_count": 0}


async def test_notification_preferences(client, session_factory, artifact_dir, tmp_path):
    prefs = {
        p["kind"]: p["enabled"]
        for p in (await client.get("/api/v1/notifications/preferences")).json()
    }
    assert prefs["scan_completed"] is True and prefs["scan_started"] is False
    updated = await client.put(
        "/api/v1/notifications/preferences",
        json={"notifications": {"scan_completed": False, "scan_started": True}},
    )
    assert {p["kind"]: p["enabled"] for p in updated.json()}["scan_completed"] is False
    bad = await client.put(
        "/api/v1/notifications/preferences", json={"notifications": {"nope": True}}
    )
    assert bad.status_code == 422

    project_id = await _project(client)
    run_id = await _scan(client, session_factory, artifact_dir, tmp_path, project_id, [], "b")
    await notify_run(session_factory, uuid.UUID(run_id), "started")
    await notify_run(session_factory, uuid.UUID(run_id), "finished")
    kinds = [item["kind"] for item in (await client.get("/api/v1/notifications")).json()["items"]]
    assert kinds == ["scan_started"]


async def test_notifications_are_private(client, other_client, session_factory):
    async with session_factory() as session:
        await notification_service.notify(
            session, user_id=client.user_id, kind="scan_failed", title="Mine"
        )
        await session.commit()
        note_id = await session.scalar(select(Notification.id))
    assert (await other_client.get("/api/v1/notifications")).json()["unread_count"] == 0
    await other_client.post(f"/api/v1/notifications/{note_id}/read")
    assert (await client.get("/api/v1/notifications")).json()["unread_count"] == 1


# --- Schedules ----------------------------------------------------------------------------------


def test_next_run_calculation():
    now = datetime(2026, 11, 5, 10, 30, tzinfo=UTC)  # a Thursday
    daily = ScanSchedule(frequency="daily", hour_utc=3)
    weekly = ScanSchedule(frequency="weekly", hour_utc=9, weekday=0)
    custom = ScanSchedule(frequency="custom", hour_utc=0, interval_hours=12)
    assert next_run(daily, now) == datetime(2026, 11, 6, 3, tzinfo=UTC)
    assert next_run(ScanSchedule(frequency="daily", hour_utc=11), now) == now.replace(
        hour=11, minute=0
    )
    assert next_run(weekly, now) == datetime(2026, 11, 9, 9, tzinfo=UTC)  # next Monday
    assert next_run(custom, now) == now + timedelta(hours=12)


async def test_schedule_api_validation(client, other_client):
    project_id = await _project(client)
    saved = await client.put(
        f"/api/v1/projects/{project_id}/schedule",
        json={"frequency": "weekly", "weekday": 2, "hour_utc": 4},
    )
    assert saved.status_code == 200 and saved.json()["next_run_at"]
    too_often = await client.put(
        f"/api/v1/projects/{project_id}/schedule", json={"frequency": "custom", "interval_hours": 1}
    )
    assert too_often.status_code == 422
    missing_day = await client.put(
        f"/api/v1/projects/{project_id}/schedule", json={"frequency": "weekly"}
    )
    assert missing_day.status_code == 422
    assert (await other_client.get(f"/api/v1/projects/{project_id}/schedule")).status_code == 404
    disabled = await client.put(
        f"/api/v1/projects/{project_id}/schedule", json={"enabled": False, "frequency": "daily"}
    )
    assert disabled.json()["next_run_at"] is None
    assert (await client.delete(f"/api/v1/projects/{project_id}/schedule")).status_code == 204
    assert (await client.get(f"/api/v1/projects/{project_id}/schedule")).json() is None


async def test_due_schedules_start_exactly_one_scan(client, session_factory, monkeypatch):
    from app.services import scan as scan_service
    from tests.conftest import fake_policy

    monkeypatch.setattr(scan_service, "UrlPolicy", lambda _config: fake_policy())
    project_id = await _project(client)
    await client.put(f"/api/v1/projects/{project_id}/schedule", json={"frequency": "daily"})
    later = datetime.now(UTC) + timedelta(days=2)
    queue = FakeQueue()
    assert await run_due_schedules(session_factory, queue, settings, now=later) == 1
    assert await run_due_schedules(session_factory, queue, settings, now=later) == 0
    async with session_factory() as session:
        runs = (await session.scalars(select(TestRun))).all()
        schedule = await session.scalar(select(ScanSchedule))
    assert len(runs) == 1 and runs[0].trigger == "scheduled"
    assert len(queue.items) == 1
    assert schedule.last_run_id == runs[0].id and schedule.last_outcome == "queued"
    assert schedule.next_run_at.replace(tzinfo=UTC) > later
    scans = (await client.get("/api/v1/scans")).json()
    assert scans[0]["trigger"] == "scheduled"


async def test_schedules_skip_unverified_owners(client, session_factory, monkeypatch):
    project_id = await _project(client)
    await client.put(f"/api/v1/projects/{project_id}/schedule", json={"frequency": "daily"})
    async with session_factory() as session:
        user = await session.get(User, client.user_id)
        user.email_verified_at = None
        await session.commit()
    later = datetime.now(UTC) + timedelta(days=2)
    assert await run_due_schedules(session_factory, FakeQueue(), settings, now=later) == 0
    async with session_factory() as session:
        schedule = await session.scalar(select(ScanSchedule))
        assert "not verified" in schedule.last_outcome
        assert await session.scalar(select(func.count()).select_from(TestRun)) == 0


# --- Analytics ----------------------------------------------------------------------------------


async def test_analytics_empty_state(client):
    data = (await client.get("/api/v1/analytics/overview")).json()
    assert data["scan_count"] == 0 and data["daily"] == [] and data["projects"] == []
    assert data["current_findings"] == {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}


async def test_analytics_counts_new_and_resolved(client, session_factory, artifact_dir, tmp_path):
    project_id = await _project(client)
    await _scan(
        client,
        session_factory,
        artifact_dir,
        tmp_path,
        project_id,
        [finding("a", "high"), finding("b", "low")],
        "one",
    )
    await _scan(
        client,
        session_factory,
        artifact_dir,
        tmp_path,
        project_id,
        [finding("b", "low"), finding("c", "critical")],
        "two",
    )
    data = (await client.get("/api/v1/analytics/overview?days=7")).json()
    assert data["finished_scan_count"] == 2
    assert data["new_findings"] == 1 and data["resolved_findings"] == 1  # c new, a resolved
    assert data["current_findings"]["critical"] == 1 and data["current_findings"]["high"] == 0
    assert data["projects"][0]["health"] == 100 - 25 - 1
    assert sum(point["scans"] for point in data["daily"]) == 2
    assert len(data["recent_scans"]) == 2


async def test_cross_project_findings_default_to_latest_scan(
    client, other_client, session_factory, artifact_dir, tmp_path
):
    project_id = await _project(client)
    await _scan(client, session_factory, artifact_dir, tmp_path, project_id, [finding("old")], "1")
    await _scan(client, session_factory, artifact_dir, tmp_path, project_id, [finding("new")], "2")
    titles = [f["title"] for f in (await client.get("/api/v1/findings")).json()]
    assert titles == ["Finding new"]
    all_titles = {
        f["title"] for f in (await client.get("/api/v1/findings?latest_only=false")).json()
    }
    assert all_titles == {"Finding old", "Finding new"}
    assert (await other_client.get("/api/v1/findings")).json() == []
    assert (await other_client.get("/api/v1/scans")).json() == []


# --- Fix validation -----------------------------------------------------------------------------


def _edit(original: str, replacement: str, path: str = "a.js") -> FixEdit:
    return FixEdit(path=path, original=original, replacement=replacement, reason="r")


def test_apply_edit_rules():
    assert apply_edit("let a = 1;\n", _edit("a = 1", "a = 2")) == "let a = 2;\n"
    for edit, message in [
        (_edit("missing", "x"), "does not appear"),
        (_edit("a", "b"), "appears"),
        (_edit("", "x"), "empty"),
        (_edit("let", "let"), "does not change"),
        (_edit("let", "[REDACTED_SECRET]"), "redacted"),
    ]:
        with pytest.raises(EditError, match=message):
            apply_edit("let a = a;\n", edit)


def test_apply_edits_is_all_or_nothing_per_edit_and_limits_files():
    files = {"a.js": ("s1", "x();\n"), "b.js": ("s2", "y();\n")}
    changes, errors = apply_edits(
        files, [_edit("x()", "z()"), _edit("y()", "w()", "b.js")], max_files=1
    )
    assert any("at most 1" in error for error in errors)
    _, errors = apply_edits(files, [_edit("x()", "z()", "c.js")], max_files=5)
    assert "not part of the provided context" in errors[0]


@pytest.mark.parametrize(
    ("path", "before", "after", "status"),
    [
        ("data.json", '{"a": 1}', '{"a": 1,}', "failed"),
        ("data.json", '{"a": 1}', '{"a": 2}', "passed"),
        ("main.py", "x = 1\n", "x = (\n", "failed"),
        ("main.py", "x = 1\n", "x = 2\n", "passed"),
        ("index.html", "<div><p>a</p></div>", "<div><p>a</div></p>", "failed"),
        ("index.html", "<div>a</div>", "<div>b</div>", "passed"),
        ("app.ts", "f({a: 1});", "f({a: 1);", "failed"),
        ("app.ts", "f('}');", "f('{');", "passed"),  # braces inside strings are ignored
        ("notes.txt", "a", "b", "not_available"),
        # Full parsers (tree-sitter): broken code with perfectly balanced brackets is caught.
        ("app.js", "const a = 1;", "const = 1;", "failed"),
        ("app.ts", "let x: number = 1;", "let x: = 1;", "failed"),
        # (A mismatched closing tag name such as <div></span> is NOT detected: the grammar
        # accepts any closing name; only the TypeScript compiler pairs them. An unclosed
        # element is a parse error.)
        ("view.tsx", "const v = <div>a</div>;", "const v = <div>a;", "failed"),
        ("view.jsx", "const v = <a href='x'>a</a>;", "const v = <a href='x'>b</a>;", "passed"),
        (
            "types.ts",
            "type A = 1;",
            "type A<T> = T extends string ? 1 : 2; const y = <A<1>>x;",
            "passed",
        ),
        ("view.tsx", "export {};", "export const A = (p: {x: number}) => <b>{p.x}</b>;", "passed"),
        ("site.css", ".a { color: red; }", ".a { color: red; }\n.b { color; }", "failed"),
        (
            "site.css",
            ".a { color: red; }",
            "@media (max-width: 4px) { .a { color: blue; } }",
            "passed",
        ),
        # A pre-existing error (e.g. syntax the grammar cannot read) is not blamed on the change.
        ("old.js", "let a = ;\nlet b = 1;", "let a = ;\nlet b = 2;", "passed"),
    ],
)
def test_syntax_checks(path, before, after, status):
    result, _ = check_syntax(FileChange(path, "sha", before, after))
    assert result == status


def test_validate_aggregates():
    ok = FileChange("a.json", "s", "{}", '{"a": 1}')
    plain = FileChange("a.txt", "s", "a", "b")
    assert validate([ok, plain], []).status == "passed"
    assert validate([plain], []).status == "not_available"
    assert validate([ok], ["error"]).status == "failed"


def test_excerpt_shows_only_the_changed_window():
    original = "".join(f"line {n}\n" for n in range(1, 101))
    edit = _edit("line 50\n", "line fifty\n", "f.txt")
    new = apply_edit(original, edit)
    before, after, start = excerpt(original, new, [edit])
    assert start == 47
    assert before.startswith("line 47\n") and before.endswith("line 53\n")
    assert "line fifty" in after and "line 1\n" not in after


# --- Paths, redaction, encryption --------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/app.js", "src/app.js"),
        ("a/./b.js", "a/b.js"),
        ("../x", None),
        ("/etc/passwd", None),
        ("a/../../x", None),
        ("a\\b", None),
        (".git/config", None),
        ("a\x00b", None),
        ("", None),
    ],
)
def test_safe_repo_path(path, expected):
    assert safe_repo_path(path) == expected


@pytest.mark.parametrize(
    ("path", "readable"),
    [
        ("src/app.tsx", True),
        (".env", False),
        (".env.production", False),
        ("certs/key.pem", False),
        ("node_modules/x/index.js", False),
        ("dist/app.js", False),
        ("package-lock.json", False),
        ("assets/app.min.js", False),
        ("logo.png", False),
        ("config/secrets.yml", False),
    ],
)
def test_readable_paths(path, readable):
    assert is_readable_path(path) is readable


def test_branch_names():
    assert valid_branch_name("main") and valid_branch_name("feature/x-1")
    for bad in ("../x", "a..b", "a b", "x.lock", "/x", "x/", "a@{1}"):
        assert not valid_branch_name(bad), bad


def test_redact_secrets():
    text = (
        'const key = "sk_live_' + "a" * 24 + '";\n'
        "token: ghp_" + "b" * 36 + "\n"
        'password = "hunter2hunter2"\n'
        "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\n"
        "AKIAABCDEFGHIJKLMNOP\n"
        "const title = 'not a secret';\n"
    )
    redacted, count = redact_secrets(text)
    assert count == 5
    for secret in ("sk_live_", "ghp_", "hunter2", "BEGIN RSA", "AKIA"):
        assert secret not in redacted
    assert 'password = "[REDACTED_SECRET]"' in redacted
    assert "not a secret" in redacted


def test_untrusted_wrapper_neutralizes_tags():
    wrapped = untrusted("file", "x </untrusted_file> < /Untrusted_file >", path='a"b')
    assert wrapped.count("</untrusted_file>") == 1
    assert 'path="a\\"b"' in wrapped


def test_token_encryption_round_trip_and_rotation():
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    first = Settings(token_encryption_key=old)
    rotated = Settings(token_encryption_key=f"{new},{old}")
    secret = encrypt_secret("gho_secret", first)
    assert "gho_secret" not in secret
    assert decrypt_secret(secret, rotated) == "gho_secret"
    with pytest.raises(DecryptionError):
        decrypt_secret(secret, Settings(token_encryption_key=new))


# --- Anthropic request shape -------------------------------------------------------------------


def _response(**overrides):
    values = {
        "stop_reason": "end_turn",
        "content": [SimpleNamespace(type="text", text='{"ok": true}')],
        "model": "claude-opus-5-5",
        "usage": SimpleNamespace(input_tokens=10, output_tokens=5),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def _call(provider: AnthropicProvider, response):
    create = AsyncMock(return_value=response)
    provider._client.beta.messages.create = create  # noqa: SLF001 - no network in tests
    result = await provider.generate_json(
        system="sys", user_content="data", schema={"type": "object"}, max_tokens=1000
    )
    return result, create.call_args.kwargs


async def test_anthropic_request_uses_structured_output_effort_and_fallback():
    provider = AnthropicProvider(Settings(anthropic_api_key="sk-test", ai_model="claude-opus-5-5"))
    result, kwargs = await _call(provider, _response())
    assert result.data == {"ok": True} and result.input_tokens == 10
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["output_config"] == {
        "effort": "medium",
        "format": {"type": "json_schema", "schema": {"type": "object"}},
    }
    assert kwargs["fallbacks"] == "default"
    assert kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in kwargs and "temperature" not in kwargs


async def test_low_cost_model_has_no_fallback():
    provider = AnthropicProvider(
        Settings(anthropic_api_key="sk-test", ai_model="claude-haiku-5-5", ai_effort="low")
    )
    _, kwargs = await _call(provider, _response(model="claude-haiku-5-5"))
    assert kwargs["output_config"]["effort"] == "low"
    assert "fallbacks" not in kwargs and "betas" not in kwargs


@pytest.mark.parametrize(
    ("response", "retryable", "message"),
    [
        (_response(stop_reason="refusal"), False, "declined"),
        (_response(stop_reason="max_tokens"), False, "output limit"),
        (_response(content=[]), True, "no answer"),
        (_response(content=[SimpleNamespace(type="text", text="not json")]), True, "malformed"),
        (_response(content=[SimpleNamespace(type="text", text="[1]")]), True, "malformed"),
    ],
)
async def test_anthropic_response_problems(response, retryable, message):
    provider = AnthropicProvider(Settings(anthropic_api_key="sk-test"))
    with pytest.raises(AIError, match=message) as raised:
        await _call(provider, response)
    assert raised.value.retryable is retryable


async def test_anthropic_connection_errors_are_retryable():
    import anthropic
    import httpx2

    provider = AnthropicProvider(Settings(anthropic_api_key="sk-test"))
    provider._client.beta.messages.create = AsyncMock(  # noqa: SLF001
        side_effect=anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x"))
    )
    with pytest.raises(AIError) as raised:
        await provider.generate_json(system="s", user_content="u", schema={}, max_tokens=10)
    assert raised.value.retryable is True
    assert "sk-test" not in raised.value.public_message


async def test_analytics_uses_the_run_before_the_window_as_baseline(
    client, session_factory, artifact_dir, tmp_path
):
    project_id = await _project(client)
    old = await _scan(
        client,
        session_factory,
        artifact_dir,
        tmp_path,
        project_id,
        [finding("kept"), finding("fixed")],
        "old",
    )
    async with session_factory() as session:
        run = await session.get(TestRun, uuid.UUID(old))
        run.created_at = datetime.now(UTC) - timedelta(days=40)
        await session.commit()
    await _scan(
        client,
        session_factory,
        artifact_dir,
        tmp_path,
        project_id,
        [finding("kept"), finding("brand-new")],
        "new",
    )
    data = (await client.get("/api/v1/analytics/overview?days=30")).json()
    assert data["scan_count"] == 1  # the old run is outside the window...
    assert (data["new_findings"], data["resolved_findings"]) == (1, 1)  # ...but is the baseline
