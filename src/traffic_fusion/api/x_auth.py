from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime

from fastapi import HTTPException, Request

from traffic_fusion.api.moderation import (
    SESSION_COOKIE,
    _decode,
    _encode,
    _session_secret,
)
from traffic_fusion.extraction.accounts import Account, AccountStore

_FAILS: dict[str, list[float]] = {}
MAX_FAILS, WINDOW = 5, 300.0


def check_lockout(key: str) -> None:
    now = time.monotonic()
    recent = [t for t in _FAILS.get(key, []) if now - t < WINDOW]
    _FAILS[key] = recent
    if len(recent) >= MAX_FAILS:
        raise HTTPException(status_code=429, detail="Too many failed sign-ins; wait 5 minutes")


def record_failure(key: str) -> None:
    _FAILS.setdefault(key, []).append(time.monotonic())


def clear_failures(key: str) -> None:
    _FAILS.pop(key, None)


def current_user(
    request: Request,
    store: AccountStore,
    *,
    roles: tuple[str, ...] | None = None,
    csrf: bool = False,
) -> tuple[Account, str]:
    """Validate the signed session cookie against the account store and its roles."""
    token = request.cookies.get(SESSION_COOKIE, "")
    try:
        encoded, supplied = token.split(".", 1)
        expected = _encode(hmac.new(_session_secret(), encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied, expected):
            raise ValueError("bad signature")
        payload = json.loads(_decode(encoded))
        username, csrf_token = str(payload["username"]), str(payload["csrf"])
        expires_at = int(payload["expires_at"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Sign-in required") from exc
    account = store.get(username)
    if expires_at <= int(datetime.now(UTC).timestamp()) or account is None:
        raise HTTPException(status_code=401, detail="Session expired")
    if csrf and not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), csrf_token):
        raise HTTPException(status_code=403, detail="Invalid request token")
    if roles and not set(roles) & set(account.roles):
        raise HTTPException(status_code=403, detail="Your account lacks the required role")
    return account, csrf_token
