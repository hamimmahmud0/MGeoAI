from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from traffic_fusion.pipeline import run_pipeline


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_report_01_bundle_maps_baniacho_and_pairs_image(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    fixture = root / "assets/submission_test/html_scrap_bundle/report_01.zip"
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    with ZipFile(fixture) as archive:
        archive.extractall(input_dir)

    summary = run_pipeline(input_dir, output_dir, "recorded")

    assert summary.status == "completed"
    sources = _read_jsonl(output_dir / "sources.jsonl")
    html_source = next(item for item in sources if item["source_type"] == "news_html")
    image_source = next(item for item in sources if item["source_type"] == "image_analysis")
    evidence = _read_jsonl(output_dir / "evidence.jsonl")
    html_evidence = [item for item in evidence if item["source_id"] == html_source["source_id"]]
    assert any(
        "Baniacho, Shahrasti, Chandpur" in item["location_mentions"]
        for item in html_evidence
    )

    incidents = json.loads((output_dir / "incidents.json").read_text())
    assert len(incidents) == 1
    incident = incidents[0]
    assert set(incident["source_ids"]) == {
        html_source["source_id"],
        image_source["source_id"],
    }
    assert incident["title"] == "Bus–truck collision in Baniacho, Shahrasti"
    assert incident["geolocation"]["display_name"] == "Baniacho, Shahrasti, Chandpur"
    assert incident["geolocation"]["granularity"] == "area"
    assert incident["geolocation"]["uncertainty_radius_km"] == 3.0

    geojson = json.loads((output_dir / "incidents.geojson").read_text())
    assert len(geojson["features"]) == 1
    assert geojson["features"][0]["geometry"]["coordinates"] == [90.968507, 23.253908]
