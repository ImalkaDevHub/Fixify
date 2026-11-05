"""Password hashing, access tokens, opaque tokens, and CSRF tokens."""

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings, settings

ACCESS_TOKEN_TYPE = "access"
_JWT_ALGORITHM = "HS256"
_ISSUER = "fixify-api"


@lru_cache
def _hasher(memory_kib: int, time_cost: int) -> PasswordHasher:
    return PasswordHasher(memory_cost=memory_kib, time_cost=time_cost, parallelism=4)


def password_hasher(config: Settings = settings) -> PasswordHasher:
    return _hasher(config.password_hash_memory_kib, config.password_hash_time_cost)


def hash_password(password: str, config: Settings = settings) -> str:
    return password_hasher(config).hash(password)


def verify_password(password_hash: str, password: str, config: Settings = settings) -> bool:
    try:
        return password_hasher(config).verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str, config: Settings = settings) -> bool:
    try:
        return password_hasher(config).check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


@lru_cache
def _dummy_hash(memory_kib: int, time_cost: int) -> str:
    return _hasher(memory_kib, time_cost).hash(secrets.token_urlsafe(16))


def burn_password_check(password: str, config: Settings = settings) -> None:
    """Spend the same time as a real verification, so unknown emails are not distinguishable."""
    verify_password(
        _dummy_hash(config.password_hash_memory_kib, config.password_hash_time_cost),
        password,
        config,
    )


def new_opaque_token() -> str:
    """256 bits of randomness, URL-safe. Only its hash is ever stored."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    expires_at: datetime


def create_access_token(
    user_id: uuid.UUID, session_id: uuid.UUID, config: Settings = settings
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=config.access_token_ttl_minutes)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "typ": ACCESS_TOKEN_TYPE,
            "iss": _ISSUER,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
        },
        config.secret_key.get_secret_value(),
        algorithm=_JWT_ALGORITHM,
    )
    return token, expires


def decode_access_token(token: str, config: Settings = settings) -> AccessClaims | None:
    try:
        payload = jwt.decode(
            token,
            config.secret_key.get_secret_value(),
            algorithms=[_JWT_ALGORITHM],  # never accept "none" or asymmetric confusion
            issuer=_ISSUER,
            options={"require": ["sub", "sid", "exp", "iat", "typ"]},
        )
        if payload.get("typ") != ACCESS_TOKEN_TYPE:
            return None
        return AccessClaims(
            user_id=uuid.UUID(payload["sub"]),
            session_id=uuid.UUID(payload["sid"]),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


def csrf_token_for(session_id: uuid.UUID, config: Settings = settings) -> str:
    """CSRF token bound to the session; a token from another session or cookie never matches."""
    digest = hmac.new(
        config.secret_key.get_secret_value().encode(),
        f"csrf:{session_id}".encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def csrf_matches(session_id: uuid.UUID, presented: str | None, config: Settings = settings) -> bool:
    if not presented:
        return False
    return hmac.compare_digest(csrf_token_for(session_id, config), presented)
