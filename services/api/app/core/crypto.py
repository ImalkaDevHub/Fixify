"""Encryption of third-party tokens at rest (Fernet: AES-128-CBC + HMAC-SHA256).

TOKEN_ENCRYPTION_KEY holds one or more comma-separated keys, newest first. New values are
encrypted with the first key; any listed key can decrypt, so keys can be rotated.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import Settings, settings


class EncryptionUnavailableError(RuntimeError):
    pass


class DecryptionError(RuntimeError):
    pass


def _cipher(config: Settings) -> MultiFernet:
    keys = [key.strip() for key in config.token_encryption_key.get_secret_value().split(",")]
    keys = [key for key in keys if key]
    if not keys:
        raise EncryptionUnavailableError("TOKEN_ENCRYPTION_KEY is not configured.")
    try:
        return MultiFernet([Fernet(key.encode()) for key in keys])
    except (ValueError, TypeError) as error:
        raise EncryptionUnavailableError(
            "TOKEN_ENCRYPTION_KEY is not a valid Fernet key."
        ) from error


def encrypt_secret(value: str, config: Settings = settings) -> str:
    return _cipher(config).encrypt(value.encode()).decode()


def decrypt_secret(value: str, config: Settings = settings) -> str:
    try:
        return _cipher(config).decrypt(value.encode()).decode()
    except InvalidToken as error:
        raise DecryptionError(
            "Stored secret cannot be decrypted with the configured keys."
        ) from error
