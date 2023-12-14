from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import config


def _fernet() -> Fernet | None:
    if not config.encryption_key:
        return None
    try:
        return Fernet(config.encryption_key.encode("ascii"))
    except (ValueError, TypeError):
        return None


def encrypt_secret(value: str) -> str | None:
    cipher = _fernet()
    return cipher.encrypt(value.encode("utf-8")).decode("ascii") if cipher else None


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    cipher = _fernet()
    if not cipher:
        return None
    try:
        return cipher.decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None
