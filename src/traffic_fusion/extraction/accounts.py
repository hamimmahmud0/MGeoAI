"""Role-based accounts for the extraction workspace.

Roles: `admin` (control panel, accounts, runs), `reviewer` (read scores, map and model
output, adjudicate), `annotator` (blind annotation only). A user may hold several roles.
Passwords are PBKDF2 hashes (same scheme as the legacy reviewer login).
"""

from __future__ import annotations

import fcntl
import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Literal

from pydantic import BaseModel, ConfigDict, Field

from traffic_fusion.api.moderation import hash_reviewer_password, verify_password

Role = Literal["admin", "reviewer", "annotator"]
ROLES: tuple[str, ...] = ("admin", "reviewer", "annotator")
USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
MIN_PASSWORD = 12


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    roles: list[Role] = Field(min_length=1)
    password_hash: str
    disabled: bool = False
    created_at: str


class AccountStore:
    def __init__(self, root: Path) -> None:
        self.path = root / "accounts.json"
        self.root = root

    def _read(self) -> dict[str, Account]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {name: Account.model_validate(value) for name, value in raw.items()}

    def _write(self, accounts: dict[str, Account]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({k: v.model_dump() for k, v in accounts.items()}, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def _locked(self) -> IO[str]:
        self.root.mkdir(parents=True, exist_ok=True)
        handle = (self.root / ".accounts.lock").open("a")
        fcntl.flock(handle, fcntl.LOCK_EX)
        return handle

    def all(self) -> list[Account]:
        return sorted(self._read().values(), key=lambda a: a.username)

    def get(self, username: str) -> Account | None:
        account = self._read().get(username)
        return None if account is None or account.disabled else account

    def authenticate(self, username: str, password: str) -> Account | None:
        account = self.get(username)
        if account is None:
            verify_password(password, hash_reviewer_password("x"))  # equalise timing
            return None
        return account if verify_password(password, account.password_hash) else None

    def upsert(
        self,
        username: str,
        roles: list[Role],
        password: str | None = None,
        disabled: bool | None = None,
    ) -> Account:
        if not USERNAME_RE.match(username):
            raise ValueError("username must be lowercase letters, digits or underscores")
        if any(role not in ROLES for role in roles) or not roles:
            raise ValueError("roles must be a non-empty subset of admin, reviewer, annotator")
        handle = self._locked()
        try:
            accounts = self._read()
            existing = accounts.get(username)
            if password is None and existing is None:
                raise ValueError("a password is required for a new account")
            if password is not None and len(password) < MIN_PASSWORD:
                raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
            account = Account(
                username=username,
                roles=roles,
                password_hash=(
                    hash_reviewer_password(password)
                    if password is not None
                    else existing.password_hash  # type: ignore[union-attr]
                ),
                disabled=existing.disabled if disabled is None and existing else bool(disabled),
                created_at=existing.created_at if existing else datetime.now(UTC).isoformat(),
            )
            others = [a for a in accounts.values() if a.username != username]
            if not any("admin" in a.roles and not a.disabled for a in [*others, account]):
                raise ValueError("at least one enabled admin account must remain")
            accounts[username] = account
            self._write(accounts)
            return account
        finally:
            handle.close()

    def bootstrap(self, specs: dict[str, list[Role]]) -> dict[str, str]:
        """Create missing accounts with random passwords; return {username: password}.

        The caller writes the passwords to a private file. Existing accounts are kept.
        """
        created: dict[str, str] = {}
        existing = {a.username for a in self.all()}
        ordered = sorted(specs.items(), key=lambda kv: "admin" not in kv[1])
        for username, roles in ordered:
            if username in existing:
                continue
            password = secrets.token_urlsafe(15)
            self.upsert(username, roles, password)
            created[username] = password
        return created
