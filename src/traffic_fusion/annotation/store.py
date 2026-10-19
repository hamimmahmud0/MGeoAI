from __future__ import annotations

import fcntl
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Label = Literal["same_incident", "related_distinct", "different", "cannot_tell"]
LABELS: tuple[str, ...] = ("same_incident", "related_distinct", "different", "cannot_tell")
USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class ArticleView(BaseModel):
    """What an annotator may see about one report. No pipeline or selection data."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    publisher: str | None = None
    url: str | None = None
    published_at: str | None = None
    text: str


class AnnotationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    left: ArticleView
    right: ArticleView


class LabelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    annotator: str
    label: Label
    notes: str = Field(default="", max_length=2000)
    submitted_at: str
    revision: int = 1


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class AnnotationStore:
    """File-backed store: served items, admin-only metadata, per-annotator labels.

    Authentication is the reviewer login in `traffic_fusion.api.moderation`.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.items_path = root / "items.json"
        self.meta_path = root / "admin_meta.json"  # never served over HTTP
        self.labels_dir = root / "labels"

    @contextmanager
    def _lock(self, name: str) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / f".{name}.lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    # items -----------------------------------------------------------------
    def items(self) -> list[AnnotationItem]:
        try:
            raw = json.loads(self.items_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [AnnotationItem.model_validate(item) for item in raw]

    # labels ----------------------------------------------------------------
    def _label_path(self, username: str) -> Path:
        if not USERNAME_RE.match(username):
            raise ValueError("invalid annotator name")
        return self.labels_dir / f"{username}.jsonl"

    def history(self, username: str) -> list[LabelRecord]:
        path = self._label_path(username)
        if not path.exists():
            return []
        return [
            LabelRecord.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def latest(self, username: str) -> dict[str, LabelRecord]:
        return {record.item_id: record for record in self.history(username)}

    def append_label(self, username: str, item_id: str, label: Label, notes: str) -> LabelRecord:
        path = self._label_path(username)
        self.labels_dir.mkdir(parents=True, exist_ok=True)
        with self._lock(f"labels-{username}"):
            revision = sum(1 for r in self.history(username) if r.item_id == item_id) + 1
            record = LabelRecord(
                item_id=item_id,
                annotator=username,
                label=label,
                notes=notes,
                submitted_at=_now(),
                revision=revision,
            )
            with path.open("a", encoding="utf-8") as handle:
                handle.write(record.model_dump_json() + "\n")
        return record

    def annotators(self) -> list[str]:
        if not self.labels_dir.is_dir():
            return []
        return sorted(path.stem for path in self.labels_dir.glob("*.jsonl"))

    def all_latest(self) -> dict[str, dict[str, LabelRecord]]:
        return {name: self.latest(name) for name in self.annotators()}
