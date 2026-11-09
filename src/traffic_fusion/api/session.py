"""Signed session cookies and password hashing for the extraction workspace."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

SESSION_COOKIE = "mgeoai_reviewer"  # historical name, kept so signed-in people stay signed in
SESSION_TTL = timedelta(hours=8)
PASSWORD_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${encode(salt)}${encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if iterations < 100_000 or iterations > 1_000_000:
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def create_session(username: str) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(24)
    payload = {
        "username": username,
        "csrf": csrf,
        "expires_at": int((datetime.now(UTC) + SESSION_TTL).timestamp()),
    }
    encoded = encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = encode(hmac.new(session_secret(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}", csrf


def session_secret() -> bytes:
    value = os.getenv("MGEOAI_SESSION_SECRET", "")
    if len(value) < 32:
        raise HTTPException(
            status_code=503,
            detail="Sessions require MGEOAI_SESSION_SECRET with at least 32 characters",
        )
    return value.encode()


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding).decode()
