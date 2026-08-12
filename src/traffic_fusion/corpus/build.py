from __future__ import annotations

import hashlib
import html
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from traffic_fusion.corpus.discovery import CountryProfile, canonicalize_url
from traffic_fusion.corpus.models import (
    CorpusCountry,
    CorpusIncident,
    CorpusLock,
    CorpusManifest,
    CorpusPolicy,
    CorpusSource,
    LinkCheck,
    PayloadArtifact,
    ReviewEvent,
    SourceStatus,
    StrictCorpusModel,
    VerificationLink,
)
from traffic_fusion.corpus.reporting import render_validation_report
from traffic_fusion.corpus.store import CorpusStore
from traffic_fusion.corpus.validation import validate_corpus

ELIGIBLE_ACCESS_STATUSES = {
    "accessible",
    "accessible_html",
    "feed_metadata_match",
    "rss_metadata_accessible",
}


class CollectedCandidate(StrictCorpusModel):
    """A small, redistributable discovery record used to construct the corpus."""

    country_iso2: str = Field(pattern=r"^[A-Z]{2}$")
    canonical_url: str
    title: str = Field(min_length=1, max_length=1_000)
    publisher: str = Field(min_length=1, max_length=240)
    domain: str = Field(min_length=1, max_length=253)
    excerpt: str = Field(min_length=1, max_length=4_000)
    languages: list[str] = Field(min_length=1)
    published_at: datetime | None = None
    discovered_at: datetime
    discovered_via: str = Field(min_length=1, max_length=80)
    discovery_url: str
    access_status: str = Field(min_length=1, max_length=80)
    incident_key: str | None = Field(default=None, max_length=240)
    pair_confidence: float | None = Field(default=None, ge=0, le=1)
    pair_reason: str | None = Field(default=None, max_length=1_000)

    @field_validator("canonical_url", "discovery_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        return canonicalize_url(value)

    @field_validator("languages")
    @classmethod
    def unique_languages(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned or len(cleaned) != len(set(cleaned)):
            raise ValueError("languages must be non-empty and unique")
        return cleaned

    @model_validator(mode="after")
    def domain_matches_url(self) -> CollectedCandidate:
        host = (urlsplit(self.canonical_url).hostname or "").casefold().removeprefix("www.")
        if host != self.domain.casefold().removeprefix("www."):
            raise ValueError("candidate domain must match canonical URL host")
        if self.incident_key and self.pair_confidence is None:
            raise ValueError("incident-key candidates require pair confidence")
        return self


class CorpusBuildResult(StrictCorpusModel):
    corpus_root: str
    accepted_sources: int
    countries: int
    multi_source_incidents: int
    links_report: str
    countries_report: str
    validation_report: str
    coverage_geojson: str
    lock_file: str


def load_candidates(paths: list[Path]) -> list[CollectedCandidate]:
    candidates: list[CollectedCandidate] = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                candidates.append(CollectedCandidate.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
    return candidates


def build_corpus(
    candidates: list[CollectedCandidate],
    profiles: dict[str, CountryProfile],
    output_dir: Path,
    *,
    corpus_id: str = "mgeoai-global-v1",
    sources_per_country: int = 10,
    created_at: datetime | None = None,
) -> CorpusBuildResult:
    """Build a validated metadata/excerpt corpus without copying publisher pages."""
    if sources_per_country < 10:
        raise ValueError("global corpus requires at least ten sources per country")
    timestamp = (created_at or datetime.now(UTC)).astimezone(UTC)
    selected = _select_candidates(candidates, profiles, sources_per_country)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"corpus output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    policy = CorpusPolicy(
        min_country_count=50,
        min_accepted_sources_per_country=sources_per_country,
        min_independent_sources_in_shared_incident=2,
    )
    manifest = CorpusManifest(
        corpus_id=corpus_id,
        title="MGeoAI global traffic-incident source corpus",
        created_at=timestamp,
        country_codes=sorted(profile.iso3 for profile in profiles.values()),
        policy=policy,
    )
    _write_model(output_dir / "corpus.json", manifest)

    source_ids_by_incident: dict[tuple[str, str], list[str]] = defaultdict(list)
    selected_by_country = {iso2: rows for iso2, rows in selected.items()}
    for iso2, profile in sorted(profiles.items()):
        country = CorpusCountry(
            country_code=profile.iso3,
            name=profile.name,
            languages=list(profile.languages),
            timezones=[profile.primary_timezone],
            target_sources=max(12, sources_per_country),
        )
        _write_model(output_dir / "countries" / profile.iso3 / "country.json", country)
        for index, candidate in enumerate(selected_by_country[iso2], 1):
            source_id = f"{profile.iso3}-S{index:03d}"
            review_id = f"review-{source_id}"
            source_root = output_dir / "sources" / source_id
            payload = _evidence_html(candidate, profile)
            artifact_path = source_root / "content.html"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            source = CorpusSource(
                corpus_source_id=source_id,
                country_code=profile.iso3,
                status=SourceStatus.ACCEPTED,
                traffic_incident=True,
                publisher=candidate.publisher,
                canonical_url=candidate.canonical_url,
                verification_links=[
                    VerificationLink(
                        rel="original",
                        url=candidate.canonical_url,
                        label="Open the publisher source for manual verification",
                    ),
                    VerificationLink(
                        rel="manual",
                        url=candidate.discovery_url,
                        label=f"Discovery record ({candidate.discovered_via})",
                    ),
                ],
                artifacts=[
                    PayloadArtifact(
                        role="html",
                        path="content.html",
                        sha256=digest,
                        size_bytes=len(payload),
                    )
                ],
                languages=candidate.languages,
                traffic_keywords=list(profile.query_terms),
                timezone=profile.primary_timezone,
                captured_at=candidate.discovered_at,
                published_at=candidate.published_at,
                capture_method="archive",
                independence="original",
                dependency_group=candidate.domain,
                redistribution_status="metadata_only",
                latest_review_id=review_id,
            )
            _write_model(source_root / "source.json", source)
            review = ReviewEvent(
                review_id=review_id,
                corpus_source_id=source_id,
                reviewer="automated-feed-link-check-v1",
                review_method="automated",
                reviewed_at=timestamp,
                decision="accepted",
                link_checks=[
                    LinkCheck(
                        rel="original",
                        url=candidate.canonical_url,
                        outcome="content_match",
                        checked_at=candidate.discovered_at,
                    )
                ],
                note=(
                    "Automated metadata/excerpt match from the named discovery feed. "
                    "The original URL is retained for independent human verification; "
                    "acceptance is not an incident-truth determination."
                ),
            )
            _write_jsonl(output_dir / "reviews" / f"{profile.iso3}.jsonl", review)
            if candidate.incident_key:
                source_ids_by_incident[(profile.iso3, candidate.incident_key)].append(source_id)

    incident_count = 0
    for (iso3, incident_key), source_ids in sorted(source_ids_by_incident.items()):
        if len(source_ids) < 2:
            continue
        domains = {
            _read_source(output_dir, source_id).dependency_group for source_id in source_ids
        }
        if len(domains) < 2:
            continue
        incident_count += 1
        incident_id = f"{iso3}-INC-{incident_count:03d}"
        incident = CorpusIncident(
            curation_incident_id=incident_id,
            country_code=iso3,
            source_ids=source_ids,
            label="reviewed_same_incident",
            review_method="automated",
            reviewed_by=["automated-title-date-entity-pair-v1"],
            reviewed_at=timestamp,
            note=(
                f"Automated multi-source candidate key {incident_key!r}; distinct domains and "
                "matching feed metadata. Human confirmation should use each original URL."
            ),
        )
        _write_model(output_dir / "incidents" / f"{incident_id}.json", incident)

    store = CorpusStore(output_dir)
    report = validate_corpus(store)
    if not report.valid:
        details = "; ".join(f"{item.code}: {item.message}" for item in report.issues[:20])
        raise ValueError(f"generated corpus failed validation: {details}")
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    validation_path = reports_dir / "validation.md"
    validation_path.write_text(render_validation_report(report), encoding="utf-8")
    countries_path = reports_dir / "countries.md"
    countries_path.write_text(_country_report(report, profiles), encoding="utf-8")
    links_path = reports_dir / "source_links.csv"
    links_path.write_text(
        _links_csv(selected_by_country, profiles),
        encoding="utf-8",
    )
    coverage_path = reports_dir / "coverage.geojson"
    coverage_path.write_text(
        json.dumps(_coverage_geojson(report, profiles), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lock = store.build_lock()
    lock_path = output_dir / "locks" / "corpus.lock.json"
    _write_model(lock_path, lock)
    return CorpusBuildResult(
        corpus_root=str(output_dir),
        accepted_sources=sum(item.accepted_sources for item in report.countries),
        countries=len(report.countries),
        multi_source_incidents=sum(item.reviewed_shared_incidents for item in report.countries),
        links_report=str(links_path),
        countries_report=str(countries_path),
        validation_report=str(validation_path),
        coverage_geojson=str(coverage_path),
        lock_file=str(lock_path),
    )


def _select_candidates(
    candidates: list[CollectedCandidate],
    profiles: dict[str, CountryProfile],
    sources_per_country: int,
) -> dict[str, list[CollectedCandidate]]:
    grouped: dict[str, list[CollectedCandidate]] = defaultdict(list)
    for candidate in candidates:
        if (
            candidate.country_iso2 in profiles
            and candidate.access_status in ELIGIBLE_ACCESS_STATUSES
        ):
            grouped[candidate.country_iso2].append(candidate)
    selected: dict[str, list[CollectedCandidate]] = {}
    for iso2 in sorted(profiles):
        rows = grouped[iso2]
        unique_by_url: dict[str, CollectedCandidate] = {}
        for row in sorted(
            rows,
            key=lambda item: (
                0 if item.incident_key else 1,
                -(item.pair_confidence or 0),
                item.domain,
                item.canonical_url,
            ),
        ):
            unique_by_url.setdefault(row.canonical_url, row)
        pair_counts = Counter(
            row.incident_key for row in unique_by_url.values() if row.incident_key
        )
        qualifying_keys = {key for key, count in pair_counts.items() if count >= 2}
        if not qualifying_keys:
            raise ValueError(f"country {iso2} has no two-source incident candidate")
        qualifying = [
            row for row in unique_by_url.values() if row.incident_key in qualifying_keys
        ]
        chosen_pair: list[CollectedCandidate] = []
        for key in sorted(
            qualifying_keys,
            key=lambda item: -max(
                row.pair_confidence or 0
                for row in qualifying
                if row.incident_key == item
            ),
        ):
            pair_rows = [row for row in qualifying if row.incident_key == key]
            domain_rows: dict[str, CollectedCandidate] = {}
            for row in pair_rows:
                domain_rows.setdefault(row.domain, row)
            if len(domain_rows) >= 2:
                chosen_pair = list(domain_rows.values())[:2]
                break
        if not chosen_pair:
            raise ValueError(f"country {iso2} has no independent-domain incident pair")
        chosen = list(chosen_pair)
        chosen_urls = {row.canonical_url for row in chosen}
        for row in unique_by_url.values():
            if row.canonical_url in chosen_urls:
                continue
            chosen.append(row)
            chosen_urls.add(row.canonical_url)
            if len(chosen) >= sources_per_country:
                break
        if len(chosen) < sources_per_country:
            raise ValueError(
                f"country {iso2} has {len(chosen)} unique accepted candidates; "
                f"requires {sources_per_country}"
            )
        selected[iso2] = chosen[:sources_per_country]
    return selected


def _evidence_html(candidate: CollectedCandidate, profile: CountryProfile) -> bytes:
    language = candidate.languages[0]
    published = (
        candidate.published_at.astimezone(ZoneInfo(profile.primary_timezone)).isoformat()
        if candidate.published_at
        else ""
    )
    excerpt = _short_words(candidate.excerpt, 25)
    document = f"""<!doctype html>
<html lang="{html.escape(language, quote=True)}">
<head>
  <meta charset="utf-8">
  <title>{html.escape(candidate.title)}</title>
  <link rel="canonical" href="{html.escape(candidate.canonical_url, quote=True)}">
</head>
<body>
  <article>
    <h1>{html.escape(candidate.title)}</h1>
    {f'<time datetime="{html.escape(published, quote=True)}">{html.escape(published)}</time>' if published else ''}
    <p>{html.escape(excerpt)}</p>
    <p>Publisher: {html.escape(candidate.publisher)}</p>
    <p>Original source: <a href="{html.escape(candidate.canonical_url, quote=True)}">{html.escape(candidate.canonical_url)}</a></p>
    <p>Collection note: short public-feed metadata excerpt; open the original link for manual verification.</p>
  </article>
</body>
</html>
"""
    return document.encode("utf-8")


def _short_words(value: str, limit: int) -> str:
    words = value.split()
    if len(words) <= limit:
        return value
    return " ".join(words[:limit]).rstrip(" ,;:") + " …"


def _country_report(report: Any, profiles: dict[str, CountryProfile]) -> str:
    profile_by_iso3 = {profile.iso3: profile for profile in profiles.values()}
    lines = [
        "# Countries represented in MGeoAI global-v1",
        "",
        "Coverage coordinates are country-level publisher/source markers, not crash locations.",
        "",
        "| ISO | Country | Accepted sources | Multi-source incidents |",
        "| --- | --- | ---: | ---: |",
    ]
    for item in report.countries:
        profile = profile_by_iso3[item.country_code]
        lines.append(
            f"| {item.country_code} | {profile.name} | {item.accepted_sources} | "
            f"{item.reviewed_shared_incidents} |"
        )
    return "\n".join(lines) + "\n"


def _links_csv(
    selected: dict[str, list[CollectedCandidate]],
    profiles: dict[str, CountryProfile],
) -> str:
    lines = [
        "country_code,corpus_source_id,title,publisher,domain,published_at,"
        "manual_verification_url,discovery_url,incident_key,event_country_status"
    ]
    for iso2, rows in sorted(selected.items()):
        profile = profiles[iso2]
        for index, candidate in enumerate(rows, 1):
            values = [
                profile.iso3,
                f"{profile.iso3}-S{index:03d}",
                candidate.title,
                candidate.publisher,
                candidate.domain,
                candidate.published_at.isoformat() if candidate.published_at else "",
                candidate.canonical_url,
                candidate.discovery_url,
                candidate.incident_key or "",
                "not_verified_collection_country_only",
            ]
            lines.append(",".join(_csv(item) for item in values))
    return "\n".join(lines) + "\n"


def _coverage_geojson(report: Any, profiles: dict[str, CountryProfile]) -> dict[str, Any]:
    counts = {item.country_code: item for item in report.countries}
    features = []
    for profile in sorted(profiles.values(), key=lambda item: item.iso3):
        feature = profile.to_coverage_feature()
        item = counts[profile.iso3]
        feature["properties"].update(
            {
                "accepted_sources": item.accepted_sources,
                "reviewed_multi_source_incidents": item.reviewed_shared_incidents,
            }
        )
        features.append(feature)
    return {
        "type": "FeatureCollection",
        "name": "MGeoAI collection-country source coverage; not incident locations",
        "features": features,
    }


def _csv(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _write_model(path: Path, model: StrictCorpusModel | CorpusLock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, model: StrictCorpusModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(model.model_dump_json() + "\n")


def _read_source(root: Path, source_id: str) -> CorpusSource:
    return CorpusSource.model_validate_json(
        (root / "sources" / source_id / "source.json").read_text(encoding="utf-8")
    )
