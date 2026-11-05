"""Authentication, sessions, CSRF, email verification, password reset, and account deletion."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import func, select

from app.core import security
from app.core.config import settings
from app.db.models import Project, User, UserSession
from tests.conftest import PASSWORD, create_user, new_client, sign_in

REGISTER = {"email": "Ada@Example.com", "password": "a long enough secret", "display_name": "Ada"}


async def test_register_signs_in_and_sends_verification(anon_client, outbox):
    response = await anon_client.post("/api/v1/auth/register", json=REGISTER)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "ada@example.com"  # normalized
    assert body["email_verified"] is False
    assert "password" not in response.text
    for name in ("fixify_access", "fixify_refresh", "fixify_csrf", "fixify_session"):
        assert name in anon_client.cookies
    me = await anon_client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["display_name"] == "Ada"
    assert outbox.messages[-1].to == "ada@example.com"
    assert "/verify-email#token=" in outbox.messages[-1].text


async def test_access_cookie_is_http_only_and_refresh_is_path_scoped(anon_client):
    response = await anon_client.post("/api/v1/auth/register", json=REGISTER)
    cookies = response.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith("fixify_access="))
    refresh = next(c for c in cookies if c.startswith("fixify_refresh="))
    csrf = next(c for c in cookies if c.startswith("fixify_csrf="))
    assert "HttpOnly" in access and "SameSite=lax" in access and "Path=/api" in access
    assert "HttpOnly" in refresh and "SameSite=strict" in refresh
    assert "Path=/api/v1/auth" in refresh
    assert "HttpOnly" not in csrf  # must be readable by the web app


async def test_email_verification_is_single_use(anon_client, outbox):
    await anon_client.post("/api/v1/auth/register", json=REGISTER)
    token = outbox.token("verify")
    verified = await anon_client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verified.status_code == 200 and verified.json()["email_verified"] is True
    again = await anon_client.post("/api/v1/auth/verify-email", json={"token": token})
    assert again.status_code == 400


async def test_resending_verification_invalidates_the_previous_link(anon_client, outbox):
    await anon_client.post("/api/v1/auth/register", json=REGISTER)
    first = outbox.token("verify")
    anon_client.headers["X-CSRF-Token"] = anon_client.cookies["fixify_csrf"]
    assert (await anon_client.post("/api/v1/auth/resend-verification")).status_code == 200
    second = outbox.token("verify")
    assert first != second
    stale = await anon_client.post("/api/v1/auth/verify-email", json={"token": first})
    assert stale.status_code == 400
    fresh = await anon_client.post("/api/v1/auth/verify-email", json={"token": second})
    assert fresh.status_code == 200


async def test_duplicate_registration_is_rejected(anon_client):
    assert (await anon_client.post("/api/v1/auth/register", json=REGISTER)).status_code == 201
    duplicate = {**REGISTER, "email": "  ADA@example.COM "}
    response = await new_client().post("/api/v1/auth/register", json=duplicate)
    assert response.status_code == 409


@pytest.mark.parametrize(
    "password", ["short", "          " * 2, "password123", "x" * 129]
)
async def test_weak_passwords_are_rejected(anon_client, password):
    response = await anon_client.post(
        "/api/v1/auth/register", json={**REGISTER, "password": password}
    )
    assert response.status_code == 422


async def test_password_cannot_equal_the_email(anon_client):
    response = await anon_client.post(
        "/api/v1/auth/register",
        json={"email": "longname123@example.com", "password": "longname123@example.com",
              "display_name": "X"},
    )
    assert response.status_code == 400


async def test_login_failures_are_generic(anon_client, session_factory):
    await create_user(session_factory, "known@example.com")
    wrong = await anon_client.post(
        "/api/v1/auth/login", json={"email": "known@example.com", "password": "wrong password!"}
    )
    unknown = await anon_client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong password!"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert "fixify_access" not in anon_client.cookies


async def test_login_is_rate_limited_per_account(anon_client, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_account", 3)
    await create_user(session_factory, "target@example.com")
    statuses = [
        (
            await anon_client.post(
                "/api/v1/auth/login", json={"email": "target@example.com", "password": "nope-nope!"}
            )
        ).status_code
        for _ in range(4)
    ]
    assert statuses == [401, 401, 401, 429]
    blocked = await anon_client.post(
        "/api/v1/auth/login", json={"email": "target@example.com", "password": PASSWORD}
    )
    assert blocked.status_code == 429 and blocked.headers["Retry-After"]


async def test_inactive_users_cannot_sign_in(anon_client, session_factory):
    user = await create_user(session_factory, "gone@example.com")
    async with session_factory() as session:
        (await session.get(User, user.id)).is_active = False
        await session.commit()
    response = await anon_client.post(
        "/api/v1/auth/login", json={"email": "gone@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401


async def test_protected_routes_require_a_session(anon_client):
    for method, path in [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/projects"),
        ("GET", "/api/v1/scans/summary"),
        ("GET", f"/api/v1/scans/{uuid.uuid4()}"),
        ("GET", f"/api/v1/findings/{uuid.uuid4()}"),
        ("GET", "/api/v1/users/me/sessions"),
    ]:
        response = await anon_client.request(method, path)
        assert response.status_code == 401, path


async def test_unsafe_requests_need_the_csrf_header(client):
    token = client.headers.pop("X-CSRF-Token")
    body = {"name": "Site", "website_url": "https://example.com"}
    missing = await client.post("/api/v1/projects", json=body)
    wrong = await client.post("/api/v1/projects", json=body, headers={"X-CSRF-Token": "x" * 43})
    right = await client.post("/api/v1/projects", json=body, headers={"X-CSRF-Token": token})
    assert (missing.status_code, wrong.status_code, right.status_code) == (403, 403, 201)


async def test_csrf_token_of_another_session_is_rejected(client, other_client):
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Site", "website_url": "https://example.com"},
        headers={"X-CSRF-Token": other_client.headers["X-CSRF-Token"]},
    )
    assert response.status_code == 403


async def test_cross_site_origin_is_rejected(client):
    response = await client.post(
        "/api/v1/projects",
        json={"name": "Site", "website_url": "https://example.com"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    trusted = await client.post(
        "/api/v1/projects",
        json={"name": "Site", "website_url": "https://example.com"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert trusted.status_code == 201


async def test_tampered_and_unsigned_tokens_are_rejected(client):
    token = client.cookies["fixify_access"]
    claims = jwt.decode(token, options={"verify_signature": False})
    forged = jwt.encode(claims, "an attacker's key, not the server secret", algorithm="HS256")
    unsigned = jwt.encode(claims, None, algorithm="none")  # type: ignore[arg-type]
    for bad in (forged, unsigned, token[:-4] + "AAAA"):
        async with new_client() as attacker:
            attacker.cookies.set("fixify_access", bad)
            assert (await attacker.get("/api/v1/auth/me")).status_code == 401


async def test_expired_access_token_is_rejected(client, session_factory):
    claims = jwt.decode(client.cookies["fixify_access"], options={"verify_signature": False})
    claims["exp"] = int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())
    expired = jwt.encode(claims, settings.secret_key.get_secret_value(), algorithm="HS256")
    async with new_client() as other:
        other.cookies.set("fixify_access", expired)
        assert (await other.get("/api/v1/auth/me")).status_code == 401


async def test_refresh_rotates_and_reuse_revokes_the_session(client):
    old_refresh = client.cookies["fixify_refresh"]
    rotated = await client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    assert client.cookies["fixify_refresh"] != old_refresh
    assert (await client.get("/api/v1/auth/me")).status_code == 200

    async with new_client() as thief:  # a stolen, already-rotated token
        thief.cookies.set("fixify_refresh", old_refresh)
        reused = await thief.post("/api/v1/auth/refresh")
        assert reused.status_code == 401
    # The legitimate holder is signed out too: the whole session was revoked.
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_failed_refresh_clears_cookies(anon_client):
    anon_client.cookies.set("fixify_refresh", "x" * 43)
    response = await anon_client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert any(
        c.startswith("fixify_access=") and "Max-Age=0" in c
        for c in response.headers.get_list("set-cookie")
    )


async def test_logout_revokes_the_session(client):
    access = client.cookies["fixify_access"]
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    async with new_client() as replay:
        replay.cookies.set("fixify_access", access)
        assert (await replay.get("/api/v1/auth/me")).status_code == 401


async def test_password_reset_flow(anon_client, session_factory, outbox):
    await create_user(session_factory, "reset@example.com")
    async with new_client() as device:  # an existing session that must end
        await sign_in(device, "reset@example.com")
        unknown = await anon_client.post(
            "/api/v1/auth/forgot-password", json={"email": "missing@example.com"}
        )
        known = await anon_client.post(
            "/api/v1/auth/forgot-password", json={"email": "reset@example.com"}
        )
        assert unknown.status_code == known.status_code == 202
        assert unknown.json() == known.json()
        assert len(outbox.messages) == 1

        token = outbox.token("reset")
        new_password = "brand new passphrase"
        reset = await anon_client.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": new_password}
        )
        assert reset.status_code == 200
        assert (await device.get("/api/v1/auth/me")).status_code == 401
        reused = await anon_client.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": "another passphrase"}
        )
        assert reused.status_code == 400

    old = await anon_client.post(
        "/api/v1/auth/login", json={"email": "reset@example.com", "password": PASSWORD}
    )
    new = await anon_client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.com", "password": "brand new passphrase"},
    )
    assert (old.status_code, new.status_code) == (401, 200)


async def test_expired_reset_token_is_rejected(anon_client, session_factory, outbox, monkeypatch):
    await create_user(session_factory, "late@example.com")
    await anon_client.post("/api/v1/auth/forgot-password", json={"email": "late@example.com"})
    token = outbox.token("reset")
    from app.services import auth as auth_service

    later = datetime.now(UTC) + timedelta(minutes=settings.password_reset_ttl_minutes + 1)
    monkeypatch.setattr(auth_service, "utcnow", lambda: later)
    response = await anon_client.post(
        "/api/v1/auth/reset-password", json={"token": token, "password": "brand new passphrase"}
    )
    assert response.status_code == 400


async def test_change_password_signs_out_other_sessions(client, session_factory):
    async with new_client() as laptop:
        await sign_in(laptop, "owner@example.com")
        wrong = await client.post(
            "/api/v1/users/me/password",
            json={"current_password": "not it at all", "new_password": "another passphrase"},
        )
        assert wrong.status_code == 401
        changed = await client.post(
            "/api/v1/users/me/password",
            json={"current_password": PASSWORD, "new_password": "another passphrase"},
        )
        assert changed.status_code == 200
        assert (await client.get("/api/v1/auth/me")).status_code == 200  # this session stays
        assert (await laptop.get("/api/v1/auth/me")).status_code == 401


async def test_sessions_can_be_listed_and_revoked(client):
    async with new_client() as phone:
        await sign_in(phone, "owner@example.com")
        sessions = (await client.get("/api/v1/users/me/sessions")).json()
        assert len(sessions) == 2
        assert sum(item["current"] for item in sessions) == 1
        other = next(item for item in sessions if not item["current"])
        assert (await client.delete(f"/api/v1/users/me/sessions/{other['id']}")).status_code == 204
        assert (await phone.get("/api/v1/auth/me")).status_code == 401
        missing = await client.delete(f"/api/v1/users/me/sessions/{uuid.uuid4()}")
        assert missing.status_code == 404


async def test_users_cannot_revoke_each_others_sessions(client, other_client):
    theirs = (await other_client.get("/api/v1/users/me/sessions")).json()[0]["id"]
    assert (await client.delete(f"/api/v1/users/me/sessions/{theirs}")).status_code == 404
    assert (await other_client.get("/api/v1/auth/me")).status_code == 200


async def test_profile_update(client):
    response = await client.patch("/api/v1/users/me", json={"display_name": "  New   Name "})
    assert response.status_code == 200 and response.json()["display_name"] == "New Name"
    bad = await client.patch("/api/v1/users/me", json={"display_name": "a\x00b"})
    assert bad.status_code == 422


async def test_delete_account_removes_owned_data(client, other_client, session_factory):
    mine = await client.post(
        "/api/v1/projects", json={"name": "Mine", "website_url": "https://example.com"}
    )
    await other_client.post(
        "/api/v1/projects", json={"name": "Theirs", "website_url": "https://example.com"}
    )
    wrong = await client.request("DELETE", "/api/v1/users/me", json={"password": "not right!!"})
    assert wrong.status_code == 401
    deleted = await client.request("DELETE", "/api/v1/users/me", json={"password": PASSWORD})
    assert deleted.status_code == 204
    async with session_factory() as session:
        assert await session.get(Project, uuid.UUID(mine.json()["id"])) is None
        assert await session.scalar(select(func.count()).select_from(Project)) == 1
        assert await session.scalar(select(func.count()).select_from(UserSession).where(
            UserSession.user_id == client.user_id)) == 0
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_unverified_users_cannot_start_scans(unverified_client, fake_queue):
    project = await unverified_client.post(
        "/api/v1/projects", json={"name": "Site", "website_url": "https://example.com"}
    )
    assert project.status_code == 201
    response = await unverified_client.post(f"/api/v1/projects/{project.json()['id']}/scans")
    assert response.status_code == 403
    assert "Verify your email" in response.json()["detail"]
    assert fake_queue.items == []


def test_production_refuses_unsafe_settings():
    from app.core.config import Settings

    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(app_env="production", secret_key="short", email_backend="smtp")
    with pytest.raises(ValueError, match="console"):
        Settings(app_env="production", secret_key="k" * 40, email_backend="console")
    ok = Settings(app_env="production", secret_key="k" * 40, email_backend="smtp")
    assert ok.secure_cookies is True


def test_passwords_are_hashed_with_argon2id():
    hashed = security.hash_password("a long enough secret")
    assert hashed.startswith("$argon2id$")
    assert security.verify_password(hashed, "a long enough secret")
    assert not security.verify_password(hashed, "a long enough secreT")
    assert not security.verify_password("not-a-hash", "anything")
