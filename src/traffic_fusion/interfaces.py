from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from traffic_fusion.models import EvidenceItem, LocationCandidate, SourceRecord


class AnalysisProvider(Protocol):
    """Extension point for future raw text/image/audio/video model analysis."""

    name: str

    def analyze(self, path: Path, source: SourceRecord) -> Sequence[EvidenceItem]: ...


class Geocoder(Protocol):
    """Provider-neutral location candidate resolver."""

    name: str
    attribution: str | None

    def resolve(self, query: str) -> Sequence[LocationCandidate]: ...


class SentimentClassifier(Protocol):
    """Optional future classifier; deterministic adapters remain the MVP path."""

    name: str

    def classify(self, evidence: EvidenceItem) -> dict[str, object]: ...
