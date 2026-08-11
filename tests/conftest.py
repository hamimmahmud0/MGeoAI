from __future__ import annotations

from pathlib import Path

import pytest

from traffic_fusion.models import (
    EvidenceItem,
    IncidentMention,
    ProvenanceLocator,
    SourceRecord,
    SourceType,
)


@pytest.fixture
def source() -> SourceRecord:
    return SourceRecord(
        source_id="src_test",
        source_type=SourceType.NEWS_HTML,
        local_path="sample.html",
        content_hash="a" * 64,
        publisher="Fixture News",
        independence="original",
    )


@pytest.fixture
def evidence(source: SourceRecord) -> EvidenceItem:
    return EvidenceItem(
        evidence_id="ev_test",
        source_id=source.source_id,
        modality="text",
        evidence_kind="article",
        assertion_type="reported",
        claim_text="One person was killed in a crash in Tongi.",
        normalized_claim="one person was killed in a crash in tongi.",
        provenance=ProvenanceLocator(
            source_path="sample.html",
            locator_type="html_selector",
            locator="article > p",
            block_id="blk_test",
            original_text="One person was killed in a crash in Tongi.",
        ),
        extraction_confidence=0.9,
    )


@pytest.fixture
def mention(source: SourceRecord, evidence: EvidenceItem) -> IncidentMention:
    from traffic_fusion.normalize import split_mentions

    return split_mentions(source, [evidence])[0]


@pytest.fixture
def root() -> Path:
    return Path(__file__).parents[1]
