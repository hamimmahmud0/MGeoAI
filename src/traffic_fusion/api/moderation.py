from __future__ import annotations

import base64
import hashlib
import hmac
import html
import io
import json
import os
import secrets
import shutil
import stat
import tempfile
import threading
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from traffic_fusion.utils import stable_id

SESSION_COOKIE = "mgeoai_reviewer"
SESSION_TTL = timedelta(hours=8)
PASSWORD_ITERATIONS = 260_000
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_FILES = 50
SubmissionType = Literal["html_bundle", "video_json"]
VIDEO_SECTIONS = {
    "claims",
    "locations",
    "traffic_affecting_events",
    "traffic_conditions",
    "traffic_incidents",
}
IMAGE_SECTIONS = {"observations", "spatial_relationships", "traffic_relevant_objects"}


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginInput(ApiModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=512)


class ReviewInput(ApiModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2_000)


class SubmissionStore:
    def __init__(self, root: Path):
        self.root = root / "moderation" / "submissions"
        self.uploads_root = root / "moderation" / "uploads"
        self._lock = threading.Lock()

    def create_upload(
        self,
        submission_type: SubmissionType,
        original_filename: str,
        payload: bytes,
        submitter_name: str | None,
    ) -> dict[str, object]:
        if not payload:
            raise HTTPException(status_code=422, detail="The uploaded file is empty")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Uploads are limited to 25 MB")
        filename = Path(original_filename).name
        if (
            not filename
            or filename != original_filename
            or len(filename) > 240
            or "\\" in original_filename
            or "\x00" in original_filename
            or any(ord(character) < 32 or ord(character) == 127 for character in filename)
        ):
            raise HTTPException(status_code=422, detail="The upload filename is invalid")
        now = datetime.now(UTC)
        submission_id = stable_id(
            "sub", now.isoformat(), secrets.token_hex(16), hashlib.sha256(payload).hexdigest()
        )
        upload_target = self.uploads_root / submission_id
        self.uploads_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{submission_id}-", dir=self.uploads_root
        ) as temporary:
            quarantine = Path(temporary)
            files_root = quarantine / "files"
            files_root.mkdir()
            if submission_type == "html_bundle":
                original_storage_name = "original.zip"
                manifest = _extract_html_bundle(filename, payload, files_root)
            else:
                original_storage_name = "original.json"
                manifest = _store_video_json(filename, payload, files_root)
            (quarantine / original_storage_name).write_bytes(payload)
            quarantine.replace(upload_target)

        record: dict[str, object] = {
            "submission_id": submission_id,
            "status": "pending",
            "submission_type": submission_type,
            "title": filename,
            "original_filename": filename,
            "original_storage_name": original_storage_name,
            "content_type": (
                "application/zip" if submission_type == "html_bundle" else "application/json"
            ),
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "files": manifest,
            "submitter_name": submitter_name,
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
                    "actor": submitter_name or "anonymous submitter",
                    "at": now.isoformat(),
                }
            ],
        }
        try:
            with self._lock:
                self._write(record)
        except Exception:
            _remove_path(upload_target)
            raise
        return record

    def original_path(self, record: dict[str, object]) -> Path:
        path = self.uploads_root / str(record["submission_id"]) / str(
            record["original_storage_name"]
        )
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Original upload not found")
        return path

    def review_file_path(self, record: dict[str, object], file_id: str) -> tuple[Path, dict[str, object]]:
        files = record.get("files")
        if not isinstance(files, list):
            raise HTTPException(status_code=404, detail="Review file not found")
        entry = next(
            (
                item
                for item in files
                if isinstance(item, dict) and item.get("file_id") == file_id
            ),
            None,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="Review file not found")
        files_root = (self.uploads_root / str(record["submission_id"]) / "files").resolve()
        path = (files_root / str(entry["path"])).resolve()
        if path.parent != files_root or not path.is_file():
            raise HTTPException(status_code=404, detail="Review file not found")
        return path, entry

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


def _extract_html_bundle(
    filename: str, payload: bytes, files_root: Path
) -> list[dict[str, object]]:
    if Path(filename).suffix.casefold() != ".zip":
        raise HTTPException(status_code=422, detail="HTML sources must be uploaded as a ZIP file")
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=422, detail="The HTML bundle is not a valid ZIP file") from exc
    with archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if not members:
            raise HTTPException(status_code=422, detail="The HTML bundle is empty")
        if len(members) > MAX_ARCHIVE_FILES:
            raise HTTPException(
                status_code=422,
                detail=f"HTML bundles may contain at most {MAX_ARCHIVE_FILES} files",
            )
        paths = [_safe_archive_path(item) for item in members]
        common_root = (
            paths[0].parts[0]
            if all(len(path.parts) > 1 and path.parts[0] == paths[0].parts[0] for path in paths)
            else None
        )
        normalized = [PurePosixPath(*path.parts[1:]) if common_root else path for path in paths]
        if any(len(path.parts) != 1 for path in normalized):
            raise HTTPException(
                status_code=422,
                detail="Place the HTML, SOURCE_INFO.md, and image_01.json in one scrap folder",
            )
        names = [path.name for path in normalized]
        if len(set(names)) != len(names):
            raise HTTPException(status_code=422, detail="The HTML bundle has duplicate filenames")
        html_names = [name for name in names if Path(name).suffix.casefold() == ".html"]
        if len(html_names) != 1:
            raise HTTPException(
                status_code=422, detail="The HTML bundle must contain exactly one .html page"
            )
        allowed = {html_names[0], "SOURCE_INFO.md", "image_01.json"}
        unsupported = sorted(set(names).difference(allowed))
        if unsupported:
            raise HTTPException(
                status_code=422,
                detail="Unsupported HTML bundle file(s): " + ", ".join(unsupported),
            )

        total_unpacked = 0
        manifest: list[dict[str, object]] = []
        for member, relative_path in zip(members, normalized, strict=True):
            total_unpacked += member.file_size
            if total_unpacked > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="HTML bundle contents may not exceed 25 MB after extraction",
                )
            try:
                content = archive.read(member)
            except (NotImplementedError, RuntimeError, zipfile.BadZipFile) as exc:
                raise HTTPException(
                    status_code=422, detail=f"Unable to read {relative_path.name} from the ZIP"
                ) from exc
            if len(content) != member.file_size:
                raise HTTPException(status_code=422, detail="The ZIP contains an invalid file size")
            _validate_scrap_file(relative_path.name, content)
            target = files_root / relative_path.name
            target.write_bytes(content)
            manifest.append(_file_manifest(relative_path.name, content))
        return sorted(manifest, key=lambda item: str(item["path"]))


def _store_video_json(
    filename: str, payload: bytes, files_root: Path
) -> list[dict[str, object]]:
    if Path(filename).suffix.casefold() != ".json":
        raise HTTPException(status_code=422, detail="Video analysis must be a .json file")
    data = _json_object(payload, "Video analysis JSON")
    if not any(isinstance(data.get(section), list) for section in VIDEO_SECTIONS):
        raise HTTPException(
            status_code=422,
            detail="Video analysis JSON does not contain a supported traffic evidence section",
        )
    path = files_root / "video.json"
    path.write_bytes(payload)
    return [_file_manifest("video.json", payload)]


def _safe_archive_path(member: zipfile.ZipInfo) -> PurePosixPath:
    if member.flag_bits & 0x1:
        raise HTTPException(status_code=422, detail="Encrypted ZIP entries are not supported")
    mode = member.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise HTTPException(status_code=422, detail="ZIP symbolic links are not supported")
    if "\\" in member.filename:
        raise HTTPException(status_code=422, detail="ZIP paths must use forward slashes")
    path = PurePosixPath(member.filename)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise HTTPException(status_code=422, detail="The ZIP contains an unsafe path")
    if ":" in path.parts[0]:
        raise HTTPException(status_code=422, detail="The ZIP contains an unsafe path")
    if any(
        len(part) > 240
        or any(ord(character) < 32 or ord(character) == 127 for character in part)
        for part in path.parts
    ):
        raise HTTPException(status_code=422, detail="The ZIP contains an unsafe filename")
    return path


def _validate_scrap_file(filename: str, payload: bytes) -> None:
    if filename == "image_01.json":
        data = _json_object(payload, "Image analysis JSON")
        if not any(isinstance(data.get(section), list) for section in IMAGE_SECTIONS):
            raise HTTPException(
                status_code=422,
                detail="Image analysis JSON does not contain a supported evidence section",
            )
        return
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422, detail=f"{filename} must be UTF-8 encoded"
        ) from exc


def _json_object(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail=f"{label} root must be an object")
    return value


def _file_manifest(filename: str, payload: bytes) -> dict[str, object]:
    digest = hashlib.sha256(payload).hexdigest()
    kind = (
        "html"
        if filename.casefold().endswith(".html")
        else "source_metadata"
        if filename == "SOURCE_INFO.md"
        else "image_analysis"
        if filename == "image_01.json"
        else "video_analysis"
    )
    return {
        "file_id": stable_id("upload", filename, digest),
        "path": filename,
        "kind": kind,
        "size_bytes": len(payload),
        "sha256": digest,
        "preview_kind": "text",
    }


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


def materialize_submission(
    data_root: Path, destination_root: Path, record: dict[str, object]
) -> Path:
    submission_id = str(record["submission_id"])
    submission_type = record.get("submission_type")
    quarantine = data_root / "moderation" / "uploads" / submission_id / "files"
    if submission_type == "html_bundle":
        if not quarantine.is_dir():
            raise RuntimeError("Quarantined HTML bundle is missing")
        target = destination_root / "runtime_scraps" / "html" / submission_id
        shutil.copytree(quarantine, target, dirs_exist_ok=True)
        return target
    if submission_type == "video_json":
        source = quarantine / "video.json"
        if not source.is_file():
            raise RuntimeError("Quarantined video analysis JSON is missing")
        target = destination_root / "runtime_scraps" / "youtube" / f"{submission_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    # Backward compatibility for pending text records created by MGeoAI v0.2.0.
    target = destination_root / "runtime_scraps" / "html" / submission_id
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


def remove_materialized_submission(root: Path, record: dict[str, object]) -> None:
    submission_id = str(record["submission_id"])
    if submission_id.startswith("sub_") and submission_id[4:].isalnum():
        _remove_path(root / "runtime_scraps" / "html" / submission_id)
        _remove_path(root / "runtime_scraps" / "youtube" / f"{submission_id}.json")


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
