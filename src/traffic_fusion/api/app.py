from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from traffic_fusion.api.moderation import (
    MAX_UPLOAD_BYTES,
    SESSION_COOKIE,
    LoginInput,
    ReviewInput,
    SubmissionStore,
    authenticate,
    combined_scraps,
    create_session,
    materialize_submission,
    publish_pipeline_output,
    remove_materialized_submission,
    require_reviewer,
)
from traffic_fusion.config import Settings
from traffic_fusion.models import (
    EvidenceItem,
    FusedIncident,
    ParsedBlock,
    ProviderRun,
    SourceRecord,
)
from traffic_fusion.pipeline import run_pipeline
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


def create_app(
    data_dir: Path | None = None,
    settings: Settings | None = None,
    base_scraps_dir: Path | None = None,
) -> FastAPI:
    configured_data_dir = (
        os.getenv("MGEOAI_DATA_DIR")
        or os.getenv("TRAFFIC_FUSION_DATA_DIR")
        or "outputs/demo"
    )
    root = data_dir or Path(configured_data_dir)
    runtime_settings = settings or Settings.load()
    configured_base_scraps = (
        os.getenv("MGEOAI_BASE_SCRAPS_DIR") or "assets/scraps"
    )
    base_scraps = base_scraps_dir or Path(configured_base_scraps)
    submissions = SubmissionStore(root)
    pipeline_lock = threading.Lock()
    review_lock = threading.Lock()
    approval_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mgeoai-approval")
    app = FastAPI(
        title="MGeoAI API",
        version="0.2.2",
        description="Evidence-fusion API; records are attributed reports, not independently verified truth.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        allow_credentials=True,
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

    def load_approved_submission(submission_id: str, reviewer: str) -> None:
        with pipeline_lock:
            record = submissions.get(submission_id)
            if record.get("status") != "processing":
                return
            runtime_persisted = False
            try:
                with tempfile.TemporaryDirectory(
                    prefix=".mgeoai-review-", dir=root.parent
                ) as temporary:
                    staging_root = Path(temporary)
                    materialize_submission(root, staging_root, record)
                    pipeline_output = staging_root / "pipeline"
                    existing_cache = root / "cache"
                    if existing_cache.is_dir():
                        shutil.copytree(existing_cache, pipeline_output / "cache")
                    with combined_scraps(
                        base_scraps,
                        root / "runtime_scraps",
                        staging_root / "runtime_scraps",
                    ) as input_dir:
                        summary = run_pipeline(
                            input_dir,
                            pipeline_output,
                            runtime_settings.provider,
                            runtime_settings,
                        )
                    if summary.status == "failed":
                        raise RuntimeError(
                            f"Pipeline run {summary.run_id} finished with failed status"
                        )
                    materialize_submission(root, root, record)
                    runtime_persisted = True
                    publish_pipeline_output(pipeline_output, root)
            except Exception as exc:
                if runtime_persisted:
                    remove_materialized_submission(root, record)
                safe_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                submissions.update(
                    submission_id, status="ingest_failed", ingest_error=safe_error
                )
                submissions.add_audit(
                    submission_id,
                    action="ingest_failed",
                    actor=reviewer,
                    detail=safe_error,
                )
                return

            submission_type = record.get("submission_type")
            runtime_prefix = f"runtime/html/{submission_id}/"
            runtime_video = f"runtime/youtube/{submission_id}.json"
            loaded_source_ids = [
                source.source_id
                for source in source_records()
                if (
                    source.local_path.startswith(runtime_prefix)
                    if submission_type == "html_bundle"
                    else source.local_path == runtime_video
                    if submission_type == "video_json"
                    else source.local_path == f"runtime/html/{submission_id}/content.html"
                )
            ]
            loaded_incident_ids = sorted(
                {
                    incident.incident_id
                    for incident in incidents()
                    if set(incident.source_ids).intersection(loaded_source_ids)
                }
            )
            submissions.update(
                submission_id,
                status="approved",
                pipeline_run_id=summary.run_id,
                loaded_source_ids=loaded_source_ids,
                loaded_incident_ids=loaded_incident_ids,
                ingest_error=None,
            )
            submissions.add_audit(
                submission_id, action="loaded", actor=reviewer, detail=summary.run_id
            )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        run = _read_json(root / "run.json", {})
        return {
            "status": "ok" if (root / "incidents.json").exists() else "no_data",
            "data_dir": str(root),
            "run": run,
        }

    @app.post("/api/submissions", status_code=201)
    async def create_submission(
        submission_type: Annotated[Literal["html_bundle", "video_json"], Form()],
        package: Annotated[UploadFile, File()],
        submitter_name: Annotated[str | None, Form(max_length=120)] = None,
    ) -> dict[str, object]:
        payload = bytearray()
        try:
            while chunk := await package.read(1024 * 1024):
                payload.extend(chunk)
                if len(payload) > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Uploads are limited to 25 MB")
        finally:
            await package.close()
        record = submissions.create_upload(
            submission_type,
            package.filename or "",
            bytes(payload),
            submitter_name,
        )
        return {
            "submission_id": record["submission_id"],
            "status": record["status"],
            "submitted_at": record["submitted_at"],
        }

    @app.get("/api/submissions/{submission_id}/status")
    def submission_status(submission_id: str) -> dict[str, object]:
        record = submissions.get(submission_id)
        return {
            "submission_id": record["submission_id"],
            "status": record["status"],
            "submitted_at": record["submitted_at"],
            "reviewed_at": record["reviewed_at"],
        }

    @app.post("/api/reviewer/login")
    def reviewer_login(payload: LoginInput) -> JSONResponse:
        if not authenticate(payload.username, payload.password):
            raise HTTPException(status_code=401, detail="Invalid reviewer credentials")
        token, csrf_token = create_session(payload.username)
        response = JSONResponse(
            {"username": payload.username, "csrf_token": csrf_token}
        )
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=8 * 60 * 60,
            httponly=True,
            secure=os.getenv("MGEOAI_SECURE_COOKIES", "false").lower() == "true",
            samesite="lax",
            path="/",
        )
        return response

    @app.get("/api/reviewer/me")
    def reviewer_me(request: Request) -> dict[str, str]:
        username, csrf_token = require_reviewer(request)
        return {"username": username, "csrf_token": csrf_token}

    @app.post("/api/reviewer/logout")
    def reviewer_logout(request: Request) -> JSONResponse:
        require_reviewer(request, csrf=True)
        response = JSONResponse({"status": "logged_out"})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/api/reviewer/submissions")
    def review_submissions(
        request: Request,
        status: str | None = Query(None, pattern="^(pending|processing|approved|rejected|ingest_failed)$"),
    ) -> dict[str, object]:
        require_reviewer(request)
        rows = submissions.list(status)
        return {"items": rows, "total": len(rows)}

    @app.get("/api/reviewer/submissions/{submission_id}/download")
    def reviewer_download(submission_id: str, request: Request) -> FileResponse:
        require_reviewer(request)
        record = submissions.get(submission_id)
        response = FileResponse(
            submissions.original_path(record),
            media_type=str(record.get("content_type") or "application/octet-stream"),
            filename=str(record.get("original_filename") or "submission"),
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/reviewer/submissions/{submission_id}/files/{file_id}")
    def reviewer_file(
        submission_id: str, file_id: str, request: Request
    ) -> PlainTextResponse:
        require_reviewer(request)
        record = submissions.get(submission_id)
        path, _ = submissions.review_file_path(record, file_id)
        response = PlainTextResponse(path.read_text(encoding="utf-8"))
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response

    @app.post("/api/reviewer/submissions/{submission_id}/review")
    def review_submission(
        submission_id: str, payload: ReviewInput, request: Request
    ) -> JSONResponse:
        reviewer, _ = require_reviewer(request, csrf=True)
        with review_lock:
            record = submissions.get(submission_id)
            if record.get("status") not in {"pending", "ingest_failed"}:
                raise HTTPException(status_code=409, detail="Submission has already been reviewed")
            reviewed_at = datetime.now(UTC).isoformat()
            if payload.decision == "reject":
                submissions.update(
                    submission_id,
                    status="rejected",
                    reviewed_by=reviewer,
                    reviewed_at=reviewed_at,
                    review_note=payload.note,
                    ingest_error=None,
                )
                rejected = submissions.add_audit(
                    submission_id, action="rejected", actor=reviewer, detail=payload.note
                )
                return JSONResponse(content=rejected)

            submissions.update(
                submission_id,
                status="processing",
                reviewed_by=reviewer,
                reviewed_at=reviewed_at,
                review_note=payload.note,
                ingest_error=None,
            )
            queued = submissions.add_audit(
                submission_id, action="approved_for_ingest", actor=reviewer, detail=payload.note
            )
            try:
                approval_executor.submit(load_approved_submission, submission_id, reviewer)
            except Exception as exc:
                safe_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                submissions.update(
                    submission_id, status="ingest_failed", ingest_error=safe_error
                )
                submissions.add_audit(
                    submission_id,
                    action="ingest_failed",
                    actor=reviewer,
                    detail=safe_error,
                )
                raise HTTPException(
                    status_code=503,
                    detail="Approval could not be queued and can be retried",
                ) from exc
            return JSONResponse(status_code=202, content=queued)

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
