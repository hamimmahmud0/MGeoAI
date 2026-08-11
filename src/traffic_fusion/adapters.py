from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from traffic_fusion.models import (
    AssertionType,
    EvidenceItem,
    ProvenanceLocator,
    SourceRecord,
    SourceType,
)
from traffic_fusion.utils import normalize_text, stable_hash, stable_id

CONFIDENCE = {"low": 0.35, "medium": 0.65, "high": 0.9}


def _confidence(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return CONFIDENCE.get(str(value).casefold(), 0.5)


def _assertion(value: Any, default: AssertionType = AssertionType.REPORTED) -> AssertionType:
    raw = str(value or "").casefold()
    if "direct" in raw or "observ" in raw:
        return AssertionType.OBSERVED
    if "alleg" in raw or "claim" in raw:
        return AssertionType.ATTRIBUTED_CLAIM
    if "opinion" in raw or "sentiment" in raw:
        return AssertionType.OPINION
    if "infer" in raw:
        return AssertionType.INFERRED
    if "predict" in raw or "possible" in raw:
        return AssertionType.PREDICTED
    return default


def _json_source(
    path: Path,
    relative_path: str,
    data: dict[str, Any],
    kind: SourceType,
    parent_source_id: str | None,
) -> SourceRecord:
    raw = path.read_bytes()
    content_hash = stable_hash(raw, 64)
    source_meta = data.get("source", {}) if isinstance(data.get("source"), dict) else {}
    publisher = source_meta.get("platform_or_publisher")
    languages = source_meta.get("source_languages") or []
    raw_title = source_meta.get("primary_topic") or data.get("overall_scene")
    if isinstance(raw_title, dict):
        raw_title = _text(raw_title)
    return SourceRecord(
        source_id=stable_id("src", relative_path, content_hash),
        source_type=kind,
        platform=publisher if kind == SourceType.VIDEO_ANALYSIS else "image",
        publisher=publisher,
        author=source_meta.get("author"),
        local_path=relative_path,
        content_hash=content_hash,
        parent_source_id=parent_source_id,
        languages=[str(item) for item in languages],
        title=str(raw_title) if raw_title else None,
        source_metadata={"adapter": kind.value, "unknown_top_level_fields_preserved": True},
        ingest_warnings=[],
    )


def _items(value: Any, path: str = "$") -> Iterable[tuple[str, dict[str, Any]]]:
    if isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, dict):
                yield f"{path}[{index}]", item


def _text(record: dict[str, Any]) -> str | None:
    for key in (
        "claim",
        "observation",
        "description",
        "inference",
        "event",
        "condition",
        "original_text",
        "normalized_text",
        "traffic_relevance",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_text(value)
    return None


def _evidence(
    source: SourceRecord,
    modality: Literal["text", "image", "video", "audio"],
    json_path: str,
    kind: str,
    record: dict[str, Any],
) -> EvidenceItem | None:
    claim = _text(record)
    if not claim:
        # Incident objects may not have a prose claim; create a compact faithful representation.
        if kind == "traffic_incident":
            bits = [
                str(record.get(key))
                for key in ("incident_type", "location", "date")
                if record.get(key)
            ]
            if record.get("fatalities") is not None:
                bits.append(f"fatalities={record['fatalities']}")
            if record.get("injuries") is not None:
                bits.append(f"injuries={record['injuries']}")
            claim = "; ".join(bits)
    if not claim:
        return None
    confidence_value = record.get("confidence_in_extraction", record.get("confidence"))
    evidence_id = stable_id("ev", source.source_id, json_path, claim)
    locations: list[str] = []
    if isinstance(record.get("location"), str):
        locations.append(record["location"])
    vehicles = []
    for vehicle in record.get("vehicles", []) if isinstance(record.get("vehicles"), list) else []:
        if isinstance(vehicle, dict) and vehicle.get("vehicle_type"):
            vehicles.append(str(vehicle["vehicle_type"]))
    road_users = []
    for road_user in (
        record.get("road_users", []) if isinstance(record.get("road_users"), list) else []
    ):
        if isinstance(road_user, dict) and road_user.get("type"):
            road_users.append(str(road_user["type"]))
    casualties = {key: record.get(key) for key in ("fatalities", "injuries") if key in record}
    default_assertion = {
        "inference": AssertionType.INFERRED,
        "predicted_impact": AssertionType.PREDICTED,
        "sentiment": AssertionType.OPINION,
        "visual_observation": AssertionType.OBSERVED,
    }.get(kind, AssertionType.REPORTED)
    return EvidenceItem(
        evidence_id=evidence_id,
        source_id=source.source_id,
        modality=modality,
        evidence_kind=kind,
        assertion_type=_assertion(
            record.get("evidence_type") or record.get("observation_type"), default_assertion
        ),
        claim_text=claim,
        normalized_claim=normalize_text(claim).casefold(),
        claimant=record.get("claimant"),
        claimant_role=record.get("claimant_role"),
        vehicles=vehicles,
        road_users=road_users,
        casualty_quantities=casualties,
        location_mentions=locations,
        provenance=ProvenanceLocator(
            source_path=source.local_path,
            locator_type="json_path",
            locator=json_path,
            original_text=record.get("supporting_text") or claim,
        ),
        extraction_confidence=_confidence(confidence_value),
        source_support=record.get("supporting_text"),
        warnings=[],
        extensions={"raw_fields": record},
    )


def adapt_video(path: Path, relative_path: str) -> tuple[SourceRecord, list[EvidenceItem]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("video analysis root must be an object")
    source = _json_source(path, relative_path, data, SourceType.VIDEO_ANALYSIS, None)
    evidence: list[EvidenceItem] = []
    sections = {
        "claims": "claim",
        "traffic_incidents": "traffic_incident",
        "traffic_conditions": "traffic_condition",
        "traffic_affecting_events": "traffic_event",
        "locations": "location",
        "predicted_or_possible_impacts": "predicted_impact",
    }
    for section, kind in sections.items():
        for json_path, record in _items(data.get(section), f"$.{section}"):
            item = _evidence(source, "video", json_path, kind, record)
            if item:
                evidence.append(item)
    sentiment = data.get("sentiment_analysis", {})
    for json_path, record in _items(
        sentiment.get("aspect_sentiments") if isinstance(sentiment, dict) else None,
        "$.sentiment_analysis.aspect_sentiments",
    ):
        record = {
            **record,
            "evidence_type": "opinion",
            "description": record.get("evidence_text") or record.get("aspect"),
        }
        item = _evidence(source, "video", json_path, "sentiment", record)
        if item:
            evidence.append(item)
    return source, evidence


def adapt_image(
    path: Path, relative_path: str, parent_source_id: str | None = None
) -> tuple[SourceRecord, list[EvidenceItem]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("image analysis root must be an object")
    source = _json_source(path, relative_path, data, SourceType.IMAGE_ANALYSIS, parent_source_id)
    evidence: list[EvidenceItem] = []
    sections = {
        "observations": "visual_observation",
        "textual_claims": "textual_claim",
        "inferences": "inference",
        "traffic_incidents": "traffic_incident",
        "traffic_conditions": "traffic_condition",
        "traffic_affecting_events": "traffic_event",
        "visible_text": "visible_text",
    }
    for section, kind in sections.items():
        for json_path, record in _items(data.get(section), f"$.{section}"):
            item = _evidence(source, "image", json_path, kind, record)
            if item:
                evidence.append(item)
    location = data.get("location_evidence")
    if isinstance(location, dict):
        names = [
            location.get(key)
            for key in ("area", "city", "district", "country")
            if location.get(key)
        ]
        if names:
            record = {
                "description": ", ".join(str(x) for x in names),
                "location": str(names[0]),
                "confidence": location.get("confidence"),
                **location,
            }
            item = _evidence(source, "image", "$.location_evidence", "location", record)
            if item:
                item.location_mentions = [str(x) for x in names]
                evidence.append(item)
    sentiment = data.get("sentiment_analysis", {})
    for json_path, record in _items(
        sentiment.get("sentiment_expressions") if isinstance(sentiment, dict) else None,
        "$.sentiment_analysis.sentiment_expressions",
    ):
        record = {
            **record,
            "evidence_type": "opinion",
            "description": record.get("evidence_text") or record.get("aspect"),
        }
        item = _evidence(source, "image", json_path, "sentiment", record)
        if item:
            evidence.append(item)
    return source, evidence
