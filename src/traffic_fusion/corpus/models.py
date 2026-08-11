from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"
ISO3_PATTERN = r"^[A-Z]{3}$"
IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
ISO_ALPHA3_CODES = frozenset(
    """
    AFG ALB DZA ASM AND AGO AIA ATA ATG ARG ARM ABW AUS AUT AZE ALA
    BHS BHR BGD BRB BLR BEL BLZ BEN BMU BTN BOL BES BIH BWA BVT BRA IOT BRN BGR BFA BDI
    CPV KHM CMR CAN CYM CAF TCD CHL CHN CXR CCK COL COM COG COD COK CRI CIV HRV CUB CUW CYP CZE
    DNK DJI DMA DOM ECU EGY SLV GNQ ERI EST SWZ ETH FLK FRO FJI FIN FRA GUF PYF ATF
    GAB GMB GEO DEU GHA GIB GRC GRL GRD GLP GUM GTM GGY GIN GNB GUY
    HTI HMD VAT HND HKG HUN ISL IND IDN IRN IRQ IRL IMN ISR ITA
    JAM JPN JEY JOR KAZ KEN KIR PRK KOR KWT KGZ
    LAO LVA LBN LSO LBR LBY LIE LTU LUX MAC MDG MWI MYS MDV MLI MLT MHL MTQ MRT MUS MYT
    MEX FSM MDA MCO MNG MNE MSR MAR MOZ MMR NAM NRU NPL NLD NCL NZL NIC NER NGA NIU NFK
    MKD MNP NOR OMN PAK PLW PSE PAN PNG PRY PER PHL PCN POL PRT PRI QAT REU ROU RUS RWA
    BLM SHN KNA LCA MAF SPM VCT WSM SMR STP SAU SEN SRB SYC SLE SGP SXM SVK SVN SLB SOM
    ZAF SGS SSD ESP LKA SDN SUR SJM SWE CHE SYR TWN TJK TZA THA TLS TGO TKL TON TTO TUN
    TUR TKM TCA TUV UGA UKR ARE GBR USA UMI URY UZB VUT VEN VNM VGB VIR WLF ESH YEM ZMB ZWE
    """.split()
)


class StrictCorpusModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("path must be a safe POSIX path relative to its record")
    return path.as_posix()


def _web_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("URL must not contain credentials")
    return value


def _iso_alpha3(value: str) -> str:
    if value not in ISO_ALPHA3_CODES:
        raise ValueError("country code must be an assigned ISO 3166-1 alpha-3 value")
    return value


class SourceStatus(StrEnum):
    ACCEPTED = "accepted"
    PENDING = "pending"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    DUPLICATE = "duplicate"


class CorpusPolicy(StrictCorpusModel):
    min_country_count: int = Field(default=50, ge=1)
    min_accepted_sources_per_country: int = Field(default=10, ge=1)
    min_independent_sources_in_shared_incident: int = Field(default=2, ge=2)


class CorpusManifest(StrictCorpusModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    corpus_id: str = Field(pattern=IDENTIFIER_PATTERN)
    title: str = Field(min_length=1, max_length=240)
    created_at: datetime
    country_codes: list[str] = Field(min_length=1)
    policy: CorpusPolicy = Field(default_factory=CorpusPolicy)

    @field_validator("country_codes")
    @classmethod
    def valid_country_codes(cls, value: list[str]) -> list[str]:
        if any(len(code) != 3 or not code.isascii() or not code.isalpha() or not code.isupper() for code in value):
            raise ValueError("country codes must be uppercase ISO alpha-3 values")
        if len(set(value)) != len(value):
            raise ValueError("country codes must be unique")
        invalid = sorted(set(value) - ISO_ALPHA3_CODES)
        if invalid:
            raise ValueError(f"country codes are not assigned ISO alpha-3 values: {invalid}")
        return value


class CorpusCountry(StrictCorpusModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    country_code: str = Field(pattern=ISO3_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    languages: list[str] = Field(min_length=1)
    timezones: list[str] = Field(min_length=1)
    target_sources: int = Field(default=12, ge=10)

    _validate_country_code = field_validator("country_code")(_iso_alpha3)

    @field_validator("languages", "timezones")
    @classmethod
    def unique_nonempty_values(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("values must be non-empty and unique")
        return cleaned


class PayloadArtifact(StrictCorpusModel):
    role: Literal["html", "video_analysis", "image_analysis"]
    path: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=1)
    encoding: Literal["utf-8"] = "utf-8"

    _validate_path = field_validator("path")(_safe_relative_path)


class VerificationLink(StrictCorpusModel):
    rel: Literal["original", "archive", "publisher", "manual"]
    url: str
    label: str | None = Field(default=None, max_length=240)

    _validate_url = field_validator("url")(_web_url)


class CorpusSource(StrictCorpusModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    corpus_source_id: str = Field(pattern=IDENTIFIER_PATTERN)
    country_code: str = Field(pattern=ISO3_PATTERN)
    status: SourceStatus
    traffic_incident: bool = True
    publisher: str = Field(min_length=1, max_length=240)
    canonical_url: str
    verification_links: list[VerificationLink] = Field(min_length=1)
    artifacts: list[PayloadArtifact] = Field(min_length=1)
    languages: list[str] = Field(min_length=1)
    traffic_keywords: list[str] = Field(default_factory=list)
    timezone: str = Field(min_length=1, max_length=120)
    captured_at: datetime
    published_at: datetime | None = None
    capture_method: Literal["http", "manual_browser_save", "manual_upload", "archive"]
    independence: Literal["original", "repost", "syndicated", "quoted", "unknown"]
    dependency_group: str = Field(min_length=1, max_length=240)
    redistribution_status: Literal[
        "redistributable", "internal_research_only", "metadata_only"
    ]
    latest_review_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)

    _validate_country_code = field_validator("country_code")(_iso_alpha3)
    _validate_canonical_url = field_validator("canonical_url")(_web_url)

    @model_validator(mode="after")
    def valid_artifact_shape(self) -> CorpusSource:
        roles = [item.role for item in self.artifacts]
        primary = roles.count("html") + roles.count("video_analysis")
        if primary != 1:
            raise ValueError("source must contain exactly one HTML or video-analysis artifact")
        if len(set(roles)) != len(roles):
            raise ValueError("artifact roles must be unique")
        if "image_analysis" in roles and "html" not in roles:
            raise ValueError("image analysis must accompany an HTML artifact")
        if not any(item.rel == "original" for item in self.verification_links):
            raise ValueError("source requires an original manual-verification URL")
        if len({(item.rel, item.url) for item in self.verification_links}) != len(
            self.verification_links
        ):
            raise ValueError("verification links must be unique")
        if len(set(self.languages)) != len(self.languages):
            raise ValueError("languages must be unique")
        if self.traffic_incident and not self.traffic_keywords:
            raise ValueError("traffic-incident source requires at least one traffic keyword")
        if any(not item.strip() for item in self.traffic_keywords) or len(
            set(self.traffic_keywords)
        ) != len(self.traffic_keywords):
            raise ValueError("traffic keywords must be non-empty and unique")
        if self.status == SourceStatus.ACCEPTED and not self.latest_review_id:
            raise ValueError("accepted source requires a latest review ID")
        return self


class LinkCheck(StrictCorpusModel):
    rel: Literal["original", "archive", "publisher", "manual"]
    url: str
    outcome: Literal["content_match", "partial_match", "unavailable", "mismatch"]
    checked_at: datetime

    _validate_url = field_validator("url")(_web_url)


class ReviewEvent(StrictCorpusModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    review_id: str = Field(pattern=IDENTIFIER_PATTERN)
    corpus_source_id: str = Field(pattern=IDENTIFIER_PATTERN)
    reviewer: str = Field(min_length=1, max_length=160)
    review_method: Literal["human", "automated"] = "human"
    reviewed_at: datetime
    decision: Literal["accepted", "rejected", "needs_changes"]
    link_checks: list[LinkCheck] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=2000)


class CorpusIncident(StrictCorpusModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    curation_only: Literal[True] = True
    curation_incident_id: str = Field(pattern=IDENTIFIER_PATTERN)
    country_code: str = Field(pattern=ISO3_PATTERN)
    source_ids: list[str] = Field(min_length=1)
    label: Literal["reviewed_same_incident", "candidate_group", "rejected_group"]
    review_method: Literal["human", "automated"] = "human"
    reviewed_by: list[str] = Field(default_factory=list)
    reviewed_at: datetime | None = None
    note: str | None = Field(default=None, max_length=2000)

    _validate_country_code = field_validator("country_code")(_iso_alpha3)

    @model_validator(mode="after")
    def valid_review(self) -> CorpusIncident:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("incident source IDs must be unique")
        if self.label == "reviewed_same_incident" and (
            not self.reviewed_by or self.reviewed_at is None
        ):
            raise ValueError("reviewed incident requires reviewer and review timestamp")
        return self


class AccessAttempt(StrictCorpusModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    candidate_id: str = Field(pattern=IDENTIFIER_PATTERN)
    url: str
    attempted_at: datetime
    attempt: int = Field(ge=1)
    outcome: Literal[
        "captured",
        "robots_blocked",
        "http_403",
        "paywall",
        "rate_limited",
        "timeout",
        "tls_error",
        "geoblocked",
        "removed",
        "unsupported_media",
        "oversize",
        "other_failure",
    ]
    http_status: int | None = Field(default=None, ge=100, le=599)
    retryable: bool
    retry_after: datetime | None = None
    error_class: str | None = Field(default=None, max_length=160)

    _validate_url = field_validator("url")(_web_url)


class LockEntry(StrictCorpusModel):
    path: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)

    _validate_path = field_validator("path")(_safe_relative_path)


class CorpusLock(StrictCorpusModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    corpus_id: str = Field(pattern=IDENTIFIER_PATTERN)
    entries: list[LockEntry]
