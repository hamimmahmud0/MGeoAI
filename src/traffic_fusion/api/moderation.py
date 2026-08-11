from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import shutil
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from traffic_fusion.utils import stable_id

SESSION_COOKIE = "mgeoai_reviewer"
SESSION_TTL = timedelta(hours=8)
PASSWORD_ITERATIONS = 260_000


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubmissionInput(ApiModel):
    source_kind: Literal["news", "social", "other"] = "news"
    title: str = Field(min_length=3, max_length=240)
    publisher: str | None = Field(default=None, max_length=160)
    source_uri: AnyHttpUrl | None = None
    content: str = Field(min_length=20, max_length=100_000)
    submitter_name: str | None = Field(default=None, max_length=120)


class LoginInput(ApiModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=512)


class ReviewInput(ApiModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2_000)


class SubmissionStore:
    def __init__(self, root: Path):
        self.root = root / "moderation" / "submissions"
        self._lock = threading.Lock()

    def create(self, payload: SubmissionInput) -> dict[str, object]:
        now = datetime.now(UTC)
        submission_id = stable_id(
            "sub", now.isoformat(), secrets.token_hex(16), payload.content
        )
        record: dict[str, object] = {
            "submission_id": submission_id,
            "status": "pending",
            **payload.model_dump(mode="json"),
            "submitted_at": now.isoformat(),
            "reviewed_by": None,
            "reviewed_at": None,
            "review_note": None,
            "pipeline_run_id": None,
            "loaded_source_ids": [],
            "loaded_incident_ids": [],
            "ingest_error": None,
            "audit": [
                {
                    "action": "submitted",
                    "actor": payload.submitter_name or "anonymous submitter",
                    "at": now.isoformat(),
                }
            ],
        }
        with self._lock:
            self._write(record)
        return record

    def list(self, status: str | None = None) -> list[dict[str, object]]:
        if not self.root.exists():
            return []
        rows = [self._read(path) for path in self.root.glob("sub_*.json")]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return sorted(rows, key=lambda row: str(row.get("submitted_at", "")), reverse=True)

    def get(self, submission_id: str) -> dict[str, object]:
        if not submission_id.startswith("sub_") or not submission_id[4:].isalnum():
            raise HTTPException(status_code=404, detail="Submission not found")
        path = self.root / f"{submission_id}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Submission not found")
        return self._read(path)

    def update(self, submission_id: str, **values: object) -> dict[str, object]:
        with self._lock:
            record = self.get(submission_id)
            record.update(values)
            self._write(record)
        return record

    def add_audit(
        self, submission_id: str, *, action: str, actor: str, detail: str | None = None
    ) -> dict[str, object]:
        with self._lock:
            record = self.get(submission_id)
            stored_audit = record.get("audit")
            audit: list[object] = list(stored_audit) if isinstance(stored_audit, list) else []
            event: dict[str, object] = {
                "action": action,
                "actor": actor,
                "at": datetime.now(UTC).isoformat(),
            }
            if detail:
                event["detail"] = detail
            audit.append(event)
            record["audit"] = audit
            self._write(record)
        return record

    def _read(self, path: Path) -> dict[str, object]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=500, detail="Submission store is unreadable") from exc
        if not isinstance(value, dict):
            raise HTTPException(status_code=500, detail="Submission store is invalid")
        return value

    def _write(self, record: dict[str, object]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        submission_id = str(record["submission_id"])
        target = self.root / f"{submission_id}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)


def configured_reviewers() -> dict[str, str]:
    raw = os.getenv("MGEOAI_REVIEWERS_JSON", "")
    try:
        value = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail="Reviewer authentication is misconfigured") from exc
    if not isinstance(value, dict) or not all(
        isinstance(key, str)
        and isinstance(password, str)
        and key
        and password.startswith("pbkdf2_sha256$")
        for key, password in value.items()
    ):
        raise HTTPException(status_code=503, detail="Reviewer authentication is misconfigured")
    return value


def authenticate(username: str, password: str) -> bool:
    expected = configured_reviewers().get(username)
    if expected is None:
        hashlib.pbkdf2_hmac("sha256", password.encode(), b"invalid-user", PASSWORD_ITERATIONS)
        return False
    return verify_password(password, expected)


def hash_reviewer_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_encode(salt)}${_encode(digest)}"


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
    encoded = _encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _encode(hmac.new(_session_secret(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}", csrf


def require_reviewer(request: Request, *, csrf: bool = False) -> tuple[str, str]:
    token = request.cookies.get(SESSION_COOKIE, "")
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _encode(
            hmac.new(_session_secret(), encoded.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("invalid signature")
        payload = json.loads(_decode(encoded))
        username = str(payload["username"])
        csrf_token = str(payload["csrf"])
        expires_at = int(payload["expires_at"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Reviewer login required") from exc
    if expires_at <= int(datetime.now(UTC).timestamp()) or username not in configured_reviewers():
        raise HTTPException(status_code=401, detail="Reviewer session expired")
    if csrf and not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), csrf_token):
        raise HTTPException(status_code=403, detail="Invalid review request token")
    return username, csrf_token


def materialize_submission(root: Path, record: dict[str, object]) -> Path:
    submission_id = str(record["submission_id"])
    target = root / "runtime_scraps" / "html" / submission_id
    target.mkdir(parents=True, exist_ok=True)
    title = html.escape(str(record["title"]))
    paragraphs = [
        f"<p>{html.escape(part.strip())}</p>"
        for part in str(record["content"]).splitlines()
        if part.strip()
    ]
    platform = (
        '<meta name="source-platform" content="Facebook">'
        if record.get("source_kind") == "social"
        else ""
    )
    (target / "content.html").write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"{platform}<title>{title}</title></head><body><article><h1>{title}</h1>"
        + "".join(paragraphs)
        + "</article></body></html>\n",
        encoding="utf-8",
    )
    publisher = " ".join(str(record.get("publisher") or "Runtime submission").split())
    info = [
        f"Source name: {publisher}",
        f"Submission ID: {submission_id}",
    ]
    if record.get("source_uri"):
        info.append(f"News link: {record['source_uri']}")
    (target / "SOURCE_INFO.md").write_text("\n".join(info) + "\n", encoding="utf-8")
    return target


@contextmanager
def combined_scraps(
    base_scraps: Path,
    runtime_scraps: Path,
    candidate_scraps: Path | None = None,
) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="mgeoai-scraps-") as temporary:
        combined = Path(temporary)
        if base_scraps.exists():
            shutil.copytree(base_scraps, combined, dirs_exist_ok=True)
        if runtime_scraps.exists():
            shutil.copytree(runtime_scraps, combined / "runtime", dirs_exist_ok=True)
        if candidate_scraps and candidate_scraps.exists():
            shutil.copytree(candidate_scraps, combined / "runtime", dirs_exist_ok=True)
        yield combined


def publish_pipeline_output(staging: Path, root: Path) -> None:
    """Replace generated pipeline artifacts without touching moderation/runtime data."""
    root.mkdir(parents=True, exist_ok=True)
    publication_id = secrets.token_hex(8)
    staged_paths = sorted(staging.iterdir(), key=lambda path: path.name)
    backups: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for staged_path in staged_paths:
            target = root / staged_path.name
            backup = root / f".{staged_path.name}.previous-{publication_id}"
            if target.exists() or target.is_symlink():
                target.replace(backup)
                backups.append((target, backup))
        for staged_path in staged_paths:
            target = root / staged_path.name
            staged_path.replace(target)
            published.append(target)
    except Exception:
        for target in reversed(published):
            _remove_path(target)
        for target, backup in reversed(backups):
            if backup.exists() or backup.is_symlink():
                backup.replace(target)
        raise
    for _, backup in backups:
        _remove_path(backup)


def remove_materialized_submission(root: Path, submission_id: str) -> None:
    if submission_id.startswith("sub_") and submission_id[4:].isalnum():
        _remove_path(root / "runtime_scraps" / "html" / submission_id)


def _session_secret() -> bytes:
    value = os.getenv("MGEOAI_SESSION_SECRET", "")
    if len(value) < 32:
        raise HTTPException(
            status_code=503,
            detail="Reviewer sessions require MGEOAI_SESSION_SECRET with at least 32 characters",
        )
    return value.encode()


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding).decode()
