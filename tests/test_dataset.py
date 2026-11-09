from __future__ import annotations

import json
from pathlib import Path

import pytest

from traffic_fusion.extraction.annotation_store import ArticleStore
from traffic_fusion.extraction.dataset import _scan_for_leaks
from traffic_fusion.extraction.reproduce import incidents_geojson, materialise
from traffic_fusion.extraction.scoring import annotation_stats, build_reference, model_metrics


def _jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")


def _accident(fatalities: int) -> dict[str, object]:
    return {"accident": True, "fatalities": fatalities, "casualities": 3, "vehicles": ["bus"], "date": "2025-01-02",
            "country": "Bangladesh", "location": "Dhaka", "coordinates": None}


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    _jsonl(data / "articles.jsonl", [
        {"article_id": a, "url": f"https://x/{a}", "publisher": "P", "title": "T", "published_at": None, "language": "en",
         "collection_country": "Bangladesh", "region": "asia", "reference_group_id": "g1"} for a in ("a1", "a2")])
    _jsonl(data / "annotations.jsonl", [
        {"article_id": a, "annotator": who, "revision": 1, "unusable": False, "accidents": [_accident(2)], "images": []}
        for a in ("a1", "a2") for who in ("annotator_1", "annotator_2")])
    _jsonl(data / "model_extractions.jsonl", [
        {"run_id": "p__m__markdown__txt", "provider": "p", "model": "m", "input_set": "markdown", "with_images": False,
         "with_meta": False, "article_id": a, "status": "ok", "accidents": [_accident(2 if a == "a1" else 5)],
         "quote_check": {"quotes": 0, "verbatim": 0}} for a in ("a1", "a2")])
    _jsonl(data / "grouping_pairs.jsonl", [])
    _jsonl(data / "grouping_pair_predictions.jsonl", [])
    _jsonl(data / "grouping_clusters.jsonl", [])
    _jsonl(data / "incidents.jsonl", [
        {"incident_id": "i1", "article_ids": ["a1", "a2"], "headline": "h", "summary": "s", "when": "2025-01-02", "killed": 2,
         "vehicles": ["bus"], "geo": {"longitude": 90.4, "latitude": 23.8, "granularity": "city", "uncertainty_radius_km": 5}},
        {"incident_id": "i2", "article_ids": ["a1"], "headline": "h", "summary": "s", "geo": None}])
    (data / "grouping_meta.json").write_text(json.dumps({
        "seed": 1, "decision_rule": "r", "population": {}, "total_articles": 2, "pairs_sha256": "0" * 64, "positive_pairs": 0,
        "negative_pairs": 0, "extraction_run_used_for_model_fields": "x", "human_record_from": {},
        "human_order": ["annotator_1", "annotator_2"]}), "utf-8")
    return tmp_path


def test_materialised_root_gives_scores_without_article_text(dataset: Path, tmp_path: Path) -> None:
    root = tmp_path / "root"
    materialise(dataset, root)
    assert not list(root.rglob("article.md"))
    store = ArticleStore(root)
    stats = annotation_stats(store)
    assert stats["articles_with_2plus_labels"] == 2
    assert stats["field_exact_agreement"]["fatalities"]["rate"] == 1.0
    labels = store.all_latest()
    metrics = model_metrics(root / "runs" / "p__m__markdown__txt", build_reference(labels), store, labels)
    assert metrics["fields_exact"]["fatalities"]["value"] == 0.5


def test_incident_map_keeps_only_placed_incidents(dataset: Path) -> None:
    geo = incidents_geojson(dataset)
    assert geo["meta"] == {"records": 2, "mapped": 1, "verified": False}
    assert geo["features"][0]["geometry"]["coordinates"] == [90.4, 23.8]
    assert len(geo["features"][0]["properties"]["articles"]) == 2


def test_leak_scan_catches_account_names_and_article_text(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.jsonl").write_text('{"annotator": "annotator_1"}\n', "utf-8")
    assert _scan_for_leaks(tmp_path, ["oishik"]) is None
    (tmp_path / "data" / "a.jsonl").write_text('{"by": "Oishik"}\n', "utf-8")
    assert "account name" in (_scan_for_leaks(tmp_path, ["oishik"]) or "")
    (tmp_path / "data" / "a.jsonl").write_text('{"markdown": "body"}\n', "utf-8")
    assert "article text" in (_scan_for_leaks(tmp_path, ["oishik"]) or "")
