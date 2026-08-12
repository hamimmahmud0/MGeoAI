from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from traffic_fusion.corpus.build import CollectedCandidate, build_corpus
from traffic_fusion.corpus.discovery import load_country_profiles
from traffic_fusion.corpus.store import CorpusStore
from traffic_fusion.corpus.validation import validate_corpus


def test_builds_production_quota_corpus_with_links_and_coverage(tmp_path: Path) -> None:
    profiles = load_country_profiles(Path("configs/global_countries.toml"))
    candidates: list[CollectedCandidate] = []
    now = datetime(2026, 8, 12, tzinfo=UTC)
    for iso2, profile in profiles.items():
        for index in range(10):
            domain = f"news{index}.{iso2.casefold()}.example"
            candidates.append(
                CollectedCandidate(
                    country_iso2=iso2,
                    canonical_url=f"https://{domain}/traffic/report-{index}",
                    title=f"{profile.name} traffic collision report {index}",
                    publisher=f"Publisher {iso2} {index}",
                    domain=domain,
                    excerpt=(
                        f"Publisher report {index} describes a road traffic collision in "
                        f"{profile.name}."
                    ),
                    languages=[profile.languages[0]],
                    published_at=now,
                    discovered_at=now,
                    discovered_via="offline_fixture",
                    discovery_url=f"https://{domain}/feed",
                    access_status="feed_metadata_match",
                    incident_key=f"{iso2}-shared-event" if index < 2 else None,
                    pair_confidence=0.9 if index < 2 else None,
                    pair_reason="Matching date, place, and casualties" if index < 2 else None,
                )
            )

    result = build_corpus(candidates, profiles, tmp_path / "global-v1", created_at=now)

    assert result.countries == 51
    assert result.accepted_sources == 510
    assert result.multi_source_incidents == 51
    store = CorpusStore(tmp_path / "global-v1")
    report = validate_corpus(store)
    assert report.valid
    assert {item.review_method for item in store.incidents()} == {"automated"}
    assert {item.review_method for item in store.reviews()} == {"automated"}
    payload = next((tmp_path / "global-v1" / "sources").glob("*/content.html"))
    assert "short public-feed metadata excerpt" in payload.read_text(encoding="utf-8")
    assert "Original source:" in payload.read_text(encoding="utf-8")
    with Path(result.links_report).open(newline="", encoding="utf-8") as handle:
        links = list(csv.DictReader(handle))
    assert len(links) == 510
    assert all(row["manual_verification_url"].startswith("https://") for row in links)
    assert all(row["title"] for row in links)
    assert {row["event_country_status"] for row in links} == {
        "not_verified_collection_country_only"
    }
    coverage = Path(result.coverage_geojson).read_text(encoding="utf-8")
    assert '"is_incident_location": false' in coverage
    assert "collection-country source coverage" in coverage
    catalog = Path(result.news_sources_report).read_text(encoding="utf-8")
    assert catalog.count("[Open discovery record]") == 510
    assert catalog.count("## ") == 52
    assert "## Datasource details" in catalog
    assert "[United States traffic collision report 0]" in catalog
