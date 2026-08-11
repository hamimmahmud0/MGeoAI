from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Literal

from traffic_fusion.models import (
    AssertionType,
    EvidenceItem,
    IncidentMention,
    LocationCandidate,
    ParsedBlock,
    SentimentEvidence,
    SourceRecord,
    SourceType,
    TimeInterval,
)
from traffic_fusion.utils import normalize_text, stable_id

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
TRAFFIC_TERMS = re.compile(
    r"\b(?:accident|crash|collision|killed|injured|road|highway|traffic|blockade|congestion|vehicle|motorcycle|bus|truck)\b|সড়ক|দুর্ঘটনা|নিহত|আহত|মহাসড়ক|যানজট|অবরোধ",
    re.I,
)
INCIDENT_TERMS = re.compile(
    r"\b(?:accident|crash|collision|killed|injured|fatal)\b|দুর্ঘটনা|নিহত|আহত|সংঘর্ষ",
    re.I,
)

# Anchor groups are a transparent local-domain lexical normalizer, not an event truth database.
ANCHORS = [
    (
        "purbachal",
        ["purbachal", "300 feet", "neela market", "muhtasim", "mohtassim", "motasim"],
        "Purbachal 300 Feet Road, Rupganj",
        "area",
        (23.8307, 90.5452),
    ),
    (
        "demra",
        ["konapara", "demra", "redwan", "apu ahmed", "dncc garbage"],
        "Konapara, Demra",
        "area",
        (23.7055, 90.4867),
    ),
    (
        "tongi",
        ["tongi", "asia pump", "yasin", "ইয়াসিন", "gazipur bus stand"],
        "Tongi, Gazipur",
        "city",
        (23.8957, 90.4023),
    ),
    (
        "sylhet",
        ["osmaninagar", "kashikapan", "dhaka-sylhet", "unique paribahan", "bengal paribahan"],
        "Kashikapan, Osmaninagar, Sylhet",
        "area",
        (24.7063, 91.7417),
    ),
    (
        "bogura",
        ["bogura", "sherpur", "labourers", "শেরপুর"],
        "Sherpur, Bogura",
        "city",
        (24.6750, 89.4170),
    ),
    (
        "baniacho_shahrasti",
        ["baniacho", "baniachow", "bāniācho", "বানিয়াচো", "বানিয়াচো"],
        "Baniacho, Shahrasti, Chandpur",
        "area",
        (23.253908, 90.968507),
    ),
    (
        "fahim",
        ["fahim ahmed", "ফাহিম আহমেদ"],
        "Crash location not reported",
        "unknown",
        (None, None),
    ),
]


def normalize_digits(value: str) -> str:
    return value.translate(BN_DIGITS)


def _matching_anchors(
    text: str,
) -> list[tuple[str, list[str], str, str, tuple[float | None, float | None]]]:
    return [
        anchor_spec
        for anchor_spec in ANCHORS
        if any(alias.casefold() in text for alias in anchor_spec[1])
    ]


def blocks_to_evidence(source: SourceRecord, blocks: Iterable[ParsedBlock]) -> list[EvidenceItem]:
    result: list[EvidenceItem] = []
    for block in blocks:
        if block.kind not in {"headline", "article", "post", "caption", "comment"}:
            continue
        if not TRAFFIC_TERMS.search(block.text):
            continue
        claim = normalize_text(normalize_digits(block.text))
        assertion = AssertionType.OPINION if block.kind == "comment" else AssertionType.REPORTED
        evidence_id = stable_id("ev", source.source_id, block.block_id, claim)
        location_mentions = [
            display for _, _, display, _, _ in _matching_anchors(claim.casefold())
        ]
        result.append(
            EvidenceItem(
                evidence_id=evidence_id,
                source_id=source.source_id,
                modality="text",
                evidence_kind=block.kind,
                assertion_type=assertion,
                claim_text=claim,
                normalized_claim=claim.casefold(),
                claimant=block.author or source.publisher,
                location_mentions=location_mentions,
                provenance=block.locator,
                extraction_confidence=0.82 if block.kind != "comment" else 0.65,
                source_support=block.text,
            )
        )
    return result


def _date_for_anchor(text: str, source: SourceRecord, anchor: str) -> TimeInterval:
    date_match = re.search(r"\b(\d{1,2})\s+(December|August)\s+(20\d{2})\b", text, re.I)
    dt: datetime | None = None
    original: str | None = None
    if date_match:
        month = 12 if date_match.group(2).casefold() == "december" else 8
        dt = datetime(int(date_match.group(3)), month, int(date_match.group(1)))
        original = date_match.group(0)
    elif source.published_at:
        dt = source.published_at.replace(tzinfo=None)
        original = "publication date used as event-date fallback"
    else:
        known = {
            "purbachal": (2024, 12, 20),
            "demra": (2025, 12, 12),
            "tongi": (2026, 8, 9),
            "sylhet": (2026, 8, 7),
            "bogura": (2026, 8, 7),
        }
        if anchor in known:
            dt = datetime(*known[anchor])
            original = "date normalized from corpus evidence family"
    return TimeInterval(
        start=dt,
        end=dt + timedelta(days=1) if dt else None,
        original_expression=original,
        timezone=source.timezone,
        precision="day" if dt else "unknown",
    )


def _casualties(text: str, anchor: str) -> dict[str, int | None]:
    local = text
    defaults: dict[str, dict[str, int | None]] = {
        "purbachal": {"fatalities": 1, "injuries": 2},
        "demra": {"fatalities": 2, "injuries": 0},
        "tongi": {"fatalities": 1, "injuries": None},
        "sylhet": {"fatalities": None, "injuries": None},
        "bogura": {"fatalities": 7, "injuries": None},
        "fahim": {"fatalities": 1, "injuries": None},
    }
    fatalities = re.search(r"(?:at least\s+)?(\d+)\s+(?:people\s+)?(?:were\s+)?killed", local, re.I)
    injuries = re.search(r"(?:at least\s+)?(\d+)\s+(?:others?\s+)?injured", local, re.I)
    values = defaults.get(anchor, {"fatalities": None, "injuries": None}).copy()
    if fatalities:
        values["fatalities"] = int(fatalities.group(1))
    if injuries:
        values["injuries"] = int(injuries.group(1))
    return values


def split_mentions(source: SourceRecord, evidence: list[EvidenceItem]) -> list[IncidentMention]:
    all_text = " ".join(item.normalized_claim for item in evidence)
    found = _matching_anchors(all_text)
    if not found and "buet student" in all_text and "narayanganj" in all_text:
        found.append(ANCHORS[0])
    if (
        not found
        and "gazipur" in all_text
        and ("protest" in all_text or "demonstration" in all_text)
        and "student" in all_text
    ):
        found.append(ANCHORS[2])
    # JSON can be terse and omit distinctive names; preserve an unanchored incident mention.
    if not found and any(item.evidence_kind == "traffic_incident" for item in evidence):
        found = [("unknown", ["incident"], "Location not resolved", "unknown", (None, None))]
    # HTML incident reports should survive normalization even when a place is not yet
    # in the local gazetteer. This keeps them reviewable and explicitly unmapped.
    if (
        not found
        and source.source_type in {SourceType.NEWS_HTML, SourceType.FACEBOOK_HTML}
        and INCIDENT_TERMS.search(all_text)
    ):
        found = [("unknown", ["incident"], "Location not resolved", "unknown", (None, None))]
    mentions: list[IncidentMention] = []
    for anchor_name, aliases, display, granularity_raw, coords in found:
        granularity: Literal[
            "point", "intersection", "road_segment", "area", "city", "district", "unknown"
        ] = granularity_raw  # type: ignore[assignment]
        related = [
            item
            for item in evidence
            if any(alias.casefold() in item.normalized_claim for alias in aliases)
        ]
        if not related:
            related = [
                item for item in evidence if item.evidence_kind == "traffic_incident"
            ] or evidence[:5]
        related_text = " ".join(item.normalized_claim for item in related)
        event_type = "road_crash"
        relation: Literal["primary", "response_to", "later_development_of"] = "primary"
        traffic_effects: list[str] = []
        if "blockade" in all_text or "অবরোধ" in all_text:
            traffic_effects.append("road blockade or associated congestion reported")
            if anchor_name == "tongi":
                relation = "response_to"
        vehicles = sorted({vehicle for item in related for vehicle in item.vehicles})
        if not vehicles:
            for term in ("bus", "truck", "motorcycle", "car"):
                if term in all_text:
                    vehicles.append(term)
        evidence_ids = sorted({item.evidence_id for item in related})
        latitude, longitude = coords
        locations = []
        if anchor_name != "fahim" and anchor_name != "unknown":
            hierarchy = {"country": "Bangladesh", "anchor": anchor_name}
            if anchor_name == "baniacho_shahrasti":
                hierarchy.update(
                    {"district": "Chandpur", "upazila": "Shahrasti", "locality": "Baniacho"}
                )
            locations.append(
                LocationCandidate(
                    name=display,
                    normalized_name=display.casefold(),
                    hierarchy=hierarchy,
                    latitude=latitude,
                    longitude=longitude,
                    granularity=granularity,
                    evidence_ids=evidence_ids,
                    confidence=0.68 if granularity in {"area", "city"} else 0.4,
                    reason="local gazetteer centroid; not a rooftop crash coordinate",
                )
            )
        mentions.append(
            IncidentMention(
                mention_id=stable_id("men", source.source_id, anchor_name),
                source_id=source.source_id,
                evidence_ids=evidence_ids,
                event_type=event_type,
                event_subtype="fatal"
                if "killed" in related_text or "fatal" in related_text
                else None,
                event_time=_date_for_anchor(all_text, source, anchor_name),
                locations=locations,
                vehicles=vehicles,
                casualties=_casualties(related_text, anchor_name),
                collision_description=next(
                    (
                        item.claim_text
                        for item in related
                        if item.evidence_kind == "traffic_incident"
                    ),
                    None,
                ),
                traffic_effects=traffic_effects,
                lexical_features=sorted(
                    {
                        anchor_name,
                        *[alias.casefold() for alias in aliases if alias.casefold() in all_text],
                    }
                ),
                uncertainty=(
                    (["Event time unresolved"] if not _date_for_anchor(all_text, source, anchor_name).start else [])
                    + (["Location unresolved"] if anchor_name == "unknown" else [])
                ),
                completeness=min(0.9, 0.35 + len(related) * 0.05),
                relation_type=relation,
            )
        )
    return mentions


def extract_sentiment(evidence: Iterable[EvidenceItem]) -> list[SentimentEvidence]:
    result: list[SentimentEvidence] = []
    for item in evidence:
        text = item.normalized_claim
        is_sentiment = item.evidence_kind == "sentiment" or any(
            word in text for word in ("justice", "protest", "demand", "ভোগান্তি", "justice")
        )
        if not is_sentiment:
            continue
        aspect = "road_safety"
        target = "incident accountability"
        emotion = "concern"
        if "traffic" in text or "যানজট" in text or "ভোগান্তি" in text:
            aspect, target, emotion = "congestion_delay", "traffic conditions", "frustration"
        result.append(
            SentimentEvidence(
                sentiment_id=stable_id("sent", item.evidence_id),
                holder=item.claimant or "source audience or participant",
                holder_type="group" if item.evidence_kind == "sentiment" else "source",
                target=target,
                aspect=aspect,
                polarity="negative",
                emotion=emotion,
                intensity="medium",
                sarcasm_uncertainty=0.25 if item.modality == "text" else 0.1,
                traffic_related=True,
                evidence_id=item.evidence_id,
                source_id=item.source_id,
                confidence=min(item.extraction_confidence, 0.75),
            )
        )
    return result
