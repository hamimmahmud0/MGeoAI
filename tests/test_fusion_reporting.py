from __future__ import annotations

from traffic_fusion.fusion.recorded import RecordedFusionProvider
from traffic_fusion.models import (
    IncidentMention,
    LocationCandidate,
    SentimentEvidence,
    SourceRecord,
    SourceType,
    TimeInterval,
)
from traffic_fusion.reporting import (
    incident_to_geojson,
    render_incident_markdown,
    validate_fused_provenance,
)


def bundle() -> dict:
    location = LocationCandidate(
        name="Tongi, Gazipur",
        normalized_name="tongi, gazipur",
        hierarchy={"country": "Bangladesh", "anchor": "tongi"},
        latitude=23.8,
        longitude=90.4,
        granularity="city",
        evidence_ids=["ev_a", "ev_b"],
        confidence=0.7,
    )
    mentions = [
        IncidentMention(
            mention_id="m_a",
            source_id="s_a",
            evidence_ids=["ev_a"],
            event_type="road_crash",
            event_time=TimeInterval(
                start="2026-08-09T00:00:00", end="2026-08-10T00:00:00", precision="day"
            ),
            locations=[location],
            casualties={"fatalities": 1, "injuries": 0},
        ),
        IncidentMention(
            mention_id="m_b",
            source_id="s_b",
            evidence_ids=["ev_b"],
            event_type="road_crash",
            event_time=TimeInterval(
                start="2026-08-09T00:00:00", end="2026-08-10T00:00:00", precision="day"
            ),
            locations=[location],
            casualties={"fatalities": 2, "injuries": None},
        ),
    ]
    sources = [
        SourceRecord(
            source_id="s_a",
            source_type=SourceType.NEWS_HTML,
            local_path="a",
            content_hash="a" * 64,
            dependency_group="wire",
            independence="syndicated",
        ),
        SourceRecord(
            source_id="s_b",
            source_type=SourceType.NEWS_HTML,
            local_path="b",
            content_hash="b" * 64,
            dependency_group="wire",
            independence="syndicated",
        ),
    ]
    sentiment = [
        SentimentEvidence(
            sentiment_id="sent",
            holder="traveller",
            holder_type="person",
            target="traffic conditions",
            aspect="congestion_delay",
            polarity="negative",
            emotion="frustration",
            intensity="medium",
            traffic_related=True,
            evidence_id="ev_a",
            source_id="s_a",
            confidence=0.8,
        )
    ]
    return {
        "mentions": [x.model_dump(mode="json") for x in mentions],
        "sources": [x.model_dump(mode="json") for x in sources],
        "sentiment": [x.model_dump(mode="json") for x in sentiment],
        "evidence": [],
        "relevant_markdown_blocks": [],
    }


def test_recorded_fusion_retains_conflict_and_dependency() -> None:
    incident = RecordedFusionProvider().fuse("cluster", bundle())
    fatality = next(fact for fact in incident.facts if fact.field == "fatalities")
    assert fatality.contradiction is True
    assert fatality.conflicting_values
    assert incident.independent_source_count == 1
    assert len(incident.duplicate_groups) == 1


def test_geojson_uses_longitude_latitude_order() -> None:
    incident = RecordedFusionProvider().fuse("cluster", bundle())
    feature = incident_to_geojson(incident)
    assert feature is not None
    assert feature["geometry"]["coordinates"] == [90.4, 23.8]
    assert feature["properties"]["granularity"] == "city"


def test_renderer_is_deterministic_and_cites_evidence() -> None:
    incident = RecordedFusionProvider().fuse("cluster", bundle())
    assert render_incident_markdown(incident) == render_incident_markdown(incident)
    assert "[ev_a]" in render_incident_markdown(incident)


def test_recorded_fusion_writes_an_informative_summary() -> None:
    incident = RecordedFusionProvider().fuse("cluster", bundle())
    assert len(incident.human_summary) >= 500
    assert "independent source group" in incident.human_summary
    assert "location" in incident.human_summary.lower()
    assert "traffic" in incident.human_summary.lower()
    assert "[ev_a]" in incident.human_summary


def test_provenance_validator_rejects_unknown_id() -> None:
    incident = RecordedFusionProvider().fuse("cluster", bundle())
    incident.evidence_ids.append("invented")
    errors = validate_fused_provenance(incident, {"ev_a", "ev_b"}, {"s_a", "s_b"})
    assert "invented" in errors[0]


def test_sentiment_is_aspect_based_and_reaction_free() -> None:
    incident = RecordedFusionProvider().fuse("cluster", bundle())
    assert incident.sentiment.by_aspect == {"congestion_delay": {"negative": 1}}
    assert "reaction counts excluded" in incident.sentiment.coverage_note
