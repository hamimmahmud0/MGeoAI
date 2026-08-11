from __future__ import annotations

from traffic_fusion.config import Settings
from traffic_fusion.matching import build_clusters, score_pair
from traffic_fusion.models import (
    EvidenceItem,
    IncidentMention,
    MatchDecision,
    ProvenanceLocator,
    SourceRecord,
    SourceType,
    TimeInterval,
)
from traffic_fusion.normalize import normalize_digits, split_mentions


def make_evidence(source_id: str, text: str, suffix: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"ev_{suffix}",
        source_id=source_id,
        modality="text",
        evidence_kind="article",
        assertion_type="reported",
        claim_text=text,
        normalized_claim=text.casefold(),
        provenance=ProvenanceLocator(
            source_path="fixture.html", locator_type="source", locator="$"
        ),
        extraction_confidence=0.8,
    )


def test_bangla_digits_normalize() -> None:
    assert normalize_digits("১৫ কিলোমিটার") == "15 কিলোমিটার"


def test_one_source_splits_sylhet_and_bogura() -> None:
    source = SourceRecord(
        source_id="src_roundup",
        source_type=SourceType.NEWS_HTML,
        local_path="roundup.html",
        content_hash="b" * 64,
    )
    evidence = [
        make_evidence(
            source.source_id,
            "Nine killed when Unique Paribahan and Bengal Paribahan buses collided at Kashikapan in Osmaninagar, Sylhet. Seven labourers were killed by a bus in Sherpur, Bogura.",
            "roundup",
        )
    ]
    mentions = split_mentions(source, evidence)
    assert {item.locations[0].hierarchy["anchor"] for item in mentions} == {"sylhet", "bogura"}


def test_bangla_baniacho_report_resolves_area_centroid() -> None:
    source = SourceRecord(
        source_id="src_baniacho",
        source_type=SourceType.NEWS_HTML,
        local_path="content.html",
        content_hash="c" * 64,
    )
    evidence = [
        make_evidence(
            source.source_id,
            "চাঁদপুরের শাহরাস্তি উপজেলার বানিয়াচো এলাকায় বাস-ট্রাক সংঘর্ষে তিনজন নিহত।",
            "baniacho",
        )
    ]

    mention = split_mentions(source, evidence)[0]

    location = mention.locations[0]
    assert location.name == "Baniacho, Shahrasti, Chandpur"
    assert location.hierarchy == {
        "country": "Bangladesh",
        "anchor": "baniacho_shahrasti",
        "district": "Chandpur",
        "upazila": "Shahrasti",
        "locality": "Baniacho",
    }
    assert (location.latitude, location.longitude) == (23.253908, 90.968507)
    assert location.granularity == "area"


def test_unrecognized_html_incident_remains_reviewable_and_unmapped() -> None:
    source = SourceRecord(
        source_id="src_unknown_html",
        source_type=SourceType.NEWS_HTML,
        local_path="unknown.html",
        content_hash="d" * 64,
    )

    mention = split_mentions(
        source,
        [make_evidence(source.source_id, "A collision killed one person near an unnamed road.", "unknown")],
    )[0]

    assert mention.locations == []
    assert "Location unresolved" in mention.uncertainty


def test_different_specific_locations_trigger_hard_guard() -> None:
    source_a = SourceRecord(
        source_id="a", source_type=SourceType.NEWS_HTML, local_path="a", content_hash="a" * 64
    )
    source_b = SourceRecord(
        source_id="b", source_type=SourceType.NEWS_HTML, local_path="b", content_hash="b" * 64
    )
    left = split_mentions(
        source_a,
        [make_evidence("a", "Crash at Purbachal Neela Market killed a BUET student.", "a")],
    )[0]
    right = split_mentions(
        source_b,
        [make_evidence("b", "DNCC garbage truck crash at Konapara, Demra killed Redwan.", "b")],
    )[0]
    features = score_pair(left, right, Settings())
    assert features.hard_guard == "specific normalized locations conflict"
    assert features.total_score == 0


def test_cannot_link_blocks_transitive_cluster() -> None:
    def mention(mid: str) -> IncidentMention:
        return IncidentMention(
            mention_id=mid,
            source_id=f"src_{mid}",
            evidence_ids=[f"ev_{mid}"],
            event_type="road_crash",
        )

    mentions = [mention("a"), mention("b"), mention("c")]
    from traffic_fusion.models import MatchFeatures

    features = MatchFeatures(
        time_score=1,
        location_score=1,
        entity_score=0,
        vehicle_score=0,
        lexical_score=1,
        total_score=0.9,
    )
    decisions = [
        MatchDecision(
            left_mention_id="a",
            right_mention_id="b",
            decision="same_incident",
            confidence=0.9,
            rationale="same",
            features=features,
        ),
        MatchDecision(
            left_mention_id="b",
            right_mention_id="c",
            decision="same_incident",
            confidence=0.8,
            rationale="same",
            features=features,
        ),
        MatchDecision(
            left_mention_id="a",
            right_mention_id="c",
            decision="different_incident",
            confidence=1,
            rationale="conflict",
            features=features,
        ),
    ]
    clusters = build_clusters(mentions, decisions)
    assert sorted(map(len, clusters)) == [1, 2]


def test_relative_time_without_reference_remains_unknown() -> None:
    mention = IncidentMention(
        mention_id="m",
        source_id="s",
        evidence_ids=["e"],
        event_type="crash",
        event_time=TimeInterval(original_expression="yesterday", precision="unknown"),
    )
    assert mention.event_time.start is None
    assert mention.event_time.timezone is None
