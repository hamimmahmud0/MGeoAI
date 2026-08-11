from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceType(StrEnum):
    NEWS_HTML = "news_html"
    FACEBOOK_HTML = "facebook_html"
    VIDEO_ANALYSIS = "video_analysis"
    IMAGE_ANALYSIS = "image_analysis"


class AssertionType(StrEnum):
    OBSERVED = "observed"
    REPORTED = "reported"
    ATTRIBUTED_CLAIM = "attributed_claim"
    OPINION = "opinion"
    INFERRED = "inferred"
    PREDICTED = "predicted"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProvenanceLocator(StrictModel):
    source_path: str
    locator_type: Literal["html_selector", "json_path", "video_timestamp", "image_region", "source"]
    locator: str
    block_id: str | None = None
    original_text: str | None = None


class SourceRecord(StrictModel):
    source_id: str
    schema_version: str = SCHEMA_VERSION
    source_type: SourceType
    platform: str | None = None
    publisher: str | None = None
    author: str | None = None
    source_uri: str | None = None
    local_path: str
    content_hash: str
    parent_source_id: str | None = None
    captured_at: datetime | None = None
    published_at: datetime | None = None
    timezone: str | None = None
    languages: list[str] = Field(default_factory=list)
    title: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    ingest_warnings: list[str] = Field(default_factory=list)
    independence: Literal["original", "repost", "syndicated", "quoted", "unknown"] = "unknown"
    dependency_group: str | None = None


class ParsedBlock(StrictModel):
    block_id: str
    source_id: str
    kind: Literal[
        "headline", "byline", "published_time", "article", "post", "caption", "comment", "link"
    ]
    text: str
    author: str | None = None
    url: str | None = None
    reactions: int | None = None
    locator: ProvenanceLocator


class EvidenceItem(StrictModel):
    evidence_id: str
    source_id: str
    modality: Literal["text", "image", "video", "audio"]
    evidence_kind: str
    assertion_type: AssertionType
    claim_text: str
    normalized_claim: str
    claimant: str | None = None
    claimant_role: str | None = None
    subject: str | None = None
    predicate: str | None = None
    object: str | int | float | bool | None = None
    entities: list[str] = Field(default_factory=list)
    vehicles: list[str] = Field(default_factory=list)
    road_users: list[str] = Field(default_factory=list)
    casualty_quantities: dict[str, int | None] = Field(default_factory=dict)
    traffic_effects: list[str] = Field(default_factory=list)
    location_mentions: list[str] = Field(default_factory=list)
    time_mentions: list[str] = Field(default_factory=list)
    provenance: ProvenanceLocator
    extraction_confidence: float = Field(ge=0, le=1)
    source_support: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)


class TimeInterval(StrictModel):
    start: datetime | None = None
    end: datetime | None = None
    original_expression: str | None = None
    timezone: str | None = None
    precision: Literal["minute", "hour", "day", "month", "year", "unknown"] = "unknown"


class LocationCandidate(StrictModel):
    name: str
    normalized_name: str
    hierarchy: dict[str, str] = Field(default_factory=dict)
    latitude: float | None = None
    longitude: float | None = None
    granularity: Literal[
        "point", "intersection", "road_segment", "area", "city", "district", "unknown"
    ] = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str | None = None


class SentimentEvidence(StrictModel):
    sentiment_id: str
    holder: str
    holder_type: str
    target: str
    aspect: str
    polarity: Literal["positive", "neutral", "negative", "mixed", "unknown"]
    emotion: str | None = None
    intensity: Literal["low", "medium", "high", "unknown"] = "unknown"
    sarcasm_uncertainty: float = Field(default=0, ge=0, le=1)
    traffic_related: bool
    evidence_id: str
    source_id: str
    confidence: float = Field(ge=0, le=1)


class IncidentMention(StrictModel):
    mention_id: str
    source_id: str
    evidence_ids: list[str]
    event_type: str
    event_subtype: str | None = None
    event_time: TimeInterval = Field(default_factory=TimeInterval)
    locations: list[LocationCandidate] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    vehicles: list[str] = Field(default_factory=list)
    casualties: dict[str, int | None] = Field(default_factory=dict)
    collision_description: str | None = None
    traffic_effects: list[str] = Field(default_factory=list)
    response: list[str] = Field(default_factory=list)
    sentiment_ids: list[str] = Field(default_factory=list)
    lexical_features: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    completeness: float = Field(default=0.5, ge=0, le=1)
    relation_type: Literal["primary", "response_to", "later_development_of"] = "primary"


class MatchFeatures(StrictModel):
    time_score: float = Field(ge=0, le=1)
    location_score: float = Field(ge=0, le=1)
    entity_score: float = Field(ge=0, le=1)
    vehicle_score: float = Field(ge=0, le=1)
    lexical_score: float = Field(ge=0, le=1)
    total_score: float = Field(ge=0, le=1)
    hard_guard: str | None = None


class MatchDecision(StrictModel):
    left_mention_id: str
    right_mention_id: str
    decision: Literal["same_incident", "related_but_distinct", "different_incident", "uncertain"]
    confidence: float = Field(ge=0, le=1)
    decisive_evidence_ids: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    rationale: str
    features: MatchFeatures
    provider_run_id: str | None = None


class FusedFact(StrictModel):
    field: str
    value: Any = None
    state: Literal["known", "unknown", "not_reported", "not_applicable", "reported_zero"] = "known"
    support_evidence_ids: list[str] = Field(default_factory=list)
    conflicting_values: list[Any] = Field(default_factory=list)
    contradiction: bool = False
    confidence: float = Field(ge=0, le=1)
    selection_rationale: str


class Geolocation(StrictModel):
    display_name: str | None = None
    hierarchy: dict[str, str] = Field(default_factory=dict)
    latitude: float | None = None
    longitude: float | None = None
    granularity: Literal[
        "point", "intersection", "road_segment", "area", "city", "district", "unknown"
    ] = "unknown"
    method: str = "unresolved"
    alternatives: list[LocationCandidate] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    ambiguity_reason: str | None = None
    uncertainty_radius_km: float | None = None

    @model_validator(mode="after")
    def coordinate_pair(self) -> Geolocation:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        return self


class SentimentSummary(StrictModel):
    items: list[SentimentEvidence] = Field(default_factory=list)
    by_aspect: dict[str, dict[str, int]] = Field(default_factory=dict)
    sample_size: int = 0
    traffic_relevant_count: int = 0
    coverage_note: str = "No visible traffic-related sentiment was supplied."
    notable_minority_views: list[str] = Field(default_factory=list)


class FusedIncident(StrictModel):
    incident_id: str
    schema_version: str = SCHEMA_VERSION
    title: str
    event_type: str
    status: Literal["reported", "developing", "resolved", "uncertain"] = "reported"
    event_time: TimeInterval = Field(default_factory=TimeInterval)
    alternate_time_claims: list[TimeInterval] = Field(default_factory=list)
    geolocation: Geolocation = Field(default_factory=Geolocation)
    facts: list[FusedFact] = Field(default_factory=list)
    involved_parties: list[str] = Field(default_factory=list)
    vehicles: list[str] = Field(default_factory=list)
    collision: str | None = None
    obstruction: str | None = None
    congestion_delay: str | None = None
    emergency_response: list[str] = Field(default_factory=list)
    contributing_factors: list[str] = Field(default_factory=list)
    later_developments: list[str] = Field(default_factory=list)
    source_ids: list[str]
    evidence_ids: list[str]
    independent_source_count: int = 0
    duplicate_groups: list[list[str]] = Field(default_factory=list)
    sentiment: SentimentSummary = Field(default_factory=SentimentSummary)
    unresolved_questions: list[str] = Field(default_factory=list)
    data_quality_warnings: list[str] = Field(default_factory=list)
    human_summary: str
    generated_at: datetime
    provider_run_id: str | None = None


class ProviderRun(StrictModel):
    run_id: str
    cluster_id: str
    operation: Literal["match", "fusion"]
    provider: str
    model: str
    endpoint_mode: str
    prompt_version: str
    prompt_hash: str
    request_hash: str
    started_at: datetime
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    retries: int = 0
    finish_status: str
    validation_status: str
    cache_hit: bool = False
    error: str | None = None


class PipelineRunSummary(StrictModel):
    run_id: str
    mode: Literal["live", "recorded"]
    provider: str
    model: str
    status: Literal["running", "completed", "partial", "failed"]
    started_at: datetime
    completed_at: datetime | None = None
    input_files: int = 0
    sources: int = 0
    evidence_items: int = 0
    mentions: int = 0
    incidents: int = 0
    warnings: list[str] = Field(default_factory=list)
