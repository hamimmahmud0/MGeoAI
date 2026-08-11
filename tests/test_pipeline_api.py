from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from traffic_fusion.api.app import create_app
from traffic_fusion.pipeline import run_pipeline


@pytest.fixture(scope="module")
def demo_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("demo")
    root = Path(__file__).parents[1]
    summary = run_pipeline(root / "assets/scraps", output, "recorded")
    assert summary.status == "completed"
    return output


def test_full_recorded_pipeline_splits_roundup_and_merges_sources(demo_dir: Path) -> None:
    incidents = json.loads((demo_dir / "incidents.json").read_text())
    titles = {item["title"] for item in incidents}
    assert "Passenger-bus collision in Osmaninagar, Sylhet" in titles
    assert "Bus crash involving labourers in Sherpur, Bogura" in titles
    assert any(item["independent_source_count"] >= 3 for item in incidents)
    assert all("RECORDED DEMO" in item["data_quality_warnings"][0] for item in incidents)


def test_pipeline_outputs_markdown_blocks_and_schema(demo_dir: Path) -> None:
    assert len(list((demo_dir / "sources").glob("*/content.md"))) == 13
    assert all(
        (path.parent / "blocks.json").exists()
        for path in (demo_dir / "sources").glob("*/content.md")
    )
    assert (Path(__file__).parents[1] / "schemas/FusedIncident.schema.json").exists()


def test_api_filters_paginates_and_returns_detail(demo_dir: Path) -> None:
    client = TestClient(create_app(demo_dir))
    page = client.get("/api/incidents", params={"severity": "critical", "page_size": 1}).json()
    assert page["page_size"] == 1
    assert page["total"] >= 1
    detail = client.get(f"/api/incidents/{page['items'][0]['incident_id']}")
    assert detail.status_code == 200
    assert detail.json()["evidence_ids"]


def test_api_bbox_geojson_and_unmapped_access(demo_dir: Path) -> None:
    client = TestClient(create_app(demo_dir))
    geo = client.get("/api/incidents.geojson", params={"bbox": "90,23,91,25"}).json()
    assert geo["type"] == "FeatureCollection"
    assert all(feature["geometry"]["coordinates"][0] >= 90 for feature in geo["features"])
    page = client.get("/api/incidents", params={"page_size": 200}).json()
    assert any(not item["mapped"] for item in page["items"])


def test_health_sources_and_runs(demo_dir: Path) -> None:
    client = TestClient(create_app(demo_dir))
    assert client.get("/openapi.json").json()["info"]["title"] == "MGeoAI API"
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/sources").json()["total"] == 21
    runs = client.get("/api/runs").json()
    assert runs["total"] > 0
    assert {item["provider"] for item in runs["items"]} == {"recorded"}


def test_api_exposes_safe_source_content_and_incident_evidence(demo_dir: Path) -> None:
    client = TestClient(create_app(demo_dir))
    source = client.get("/api/sources").json()["items"][0]
    detail = client.get(f"/api/sources/{source['source_id']}")
    assert detail.status_code == 200
    assert detail.json()["content"]
    assert detail.json()["blocks"]
    assert detail.json()["evidence"]
    assert detail.json()["source_id"] == source["source_id"]

    incident = client.get("/api/incidents", params={"page_size": 1}).json()["items"][0]
    evidence = client.get(f"/api/incidents/{incident['incident_id']}/evidence")
    assert evidence.status_code == 200
    assert evidence.json()["items"]
    assert set(item["evidence_id"] for item in evidence.json()["items"]) == set(
        incident["evidence_ids"]
    )
    assert evidence.json()["sources"]


def test_source_and_evidence_detail_return_not_found(demo_dir: Path) -> None:
    client = TestClient(create_app(demo_dir))
    assert client.get("/api/sources/src_missing").status_code == 404
    assert client.get("/api/incidents/inc_missing/evidence").status_code == 404


def test_rerun_removes_stale_generated_incident(demo_dir: Path) -> None:
    stale = demo_dir / "incidents" / "inc_stale_fixture"
    stale.mkdir(parents=True)
    (stale / "incident.json").write_text("{}")
    root = Path(__file__).parents[1]
    run_pipeline(root / "assets/scraps", demo_dir, "recorded")
    assert not stale.exists()
    assert len(list((demo_dir / "incidents").glob("*/incident.json"))) == 6
