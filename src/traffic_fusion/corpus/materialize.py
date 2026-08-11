from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pydantic import Field

from traffic_fusion.corpus.models import CorpusPolicy, SourceStatus, StrictCorpusModel
from traffic_fusion.corpus.store import CorpusStore
from traffic_fusion.corpus.validation import validate_corpus


class MaterializedSource(StrictCorpusModel):
    corpus_source_id: str
    relative_paths: list[str] = Field(min_length=1)


class MaterializationResult(StrictCorpusModel):
    corpus_id: str
    source_count: int
    files: list[str]
    sources: list[MaterializedSource]


def _write_identical(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.is_symlink() or path.read_bytes() != content:
            raise ValueError(f"materialization target conflicts with existing path: {path}")
        return
    path.write_bytes(content)


def _source_info(
    source_id: str,
    publisher: str,
    canonical_url: str,
    country: str,
    country_code: str,
    languages: list[str],
    timezone: str,
    published_at: datetime | None,
    traffic_incident: bool,
    traffic_keywords: list[str],
    payload_hash: str,
    verification_links: list[tuple[str, str]],
) -> bytes:
    metadata: dict[str, object] = {
        "languages": languages,
        "timezone": timezone,
        "country": country,
        "country_code": country_code,
        "traffic_incident": traffic_incident,
        "traffic_keywords": traffic_keywords,
    }
    if published_at:
        metadata["published_at"] = published_at.isoformat()
    lines = ["---"]
    lines.extend(
        f"{key}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in metadata.items()
    )
    lines.extend([
        "---",
        f"Source name: {publisher}",
        f"News link: {canonical_url}",
        f"Corpus source ID: {source_id}",
        f"Payload SHA-256: {payload_hash}",
    ])
    lines.extend(f"Verification link ({rel}): {url}" for rel, url in verification_links)
    return ("\n".join(lines) + "\n").encode()


def materialize_corpus(
    store: CorpusStore,
    output_dir: Path,
    *,
    policy: CorpusPolicy | None = None,
    require_valid: bool = True,
) -> MaterializationResult:
    """Emit only accepted payloads and non-gold source metadata in scrap format."""
    report = validate_corpus(store, policy)
    if require_valid and not report.valid:
        codes = ", ".join(sorted({item.code for item in report.issues}))
        raise ValueError(f"cannot materialize invalid corpus: {codes}")

    manifest = store.manifest()
    gold_ids = [item.curation_incident_id for item in store.incidents()]
    country_names = {item.country_code: item.name for item in store.countries()}
    materialized: list[MaterializedSource] = []
    generated_files: list[str] = []
    for source in sorted(store.sources(), key=lambda item: item.corpus_source_id):
        if source.status != SourceStatus.ACCEPTED or not source.traffic_incident:
            continue
        artifact_by_role = {item.role: item for item in source.artifacts}
        paths: list[str] = []
        if "html" in artifact_by_role:
            base = Path("html") / source.country_code / source.corpus_source_id
            html_artifact = artifact_by_role["html"]
            html_path = base / "content.html"
            _write_identical(
                output_dir / html_path,
                store.artifact_path(source, html_artifact.path).read_bytes(),
            )
            paths.append(html_path.as_posix())
            info_path = base / "SOURCE_INFO.md"
            info_content = _source_info(
                source.corpus_source_id,
                source.publisher,
                source.canonical_url,
                country_names[source.country_code],
                source.country_code,
                source.languages,
                source.timezone,
                source.published_at,
                source.traffic_incident,
                source.traffic_keywords,
                html_artifact.sha256,
                [(item.rel, item.url) for item in source.verification_links],
            )
            leaked = [item for item in gold_ids if item.encode() in info_content]
            if leaked:
                raise ValueError(
                    f"gold incident identifiers leaked into materialized metadata: {leaked}"
                )
            _write_identical(
                output_dir / info_path,
                info_content,
            )
            paths.append(info_path.as_posix())
            image_artifact = artifact_by_role.get("image_analysis")
            if image_artifact:
                image_path = base / "image_01.json"
                _write_identical(
                    output_dir / image_path,
                    store.artifact_path(source, image_artifact.path).read_bytes(),
                )
                paths.append(image_path.as_posix())
        else:
            video_artifact = artifact_by_role["video_analysis"]
            video_path = (
                Path(source.country_code)
                / source.corpus_source_id
                / "youtube"
                / "video.json"
            )
            _write_identical(
                output_dir / video_path,
                store.artifact_path(source, video_artifact.path).read_bytes(),
            )
            paths.append(video_path.as_posix())
        materialized.append(
            MaterializedSource(corpus_source_id=source.corpus_source_id, relative_paths=paths)
        )
        generated_files.extend(paths)

    result = MaterializationResult(
        corpus_id=manifest.corpus_id,
        source_count=len(materialized),
        files=sorted(generated_files),
        sources=materialized,
    )
    # This manifest deliberately contains source IDs and paths only. Curation incident
    # IDs, labels, reviewer notes, and gold memberships are never materialized.
    marker = output_dir / "_corpus_materialization.json"
    marker_content = (result.model_dump_json(indent=2) + "\n").encode()
    _write_identical(marker, marker_content)

    generated_metadata = marker_content + b"".join(
        (output_dir / path).read_bytes()
        for path in result.files
        if path.endswith("SOURCE_INFO.md")
    )
    leaked = [item for item in gold_ids if item.encode() in generated_metadata]
    if leaked:
        raise ValueError(f"gold incident identifiers leaked into materialized metadata: {leaked}")
    return result


def materialization_digest(result: MaterializationResult) -> str:
    """Return a stable digest useful in external build/release records."""
    raw = json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()
