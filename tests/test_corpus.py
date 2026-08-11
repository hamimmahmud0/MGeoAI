from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from traffic_fusion.corpus.materialize import materialization_digest, materialize_corpus
from traffic_fusion.corpus.models import (
    AccessAttempt,
    CorpusCountry,
    CorpusPolicy,
    CorpusSource,
)
from traffic_fusion.corpus.reporting import render_validation_report
from traffic_fusion.corpus.store import CorpusStore
from traffic_fusion.corpus.validation import validate_corpus
from traffic_fusion.ingest.discovery import discover
from traffic_fusion.ingest.html import parse_html

NOW = "2026-08-12T00:00:00Z"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def artifact(path: Path, role: str, content: bytes) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "role": role,
        "path": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "encoding": "utf-8",
    }


def make_source(
    root: Path,
    country: str,
    index: int,
    *,
    media: str = "html",
    image: bool = False,
    status: str = "accepted",
) -> str:
    source_id = f"{country}-S{index:03d}"
    source_root = root / "sources" / source_id
    if media == "html":
        content = (
            f"<!doctype html><title>{source_id} crash</title><article><h1>Road crash "
            f"report {index}</h1><p>One person was injured in a traffic collision.</p></article>"
        ).encode()
        artifacts = [artifact(source_root / "content.html", "html", content)]
        if image:
            image_content = json.dumps(
                {
                    "observations": [
                        {
                            "observation": "A damaged vehicle is visible.",
                            "observation_type": "direct_visual_observation",
                        }
                    ]
                }
            ).encode()
            artifacts.append(artifact(source_root / "image.json", "image_analysis", image_content))
    else:
        video_content = json.dumps(
            {
                "source": {"platform_or_publisher": f"Publisher {index}"},
                "traffic_incidents": [
                    {
                        "incident_type": "road_crash",
                        "location": f"Fixture locality {index}",
                        "fatalities": 1,
                    }
                ],
            }
        ).encode()
        artifacts = [artifact(source_root / "video.json", "video_analysis", video_content)]

    review_id = f"review-{source_id}"
    canonical_url = f"https://news{index}.{country.lower()}.example/crash"
    write_json(
        source_root / "source.json",
        {
            "schema_version": "1.0.0",
            "corpus_source_id": source_id,
            "country_code": country,
            "status": status,
            "traffic_incident": True,
            "publisher": f"Publisher {index}",
            "canonical_url": canonical_url,
            "verification_links": [{"rel": "original", "url": canonical_url}],
            "artifacts": artifacts,
            "languages": ["en"],
            "traffic_keywords": ["crash", "collision"],
            "timezone": "Etc/UTC",
            "captured_at": NOW,
            "published_at": NOW,
            "capture_method": "manual_browser_save",
            "independence": "original",
            "dependency_group": f"publisher-{country}-{index}",
            "redistribution_status": "redistributable",
            "latest_review_id": review_id if status == "accepted" else None,
        },
    )
    review_path = root / "reviews" / f"{source_id}.jsonl"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "review_id": review_id,
                "corpus_source_id": source_id,
                "reviewer": "fixture-reviewer",
                "reviewed_at": NOW,
                "decision": "accepted",
                "link_checks": [
                    {
                        "rel": "original",
                        "url": canonical_url,
                        "outcome": "content_match",
                        "checked_at": NOW,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return source_id


def corpus_fixture(root: Path) -> CorpusStore:
    countries = ["BGD", "ESP"]
    write_json(
        root / "corpus.json",
        {
            "schema_version": "1.0.0",
            "corpus_id": "fixture-global-v1",
            "title": "International fixture",
            "created_at": NOW,
            "country_codes": countries,
            "policy": {
                "min_country_count": 2,
                "min_accepted_sources_per_country": 2,
                "min_independent_sources_in_shared_incident": 2,
            },
        },
    )
    for code in countries:
        write_json(
            root / "countries" / code / "country.json",
            {
                "schema_version": "1.0.0",
                "country_code": code,
                "name": f"Fixture {code}",
                "languages": ["en"],
                "timezones": ["Etc/UTC"],
                "target_sources": 10,
            },
        )
        first = make_source(root, code, 1, image=code == "BGD")
        second = make_source(root, code, 2, media="video")
        write_json(
            root / "incidents" / f"{code}-INC-001.json",
            {
                "schema_version": "1.0.0",
                "curation_only": True,
                "curation_incident_id": f"{code}-INC-001",
                "country_code": code,
                "source_ids": [first, second],
                "label": "reviewed_same_incident",
                "reviewed_by": ["gold-reviewer"],
                "reviewed_at": NOW,
                "note": f"private gold note for {code}",
            },
        )
    return CorpusStore(root)


def test_strict_models_reject_unsafe_paths_and_credential_urls() -> None:
    with pytest.raises(ValidationError, match="assigned ISO"):
        CorpusCountry(
            country_code="AAA",
            name="Invented country",
            languages=["en"],
            timezones=["Etc/UTC"],
        )
    base = {
        "corpus_source_id": "BGD-S001",
        "country_code": "BGD",
        "status": "accepted",
        "publisher": "Publisher",
        "canonical_url": "https://example.test/report",
        "verification_links": [{"rel": "original", "url": "https://example.test/report"}],
        "artifacts": [
            {
                "role": "html",
                "path": "../content.html",
                "sha256": "a" * 64,
                "size_bytes": 1,
            }
        ],
        "languages": ["en"],
        "traffic_keywords": ["crash"],
        "timezone": "Etc/UTC",
        "captured_at": NOW,
        "capture_method": "http",
        "independence": "original",
        "dependency_group": "example.test",
        "redistribution_status": "redistributable",
        "latest_review_id": "review-1",
    }
    with pytest.raises(ValidationError, match="safe POSIX path"):
        CorpusSource.model_validate(base)
    base["artifacts"][0]["path"] = "content.html"  # type: ignore[index]
    base["canonical_url"] = "https://user:secret@example.test/report"
    with pytest.raises(ValidationError, match="must not contain credentials"):
        CorpusSource.model_validate(base)


def test_access_attempt_records_failures_without_secrets() -> None:
    attempt = AccessAttempt(
        candidate_id="candidate-1",
        url="https://example.test/report",
        attempted_at=datetime(2026, 8, 12, tzinfo=UTC),
        attempt=2,
        outcome="rate_limited",
        http_status=429,
        retryable=True,
    )
    assert attempt.outcome == "rate_limited"
    assert "Authorization" not in attempt.model_dump_json()


def test_validation_enforces_hashes_reviews_quotas_and_independent_incidents(
    tmp_path: Path,
) -> None:
    store = corpus_fixture(tmp_path)
    report = validate_corpus(store)
    assert report.valid
    assert all(item.accepted_sources == 2 for item in report.countries)
    assert all(item.reviewed_shared_incidents == 1 for item in report.countries)

    payload = tmp_path / "sources" / "BGD-S001" / "content.html"
    payload.write_text("changed", encoding="utf-8")
    broken = validate_corpus(store)
    assert not broken.valid
    assert {item.code for item in broken.issues} >= {"artifact_hash", "artifact_size"}


def test_unavailable_sources_do_not_satisfy_country_or_incident_quota(tmp_path: Path) -> None:
    store = corpus_fixture(tmp_path)
    source_path = tmp_path / "sources" / "ESP-S002" / "source.json"
    source = json.loads(source_path.read_text())
    source["status"] = "unavailable"
    source["latest_review_id"] = None
    write_json(source_path, source)

    report = validate_corpus(store)
    codes = {item.code for item in report.issues}
    assert "source_quota" in codes
    assert "multi_source_incident" in codes


def test_production_policy_requires_fifty_countries_and_ten_sources(tmp_path: Path) -> None:
    store = corpus_fixture(tmp_path)
    report = validate_corpus(store, CorpusPolicy())
    codes = [item.code for item in report.issues]
    assert "country_quota" in codes
    assert codes.count("source_quota") == 2


def test_accepted_duplicate_canonical_urls_are_rejected(tmp_path: Path) -> None:
    store = corpus_fixture(tmp_path)
    first_path = tmp_path / "sources" / "BGD-S001" / "source.json"
    second_path = tmp_path / "sources" / "BGD-S002" / "source.json"
    first = json.loads(first_path.read_text())
    second = json.loads(second_path.read_text())
    second["canonical_url"] = first["canonical_url"]
    second["verification_links"] = first["verification_links"]
    write_json(second_path, second)
    review_path = tmp_path / "reviews" / "BGD-S002.jsonl"
    review = json.loads(review_path.read_text())
    review["link_checks"][0]["url"] = first["canonical_url"]
    review_path.write_text(json.dumps(review) + "\n", encoding="utf-8")

    report = validate_corpus(store)
    assert "accepted_duplicate_url" in {item.code for item in report.issues}


def test_materializer_is_current_ingest_compatible_deterministic_and_gold_free(
    tmp_path: Path,
) -> None:
    store = corpus_fixture(tmp_path / "corpus")
    output = tmp_path / "materialized"
    first = materialize_corpus(store, output)
    second = materialize_corpus(store, output)
    assert first == second
    assert materialization_digest(first) == materialization_digest(second)
    assert first.source_count == 4

    rows = discover(output)
    assert [row["kind"] for row in rows].count("html") == 2
    assert [row["kind"] for row in rows].count("video_analysis") == 2
    assert [row["kind"] for row in rows].count("image_analysis") == 1

    html_row = next(row for row in rows if row["kind"] == "html")
    parsed = parse_html(
        Path(html_row["absolute_path"]),
        str(html_row["relative_path"]),
        Path(str(html_row["source_info_path"])),
    )
    assert parsed.source.source_uri and parsed.source.source_uri.startswith("https://")
    assert parsed.source.country_code in {"BGD", "ESP"}
    assert parsed.source.country and parsed.source.country.startswith("Fixture")
    assert parsed.source.languages == ["en"]
    assert parsed.source.timezone == "Etc/UTC"
    assert parsed.source.published_at == datetime(2026, 8, 12, tzinfo=UTC)
    assert parsed.source.source_metadata["traffic_incident"] is True
    assert parsed.source.source_metadata["traffic_keywords"] == ["crash", "collision"]
    assert parsed.blocks

    metadata = (output / "_corpus_materialization.json").read_text()
    metadata += "".join(path.read_text() for path in output.rglob("SOURCE_INFO.md"))
    for code in ("BGD", "ESP"):
        assert f"{code}-INC-001" not in metadata
        assert f"private gold note for {code}" not in metadata
    assert "reviewed_same_incident" not in metadata
    assert "gold-reviewer" not in metadata


def test_store_lock_and_report_are_deterministic(tmp_path: Path) -> None:
    store = corpus_fixture(tmp_path)
    first_lock = store.build_lock()
    second_lock = store.build_lock()
    assert first_lock == second_lock
    assert first_lock.entries == sorted(first_lock.entries, key=lambda item: item.path)
    report = render_validation_report(validate_corpus(store))
    assert "Status: **VALID**" in report
    assert "| BGD | 2 | 2 | 1 |" in report
