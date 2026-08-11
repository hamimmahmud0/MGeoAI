from __future__ import annotations

import hashlib
from collections import Counter, defaultdict

from pydantic import Field, computed_field

from traffic_fusion.corpus.models import (
    CorpusPolicy,
    SourceStatus,
    StrictCorpusModel,
)
from traffic_fusion.corpus.store import CorpusStore


class ValidationIssue(StrictCorpusModel):
    code: str
    message: str
    path: str | None = None


class CountryStatistics(StrictCorpusModel):
    country_code: str
    accepted_sources: int = 0
    independent_groups: int = 0
    reviewed_shared_incidents: int = 0


class ValidationReport(StrictCorpusModel):
    corpus_id: str
    policy: CorpusPolicy
    countries: list[CountryStatistics]
    issues: list[ValidationIssue] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def valid(self) -> bool:
        return not self.issues


def validate_corpus(
    store: CorpusStore, policy: CorpusPolicy | None = None
) -> ValidationReport:
    manifest = store.manifest()
    active_policy = policy or manifest.policy
    countries = store.countries()
    sources = store.sources()
    incidents = store.incidents()
    reviews = store.reviews()
    issues: list[ValidationIssue] = []

    def issue(code: str, message: str, path: str | None = None) -> None:
        issues.append(ValidationIssue(code=code, message=message, path=path))

    country_counts = Counter(item.country_code for item in countries)
    duplicate_countries = sorted(code for code, count in country_counts.items() if count > 1)
    for code in duplicate_countries:
        issue("duplicate_country", f"country {code} has more than one record")
    actual_country_codes = {item.country_code for item in countries}
    declared_country_codes = set(manifest.country_codes)
    if actual_country_codes != declared_country_codes:
        issue(
            "country_manifest_mismatch",
            "manifest country codes differ from country records: "
            f"missing={sorted(declared_country_codes - actual_country_codes)}, "
            f"undeclared={sorted(actual_country_codes - declared_country_codes)}",
            "corpus.json",
        )
    if len(actual_country_codes) < active_policy.min_country_count:
        issue(
            "country_quota",
            f"corpus has {len(actual_country_codes)} countries; "
            f"requires {active_policy.min_country_count}",
        )

    source_counts = Counter(item.corpus_source_id for item in sources)
    for source_id, count in sorted(source_counts.items()):
        if count > 1:
            issue("duplicate_source", f"source ID {source_id} appears {count} times")
    source_by_id = {item.corpus_source_id: item for item in sources}

    review_counts = Counter(item.review_id for item in reviews)
    for review_id, count in sorted(review_counts.items()):
        if count > 1:
            issue("duplicate_review", f"review ID {review_id} appears {count} times")
    review_by_id = {item.review_id: item for item in reviews}

    accepted_by_country: dict[str, list[str]] = defaultdict(list)
    groups_by_country: dict[str, set[str]] = defaultdict(set)
    accepted_urls_by_country: dict[str, dict[str, str]] = defaultdict(dict)
    accepted_payloads_by_country: dict[str, dict[str, str]] = defaultdict(dict)
    for source in sources:
        record_path = f"sources/{source.corpus_source_id}/source.json"
        if source.country_code not in actual_country_codes:
            issue(
                "unknown_source_country",
                f"source {source.corpus_source_id} references undeclared country "
                f"{source.country_code}",
                record_path,
            )
        for artifact in source.artifacts:
            try:
                artifact_path = store.artifact_path(source, artifact.path)
            except ValueError as exc:
                issue("unsafe_artifact", str(exc), record_path)
                continue
            if not artifact_path.is_file() or artifact_path.is_symlink():
                issue(
                    "missing_artifact",
                    f"artifact is missing or not a regular file: {artifact.path}",
                    record_path,
                )
                continue
            content = artifact_path.read_bytes()
            if len(content) != artifact.size_bytes:
                issue(
                    "artifact_size",
                    f"artifact {artifact.path} declares {artifact.size_bytes} bytes, "
                    f"found {len(content)}",
                    record_path,
                )
            digest = hashlib.sha256(content).hexdigest()
            if digest != artifact.sha256:
                issue(
                    "artifact_hash",
                    f"artifact {artifact.path} SHA-256 does not match its record",
                    record_path,
                )
            try:
                content.decode(artifact.encoding)
            except UnicodeDecodeError:
                issue(
                    "artifact_encoding",
                    f"artifact {artifact.path} is not valid {artifact.encoding}",
                    record_path,
                )

        if source.status != SourceStatus.ACCEPTED or not source.traffic_incident:
            continue
        previous_url = accepted_urls_by_country[source.country_code].get(source.canonical_url)
        if previous_url:
            issue(
                "accepted_duplicate_url",
                f"accepted sources {previous_url} and {source.corpus_source_id} share a "
                "canonical URL; mark the duplicate record accordingly",
                record_path,
            )
        else:
            accepted_urls_by_country[source.country_code][source.canonical_url] = (
                source.corpus_source_id
            )
        primary_hash = next(
            item.sha256 for item in source.artifacts if item.role in {"html", "video_analysis"}
        )
        previous_payload = accepted_payloads_by_country[source.country_code].get(primary_hash)
        if previous_payload:
            issue(
                "accepted_duplicate_payload",
                f"accepted sources {previous_payload} and {source.corpus_source_id} share an "
                "exact primary payload; mark the duplicate record accordingly",
                record_path,
            )
        else:
            accepted_payloads_by_country[source.country_code][primary_hash] = (
                source.corpus_source_id
            )
        accepted_by_country[source.country_code].append(source.corpus_source_id)
        if source.independence == "original":
            groups_by_country[source.country_code].add(source.dependency_group)
        review = review_by_id.get(source.latest_review_id or "")
        if review is None:
            issue(
                "missing_accepted_review",
                f"accepted source {source.corpus_source_id} has no matching review event",
                record_path,
            )
            continue
        if review.corpus_source_id != source.corpus_source_id:
            issue(
                "review_source_mismatch",
                f"review {review.review_id} belongs to {review.corpus_source_id}",
                record_path,
            )
        if review.decision != "accepted":
            issue(
                "review_not_accepted",
                f"latest review {review.review_id} did not accept the source",
                record_path,
            )
        configured_links = {(item.rel, item.url) for item in source.verification_links}
        matching_checks = [
            check
            for check in review.link_checks
            if (check.rel, check.url) in configured_links and check.outcome == "content_match"
        ]
        if not matching_checks:
            issue(
                "manual_verification",
                f"accepted source {source.corpus_source_id} lacks a content-matching "
                "manual verification check for a configured URL",
                record_path,
            )

    incident_counts = Counter(item.curation_incident_id for item in incidents)
    for incident_id, count in sorted(incident_counts.items()):
        if count > 1:
            issue("duplicate_incident", f"incident ID {incident_id} appears {count} times")
        if incident_id in source_by_id:
            issue(
                "gold_identifier_collision",
                f"curation incident ID {incident_id} collides with a source ID",
                f"incidents/{incident_id}.json",
            )
    qualifying_by_country: dict[str, int] = defaultdict(int)
    for incident in incidents:
        path = f"incidents/{incident.curation_incident_id}.json"
        linked = []
        for source_id in incident.source_ids:
            linked_source = source_by_id.get(source_id)
            if linked_source is None:
                issue(
                    "unknown_incident_source",
                    f"incident references unknown source {source_id}",
                    path,
                )
                continue
            linked.append(linked_source)
            if linked_source.country_code != incident.country_code:
                issue(
                    "incident_country_mismatch",
                    f"source {source_id} belongs to {linked_source.country_code}, not "
                    f"{incident.country_code}",
                    path,
                )
        independent_groups = {
            source.dependency_group
            for source in linked
            if source.status == SourceStatus.ACCEPTED
            and source.traffic_incident
            and source.independence == "original"
        }
        if (
            incident.label == "reviewed_same_incident"
            and len(independent_groups)
            >= active_policy.min_independent_sources_in_shared_incident
        ):
            qualifying_by_country[incident.country_code] += 1

    statistics: list[CountryStatistics] = []
    for code in sorted(actual_country_codes):
        accepted = len(accepted_by_country[code])
        shared = qualifying_by_country[code]
        statistics.append(
            CountryStatistics(
                country_code=code,
                accepted_sources=accepted,
                independent_groups=len(groups_by_country[code]),
                reviewed_shared_incidents=shared,
            )
        )
        if accepted < active_policy.min_accepted_sources_per_country:
            issue(
                "source_quota",
                f"country {code} has {accepted} accepted traffic sources; requires "
                f"{active_policy.min_accepted_sources_per_country}",
            )
        if shared < 1:
            issue(
                "multi_source_incident",
                f"country {code} has no reviewed incident supported by at least "
                f"{active_policy.min_independent_sources_in_shared_incident} independent groups",
            )

    return ValidationReport(
        corpus_id=manifest.corpus_id,
        policy=active_policy,
        countries=statistics,
        issues=issues,
    )
