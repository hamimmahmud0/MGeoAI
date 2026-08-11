from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from traffic_fusion.corpus.models import (
    CorpusCountry,
    CorpusIncident,
    CorpusLock,
    CorpusManifest,
    CorpusSource,
    LockEntry,
    ReviewEvent,
)

T = TypeVar("T", bound=BaseModel)


class CorpusStore:
    """Read a canonical corpus without mutating its source artifacts."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def manifest(self) -> CorpusManifest:
        return self._model(self.root / "corpus.json", CorpusManifest)

    def countries(self) -> list[CorpusCountry]:
        return [
            self._model(path, CorpusCountry)
            for path in sorted((self.root / "countries").glob("*/country.json"))
        ]

    def sources(self) -> list[CorpusSource]:
        return [
            self._model(path, CorpusSource)
            for path in sorted((self.root / "sources").glob("*/source.json"))
        ]

    def incidents(self) -> list[CorpusIncident]:
        return [
            self._model(path, CorpusIncident)
            for path in sorted((self.root / "incidents").glob("*.json"))
        ]

    def reviews(self) -> list[ReviewEvent]:
        events: list[ReviewEvent] = []
        for path in sorted((self.root / "reviews").glob("*.jsonl")):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    events.append(ReviewEvent.model_validate_json(line))
                except ValueError as exc:
                    raise ValueError(f"{path}:{line_number}: {exc}") from exc
        return events

    def source_directory(self, source: CorpusSource) -> Path:
        return self.root / "sources" / source.corpus_source_id

    def artifact_path(self, source: CorpusSource, relative_path: str) -> Path:
        source_root = self.source_directory(source).resolve()
        candidate = source_root / relative_path
        if candidate.is_symlink():
            raise ValueError(f"artifact must not be a symbolic link: {relative_path}")
        target = candidate.resolve()
        if target != source_root and source_root not in target.parents:
            raise ValueError(f"artifact escapes source directory: {relative_path}")
        return target

    def build_lock(self) -> CorpusLock:
        manifest = self.manifest()
        entries: list[LockEntry] = []
        lock_root = self.root / "locks"
        for path in sorted(
            item for item in self.root.rglob("*") if item.is_file() and not item.is_symlink()
        ):
            if lock_root in path.parents:
                continue
            content = path.read_bytes()
            entries.append(
                LockEntry(
                    path=path.relative_to(self.root).as_posix(),
                    sha256=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                )
            )
        return CorpusLock(corpus_id=manifest.corpus_id, entries=entries)

    @staticmethod
    def _model(path: Path, model: type[T]) -> T:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read corpus record {path}: {exc}") from exc
        return model.model_validate(data)
