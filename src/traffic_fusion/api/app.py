from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from traffic_fusion.models import (
    EvidenceItem,
    FusedIncident,
    ParsedBlock,
    ProviderRun,
    SourceRecord,
)
from traffic_fusion.reporting import incident_to_geojson


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _severity(incident: FusedIncident) -> str:
    fatalities = next(
        (
            fact.value
            for fact in incident.facts
            if fact.field == "fatalities" and isinstance(fact.value, int)
        ),
        0,
    )
    injuries = next(
        (
            fact.value
            for fact in incident.facts
            if fact.field == "injuries" and isinstance(fact.value, int)
        ),
        0,
    )
    if fatalities >= 5:
        return "critical"
    if fatalities > 0:
        return "high"
    if injuries > 0:
        return "medium"
    return "unknown"


def _bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    try:
        parts = tuple(float(item) for item in value.split(","))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="bbox must contain west,south,east,north"
        ) from exc
    if len(parts) != 4:
        raise HTTPException(status_code=422, detail="bbox must contain west,south,east,north")
    return parts


def _filter(
    incidents: list[FusedIncident],
    bbox: str | None,
    from_date: str | None,
    to_date: str | None,
    event_type: str | None,
    severity: str | None,
    confidence: float | None,
    source_count: int | None,
    sentiment: str | None,
    search: str | None,
) -> list[FusedIncident]:
    bounds = _bbox(bbox)
    result = []
    for item in incidents:
        if event_type and item.event_type != event_type:
            continue
        if severity and _severity(item) != severity:
            continue
        if confidence is not None and item.geolocation.confidence < confidence:
            continue
        if source_count is not None and item.independent_source_count < source_count:
            continue
        if sentiment and sentiment not in {entry.polarity for entry in item.sentiment.items}:
            continue
        if search and search.casefold() not in (item.title + " " + item.human_summary).casefold():
            continue
        start = item.event_time.start.date().isoformat() if item.event_time.start else None
        if from_date and (not start or start < from_date):
            continue
        if to_date and (not start or start > to_date):
            continue
        if bounds:
            lon, lat = item.geolocation.longitude, item.geolocation.latitude
            if (
                lon is not None
                and lat is not None
                and not (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3])
            ):
                continue
        result.append(item)
    return result


def create_app(data_dir: Path | None = None) -> FastAPI:
    configured_data_dir = (
        os.getenv("MGEOAI_DATA_DIR")
        or os.getenv("TRAFFIC_FUSION_DATA_DIR")
        or "outputs/demo"
    )
    root = data_dir or Path(configured_data_dir)
    app = FastAPI(
        title="MGeoAI API",
        version="0.1.0",
        description="Evidence-fusion API; records are attributed reports, not independently verified truth.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    def incidents() -> list[FusedIncident]:
        return [
            FusedIncident.model_validate(item) for item in _read_json(root / "incidents.json", [])
        ]

    def source_records() -> list[SourceRecord]:
        return [SourceRecord.model_validate(item) for item in _read_jsonl(root / "sources.jsonl")]

    def evidence_items() -> list[EvidenceItem]:
        return [EvidenceItem.model_validate(item) for item in _read_jsonl(root / "evidence.jsonl")]

    def incident_links() -> dict[str, list[str]]:
        links: dict[str, list[str]] = {}
        for incident in incidents():
            for source_id in incident.source_ids:
                links.setdefault(source_id, []).append(incident.incident_id)
        return links

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        run = _read_json(root / "run.json", {})
        return {
            "status": "ok" if (root / "incidents.json").exists() else "no_data",
            "data_dir": str(root),
            "run": run,
        }

    @app.get("/api/incidents")
    def list_incidents(
        bbox: str | None = None,
        from_date: str | None = Query(None, alias="from"),
        to_date: str | None = Query(None, alias="to"),
        event_type: str | None = Query(None, alias="type"),
        severity: str | None = None,
        confidence: float | None = Query(None, ge=0, le=1),
        source_count: int | None = Query(None, ge=1),
        sentiment: str | None = None,
        search: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        filtered = _filter(
            incidents(),
            bbox,
            from_date,
            to_date,
            event_type,
            severity,
            confidence,
            source_count,
            sentiment,
            search,
        )
        start = (page - 1) * page_size
        items = []
        for item in filtered[start : start + page_size]:
            row = item.model_dump(mode="json")
            row["severity"] = _severity(item)
            row["mapped"] = item.geolocation.longitude is not None
            items.append(row)
        return {"items": items, "total": len(filtered), "page": page, "page_size": page_size}

    @app.get("/api/incidents.geojson")
    def geojson(
        bbox: str | None = None,
        from_date: str | None = Query(None, alias="from"),
        to_date: str | None = Query(None, alias="to"),
        event_type: str | None = Query(None, alias="type"),
        severity: str | None = None,
        confidence: float | None = Query(None, ge=0, le=1),
        source_count: int | None = Query(None, ge=1),
        sentiment: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        filtered = _filter(
            incidents(),
            bbox,
            from_date,
            to_date,
            event_type,
            severity,
            confidence,
            source_count,
            sentiment,
            search,
        )
        return {
            "type": "FeatureCollection",
            "features": [feature for item in filtered if (feature := incident_to_geojson(item))],
        }

    @app.get("/api/incidents/{incident_id}")
    def incident_detail(incident_id: str) -> dict[str, Any]:
        item = next((item for item in incidents() if item.incident_id == incident_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="Incident not found")
        result = item.model_dump(mode="json")
        result["severity"] = _severity(item)
        return result

    @app.get("/api/sources")
    def sources(
        page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)
    ) -> dict[str, Any]:
        rows = [item.model_dump(mode="json") for item in source_records()]
        links = incident_links()
        for row in rows:
            row["linked_incident_ids"] = links.get(str(row["source_id"]), [])
        start = (page - 1) * page_size
        return {
            "items": rows[start : start + page_size],
            "total": len(rows),
            "page": page,
            "page_size": page_size,
        }

    @app.get("/api/sources/{source_id}")
    def source_detail(source_id: str) -> dict[str, Any]:
        record = next((item for item in source_records() if item.source_id == source_id), None)
        if not record:
            raise HTTPException(status_code=404, detail="Source not found")
        sources_root = (root / "sources").resolve()
        source_dir = (sources_root / record.source_id).resolve()
        if source_dir.parent != sources_root:
            raise HTTPException(status_code=404, detail="Source artifacts not found")
        blocks = [
            ParsedBlock.model_validate(item).model_dump(mode="json")
            for item in _read_json(source_dir / "blocks.json", [])
        ]
        result = record.model_dump(mode="json")
        result["linked_incident_ids"] = incident_links().get(record.source_id, [])
        result["content"] = _read_text(source_dir / "content.md")
        result["blocks"] = blocks
        result["evidence"] = [
            item.model_dump(mode="json")
            for item in evidence_items()
            if item.source_id == record.source_id
        ]
        return result

    @app.get("/api/incidents/{incident_id}/evidence")
    def incident_evidence(incident_id: str) -> dict[str, Any]:
        incident = next((item for item in incidents() if item.incident_id == incident_id), None)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        evidence_ids = set(incident.evidence_ids)
        rows = [
            item.model_dump(mode="json")
            for item in evidence_items()
            if item.evidence_id in evidence_ids
        ]
        source_ids = {item["source_id"] for item in rows}
        sources_by_id = {
            item.source_id: item.model_dump(mode="json")
            for item in source_records()
            if item.source_id in source_ids
        }
        return {"items": rows, "sources": sources_by_id}

    @app.get("/api/runs")
    def runs(
        page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)
    ) -> dict[str, Any]:
        rows = [
            ProviderRun.model_validate(item).model_dump(mode="json")
            for item in _read_json(root / "provider_runs.json", [])
        ]
        start = (page - 1) * page_size
        return {
            "items": rows[start : start + page_size],
            "total": len(rows),
            "page": page,
            "page_size": page_size,
        }

    frontend = Path("web/dist")
    if frontend.exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = frontend / path
            return FileResponse(candidate if candidate.is_file() else frontend / "index.html")

    return app


app = create_app()
