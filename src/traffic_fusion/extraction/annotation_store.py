"""Per-annotator, append-only article labels (blind, latest revision wins)."""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from traffic_fusion.extraction.accounts import USERNAME_RE
from traffic_fusion.extraction.schema import AccidentRecord, ImageLabel


class ArticleLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: str
    annotator: str
    accidents: list[AccidentRecord] = Field(min_length=1, max_length=20)
    images: list[ImageLabel] = Field(default_factory=list, max_length=20)
    unusable: bool = False  # page is not an article (listing, paywall, empty)
    notes: str = Field(default="", max_length=2000)
    submitted_at: str
    revision: int = 1


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ArticleStore:
    """Reads `articles/<id>/` and the label files under one extraction root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.articles_dir = root / "articles"
        self.labels_dir = root / "labels"

    def article_ids(self) -> list[str]:
        if not self.articles_dir.is_dir():
            return []
        return sorted(p.name for p in self.articles_dir.iterdir() if (p / "meta.json").exists())

    def meta(self, article_id: str) -> dict[str, object]:
        return json.loads((self._dir(article_id) / "meta.json").read_text("utf-8"))  # type: ignore[no-any-return]

    def markdown(self, article_id: str) -> str:
        return (self._dir(article_id) / "article.md").read_text("utf-8")

    def _dir(self, article_id: str) -> Path:
        if not article_id.isalnum() or len(article_id) > 40:
            raise ValueError("invalid article id")
        return self.articles_dir / article_id

    @contextmanager
    def _lock(self, name: str) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / f".{name}.lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def _path(self, username: str) -> Path:
        if not USERNAME_RE.match(username):
            raise ValueError("invalid annotator name")
        return self.labels_dir / f"{username}.jsonl"

    def history(self, username: str) -> list[ArticleLabel]:
        path = self._path(username)
        if not path.exists():
            return []
        return [
            ArticleLabel.model_validate_json(line)
            for line in path.read_text("utf-8").splitlines()
            if line.strip()
        ]

    def latest(self, username: str) -> dict[str, ArticleLabel]:
        return {record.article_id: record for record in self.history(username)}

    def append(
        self,
        username: str,
        article_id: str,
        accidents: list[AccidentRecord],
        images: list[ImageLabel],
        unusable: bool,
        notes: str,
    ) -> ArticleLabel:
        path = self._path(username)
        self.labels_dir.mkdir(parents=True, exist_ok=True)
        with self._lock(f"labels-{username}"):
            revision = sum(1 for r in self.history(username) if r.article_id == article_id) + 1
            record = ArticleLabel(
                article_id=article_id,
                annotator=username,
                accidents=accidents,
                images=images,
                unusable=unusable,
                notes=notes,
                submitted_at=_now(),
                revision=revision,
            )
            with path.open("a", encoding="utf-8") as handle:
                handle.write(record.model_dump_json(by_alias=True) + "\n")
        return record

    def annotators(self) -> list[str]:
        if not self.labels_dir.is_dir():
            return []
        return sorted(p.stem for p in self.labels_dir.glob("*.jsonl"))

    def all_latest(self) -> dict[str, dict[str, ArticleLabel]]:
        return {name: self.latest(name) for name in self.annotators()}
