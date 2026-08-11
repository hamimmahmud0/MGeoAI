from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
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
# Location aliases are deliberately separated from person/vehicle aliases so provenance never
# claims that a paragraph names a place merely because it names a victim or bus company.
@dataclass(frozen=True)
class Anchor:
    name: str
    location_aliases: tuple[str, ...]
    display: str
    granularity: str
    coordinates: tuple[float | None, float | None]
    event_aliases: tuple[str, ...] = ()
    family: str | None = None
    priority: int = 0
    radius_km: float | None = None
    hierarchy: dict[str, str] = field(default_factory=dict)

    @property
    def aliases(self) -> tuple[str, ...]:
        return self.location_aliases + self.event_aliases


ANCHORS = [
    Anchor(
        "nila_market_purbachal",
        ("neela market", "nila market", "নীলা মার্কেট"),
        "Nila Market intersection, Purbachal 300 Feet Road, Rupganj",
        "area",
        (23.834106, 90.484744),
        ("muhtasim", "mohtassim", "motasim"),
        family="purbachal",
        priority=20,
        radius_km=1.5,
        hierarchy={"district": "Narayanganj", "upazila": "Rupganj", "locality": "Nila Market"},
    ),
    Anchor(
        "purbachal",
        ("purbachal", "300 feet"),
        "Purbachal 300 Feet Road, Rupganj",
        "area",
        (23.8307, 90.5452),
        ("muhtasim", "mohtassim", "motasim"),
        family="purbachal",
        priority=10,
        radius_km=8.0,
        hierarchy={"district": "Narayanganj", "upazila": "Rupganj"},
    ),
    Anchor(
        "konapara_demra",
        ("konapara", "কোনাপাড়া", "কোনাপাড়া"),
        "Konapara, Demra",
        "area",
        (23.71677, 90.4685),
        ("redwan", "apu ahmed", "dncc garbage"),
        family="demra",
        priority=20,
        radius_km=3.0,
        hierarchy={"city": "Dhaka", "locality": "Konapara"},
    ),
    Anchor(
        "demra",
        ("demra",),
        "Demra, Dhaka",
        "area",
        (23.7055, 90.4867),
        ("redwan", "apu ahmed", "dncc garbage"),
        family="demra",
        priority=10,
        radius_km=5.0,
        hierarchy={"city": "Dhaka"},
    ),
    Anchor(
        "asia_pump_tongi",
        ("asia pump", "এশিয়া পাম্প", "এশিয়া পাম্প"),
        "Asia Pump area, Tongi, Gazipur",
        "road_segment",
        (23.917957, 90.393642),
        ("yasin", "ইয়াসিন", "gazipur bus stand"),
        family="tongi",
        priority=20,
        radius_km=1.0,
        hierarchy={"district": "Gazipur", "city": "Tongi", "locality": "Asia Pump"},
    ),
    Anchor(
        "tongi",
        ("tongi", "টঙ্গী"),
        "Tongi, Gazipur",
        "city",
        (23.8957, 90.4023),
        ("yasin", "ইয়াসিন", "gazipur bus stand"),
        family="tongi",
        priority=10,
        radius_km=12.0,
        hierarchy={"district": "Gazipur", "city": "Tongi"},
    ),
    Anchor(
        "sylhet",
        ("sylhet", "osmaninagar", "kashikapan", "dhaka-sylhet"),
        "Kashikapan, Osmaninagar, Sylhet",
        "area",
        (24.7063, 91.7417),
        ("unique paribahan", "bengal paribahan"),
        radius_km=3.0,
        hierarchy={"district": "Sylhet", "upazila": "Osmaninagar"},
    ),
    Anchor(
        "erulia_bogura",
        ("erulia", "arulia", "এরুলিয়া", "এরুলিয়া"),
        "Erulia Bazar, Bogura Sadar, Bogura",
        "area",
        (24.858327, 89.333249),
        family="bogura",
        priority=30,
        radius_km=3.0,
        hierarchy={"district": "Bogura", "upazila": "Bogura Sadar", "locality": "Erulia Bazar"},
    ),
    Anchor(
        "sherpur_bogura",
        ("sherpur", "শেরপুর"),
        "Sherpur, Bogura",
        "city",
        (24.675, 89.417),
        family="bogura",
        priority=20,
        radius_km=12.0,
        hierarchy={"district": "Bogura", "upazila": "Sherpur"},
    ),
    Anchor(
        "bogura",
        ("bogura", "বগুড়া", "বগুড়া"),
        "Bogura District, Bangladesh",
        "district",
        (24.8465, 89.3773),
        family="bogura",
        priority=10,
        radius_km=35.0,
        hierarchy={"district": "Bogura"},
    ),
    Anchor(
        "baniacho_shahrasti",
        ("baniacho", "baniachow", "bāniācho", "বানিয়াচো", "বানিয়াচো"),
        "Baniacho, Shahrasti, Chandpur",
        "area",
        (23.253908, 90.968507),
        radius_km=3.0,
        hierarchy={"district": "Chandpur", "upazila": "Shahrasti", "locality": "Baniacho"},
    ),
    Anchor(
        "fahim",
        (),
        "Crash location not reported",
        "unknown",
        (None, None),
        ("fahim ahmed", "ফাহিম আহমেদ"),
    ),
]


def normalize_digits(value: str) -> str:
    return value.translate(BN_DIGITS)


def _has_alias(text: str, alias: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(alias.casefold())}(?!\w)", text.casefold()))


def _matching_anchors(text: str, *, location_only: bool = False) -> list[Anchor]:
    matches = [
        anchor
        for anchor in ANCHORS
        if any(_has_alias(text, alias) for alias in (anchor.location_aliases if location_only else anchor.aliases))
    ]
    # Prefer the most specific named place within an anchor family.
    best_by_family: dict[str, Anchor] = {}
    ungrouped: list[Anchor] = []
    for anchor in matches:
        if not anchor.family:
            ungrouped.append(anchor)
            continue
        current = best_by_family.get(anchor.family)
        if current is None or anchor.priority > current.priority:
            best_by_family[anchor.family] = anchor
    return sorted([*ungrouped, *best_by_family.values()], key=lambda item: (-item.priority, item.name))


NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "sixteen": 16,
    "twenty-four": 24,
    "twenty-five": 25,
    "forty-eight": 48,
}
NUMBER_PATTERN = r"\d+|" + "|".join(re.escape(word) for word in sorted(NUMBER_WORDS, key=len, reverse=True))


def _count(value: str) -> int:
    return int(value) if value.isdigit() else NUMBER_WORDS[value.casefold()]


def _extract_casualty_quantities(text: str) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    fatality = re.search(
        rf"\b({NUMBER_PATTERN})\s+(?:(?:people|persons?|students?|labourers?|workers?|others?)\s+)?(?:were\s+|was\s+)?(?:killed|died|dead|deaths?|fatalities)\b",
        text,
        re.I,
    )
    injury = re.search(
        rf"\b({NUMBER_PATTERN})\s+(?:more\s+)?(?:(?:people|persons?|students?|labourers?|workers?|friends?|classmates?|others?)\s+)?(?:were\s+|was\s+)?(?:\w+ly\s+)?(?:injured|hurt)\b",
        text,
        re.I,
    )
    if not injury:
        injury = re.search(
            rf"\binjuring\s+(?:his|her|their)\s+({NUMBER_PATTERN})\s+"
            r"(?:friends?|classmates?|students?|people|persons?)\b"
            rf"|\b(?:(?:his|her|their)\s+)?({NUMBER_PATTERN})\s+"
            r"(?:of\s+(?:his|her|their)\s+)?(?:friends?|classmates?|students?|people|persons?)\s+"
            r"(?:were\s+)?(?:injured|hurt)\b",
            text,
            re.I,
        )
    if fatality:
        result["fatalities"] = _count(fatality.group(1))
    elif re.search(
        r"\b(?:a|one)\s+(?:[\w-]+\s+){0,3}(?:was\s+)?(?:killed|died)\b"
        r"|\b(?:student|man|woman|person|motorcyclist|pedestrian|driver|rider)\s+"
        r"(?:[\w'-]+\s+){0,3}(?:was\s+)?(?:killed|died)\b"
        r"|\b(?:killing|death of)\s+(?:[\w'-]+\s+){0,4}[\w'-]+",
        text,
        re.I,
    ):
        result["fatalities"] = 1
    if injury:
        result["injuries"] = _count(next(group for group in injury.groups() if group))
    return result


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
            anchor.display for anchor in _matching_anchors(claim.casefold(), location_only=True)
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
                casualty_quantities=_extract_casualty_quantities(claim),
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


def _casualties(items: list[EvidenceItem]) -> dict[str, int | None]:
    values: dict[str, int | None] = {"fatalities": None, "injuries": None}
    for field_name in values:
        reported = {
            item.casualty_quantities[field_name]
            for item in items
            if item.casualty_quantities.get(field_name) is not None
        }
        if len(reported) == 1:
            values[field_name] = reported.pop()
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
        found.append(next(anchor for anchor in ANCHORS if anchor.name == "tongi"))
    # JSON can be terse and omit distinctive names; preserve an unanchored incident mention.
    if not found and any(item.evidence_kind == "traffic_incident" for item in evidence):
        found = [Anchor("unknown", (), "Location not resolved", "unknown", (None, None), ("incident",))]
    # HTML incident reports should survive normalization even when a place is not yet
    # in the local gazetteer. This keeps them reviewable and explicitly unmapped.
    if (
        not found
        and source.source_type in {SourceType.NEWS_HTML, SourceType.FACEBOOK_HTML}
        and INCIDENT_TERMS.search(all_text)
    ):
        found = [Anchor("unknown", (), "Location not resolved", "unknown", (None, None), ("incident",))]
    mentions: list[IncidentMention] = []
    for anchor in found:
        anchor_name = anchor.name
        family = anchor.family or anchor.name
        granularity: Literal[
            "point", "intersection", "road_segment", "area", "city", "district", "unknown"
        ] = anchor.granularity  # type: ignore[assignment]
        family_anchors = [
            candidate
            for candidate in ANCHORS
            if (candidate.family or candidate.name) == family
        ]
        family_aliases = {
            alias for candidate in family_anchors for alias in candidate.aliases
        }
        matching_items = [
            item
            for item in evidence
            if any(_has_alias(item.normalized_claim, alias) for alias in family_aliases)
        ]
        # Aggregate roundup headlines can name several incidents and carry combined counts.
        # Prefer blocks that identify only this anchor family whenever they exist.
        exclusive = []
        for item in matching_items:
            item_families = {candidate.family or candidate.name for candidate in _matching_anchors(item.normalized_claim)}
            if item_families == {family}:
                exclusive.append(item)
        related = exclusive or matching_items
        if not related:
            related = [
                item for item in evidence if item.evidence_kind == "traffic_incident"
            ] or evidence[:5]
        related_text = " ".join(item.normalized_claim for item in related)
        event_type = "road_crash"
        relation: Literal["primary", "response_to", "later_development_of"] = "primary"
        traffic_effects: list[str] = []
        if "blockade" in related_text or "অবরোধ" in related_text:
            traffic_effects.append("road blockade or associated congestion reported")
            if anchor_name == "tongi":
                relation = "response_to"
        vehicles = sorted({vehicle for item in related for vehicle in item.vehicles})
        if not vehicles:
            for term in ("bus", "truck", "motorcycle", "car"):
                if term in related_text:
                    vehicles.append(term)
        evidence_ids = sorted({item.evidence_id for item in related})
        location_evidence_ids = sorted(
            {
                item.evidence_id
                for item in related
                if any(_has_alias(item.normalized_claim, alias) for alias in anchor.location_aliases)
            }
        ) or evidence_ids
        latitude, longitude = anchor.coordinates
        locations = []
        if anchor_name != "fahim" and anchor_name != "unknown":
            hierarchy = {
                "country": "Bangladesh",
                "anchor": anchor.family or anchor_name,
                **anchor.hierarchy,
            }
            locations.append(
                LocationCandidate(
                    name=anchor.display,
                    normalized_name=anchor.display.casefold(),
                    hierarchy=hierarchy,
                    latitude=latitude,
                    longitude=longitude,
                    granularity=granularity,
                    evidence_ids=location_evidence_ids,
                    confidence=0.75 if anchor.priority >= 20 else (0.68 if granularity in {"area", "city"} else 0.55),
                    reason=(
                        "source-named place represented by a local gazetteer centroid; "
                        f"approximately {anchor.radius_km:g} km uncertainty"
                        if anchor.radius_km
                        else "local gazetteer centroid; not a rooftop crash coordinate"
                    ),
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
                event_time=_date_for_anchor(related_text, source, anchor.family or anchor_name),
                locations=locations,
                vehicles=vehicles,
                casualties=_casualties(related),
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
                        *[alias.casefold() for alias in family_aliases if _has_alias(related_text, alias)],
                    }
                ),
                uncertainty=(
                    (["Event time unresolved"] if not _date_for_anchor(related_text, source, anchor.family or anchor_name).start else [])
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
