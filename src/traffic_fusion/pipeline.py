from __future__ import annotations

import json
import shutil
from pathlib import Path

from traffic_fusion.adapters import adapt_image, adapt_video
from traffic_fusion.config import Settings
from traffic_fusion.fusion.provider import DeepSeekProvider, FusionProvider, ProviderFailure
from traffic_fusion.fusion.recorded import RecordedFusionProvider
from traffic_fusion.ingest.discovery import discover
from traffic_fusion.ingest.html import parse_html, write_parsed_html
from traffic_fusion.matching import build_clusters, decide_pairs, score_pair
from traffic_fusion.models import (
    EvidenceItem,
    FusedIncident,
    IncidentMention,
    PipelineRunSummary,
    SourceRecord,
)
from traffic_fusion.normalize import blocks_to_evidence, extract_sentiment, split_mentions
from traffic_fusion.reporting import (
    incident_to_geojson,
    render_incident_markdown,
    validate_fused_provenance,
)
from traffic_fusion.utils import (
    read_jsonl,
    stable_hash,
    stable_id,
    utc_now,
    write_json,
    write_jsonl,
)


class PipelineFailure(RuntimeError):
    pass


def run_live_smoke(data_dir: Path, output_dir: Path, settings: Settings) -> dict[str, object]:
    """Run one bounded real match and fusion call over an existing normalized demo."""
    sources = [SourceRecord.model_validate(item) for item in read_jsonl(data_dir / "sources.jsonl")]
    evidence = [
        EvidenceItem.model_validate(item) for item in read_jsonl(data_dir / "evidence.jsonl")
    ]
    mentions = [
        IncidentMention.model_validate(item) for item in read_jsonl(data_dir / "mentions.jsonl")
    ]
    if not sources or not evidence or len(mentions) < 2:
        raise PipelineFailure(
            "live smoke requires an existing recorded demo with normalized artifacts"
        )
    grouped: dict[str, list[IncidentMention]] = {}
    for mention in mentions:
        anchor = next((item.hierarchy.get("anchor") for item in mention.locations), None)
        if anchor:
            grouped.setdefault(anchor, []).append(mention)
    selected = next((items for items in grouped.values() if len(items) >= 2), None)
    if not selected:
        raise PipelineFailure("no bounded multi-source cluster is available for live smoke")
    selected = selected[:2]
    provider = DeepSeekProvider(
        settings, Path("assets/mllm_prompts/data_fusion_prompt.md"), output_dir / "cache"
    )
    left, right = selected
    decision = provider.adjudicate(left, right, score_pair(left, right, settings))
    selected_source_ids = {item.source_id for item in selected}
    selected_evidence_ids = {item for mention in selected for item in mention.evidence_ids}
    source_by_id = {item.source_id: item for item in sources}
    evidence_by_id = {item.evidence_id: item for item in evidence}
    bundle = {
        "cluster_id": "live-smoke-cluster",
        "mentions": [item.model_dump(mode="json") for item in selected],
        "sources": [
            source_by_id[item].model_dump(mode="json") for item in sorted(selected_source_ids)
        ],
        "evidence": [
            evidence_by_id[item].model_dump(mode="json") for item in sorted(selected_evidence_ids)
        ],
        "sentiment": [],
        "relevant_markdown_blocks": [
            {"evidence_id": item, "text": evidence_by_id[item].claim_text}
            for item in sorted(selected_evidence_ids)
            if evidence_by_id[item].provenance.block_id
        ],
    }
    incident = provider.fuse("live-smoke-cluster", bundle)
    errors = validate_fused_provenance(incident, selected_evidence_ids, selected_source_ids)
    if errors:
        raise PipelineFailure("live smoke provenance validation failed: " + "; ".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "match.json", decision)
    write_json(output_dir / "incident.json", incident)
    write_json(
        output_dir / "provider_runs.json", [item.model_dump(mode="json") for item in provider.runs]
    )
    usage = {
        "input_tokens": sum(item.input_tokens or 0 for item in provider.runs),
        "output_tokens": sum(item.output_tokens or 0 for item in provider.runs),
        "estimated_cost_usd": round(sum(item.estimated_cost_usd or 0 for item in provider.runs), 8),
    }
    result: dict[str, object] = {
        "status": "passed",
        "scope": "one bounded match adjudication and one cluster fusion",
        "provider": provider.name,
        "model": provider.model,
        "match_decision": decision.decision,
        "incident_id": incident.incident_id,
        "usage": usage,
    }
    write_json(output_dir / "smoke.json", result)
    return result


def export_schemas(schema_dir: Path) -> None:
    schema_dir.mkdir(parents=True, exist_ok=True)
    for model in (SourceRecord, EvidenceItem, IncidentMention, FusedIncident):
        write_json(schema_dir / f"{model.__name__}.schema.json", model.model_json_schema())


def _provider(name: str, settings: Settings, output_dir: Path) -> FusionProvider:
    if name == "recorded":
        return RecordedFusionProvider()
    if name != "deepseek":
        raise PipelineFailure(f"Unsupported fusion provider: {name}")
    return DeepSeekProvider(
        settings, Path("assets/mllm_prompts/data_fusion_prompt.md"), output_dir / "cache"
    )


def run_pipeline(
    input_dir: Path, output_dir: Path, provider_name: str, settings: Settings | None = None
) -> PipelineRunSummary:
    settings = settings or Settings.load()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = discover(input_dir, settings)
    run_id = stable_id(
        "run",
        stable_hash(json.dumps([(row["relative_path"], row["sha256"]) for row in manifest])),
        provider_name,
    )
    started_at = utc_now()
    summary = PipelineRunSummary(
        run_id=run_id,
        mode="recorded" if provider_name == "recorded" else "live",
        provider=provider_name,
        model="recorded-fixture-v2"
        if provider_name == "recorded"
        else settings.deepseek_model or "unconfigured",
        status="running",
        started_at=started_at,
        input_files=len(manifest),
    )
    public_manifest = []
    input_root = input_dir.resolve()
    for row in manifest:
        public_row = {key: value for key, value in row.items() if key != "absolute_path"}
        source_info = row.get("source_info_path")
        if isinstance(source_info, str):
            public_row["source_info_path"] = Path(source_info).relative_to(input_root).as_posix()
        public_manifest.append(public_row)
    write_jsonl(output_dir / "manifest.jsonl", public_manifest)
    sources: list[SourceRecord] = []
    evidence: list[EvidenceItem] = []
    html_source_by_relative: dict[str, str] = {}
    warnings: list[str] = []

    for row in manifest:
        if row["warnings"]:
            warnings.extend(f"{row['relative_path']}: {warning}" for warning in row["warnings"])
            continue
        path = Path(row["absolute_path"])
        try:
            if row["kind"] == "html":
                source_info = Path(row["source_info_path"]) if row.get("source_info_path") else None
                parsed = parse_html(path, row["relative_path"], source_info)
                sources.append(parsed.source)
                html_source_by_relative[row["relative_path"]] = parsed.source.source_id
                write_parsed_html(parsed, output_dir)
                evidence.extend(blocks_to_evidence(parsed.source, parsed.blocks))
            elif row["kind"] == "video_analysis":
                source, items = adapt_video(path, row["relative_path"])
                sources.append(source)
                evidence.extend(items)
            elif row["kind"] == "image_analysis":
                parent_relative = row.get("parent_relative_path")
                parent_id = (
                    html_source_by_relative.get(parent_relative)
                    if isinstance(parent_relative, str)
                    else None
                )
                source, items = adapt_image(path, row["relative_path"], parent_id)
                sources.append(source)
                evidence.extend(items)
        except Exception as exc:  # Per-file isolation is intentional at this boundary.
            warnings.append(f"{row['relative_path']}: {type(exc).__name__}: {exc}")

    # Exact duplicate hashes share a dependency group and do not inflate independence.
    hash_groups: dict[str, list[SourceRecord]] = {}
    for source in sources:
        hash_groups.setdefault(source.content_hash, []).append(source)
    for content_hash, group in hash_groups.items():
        if len(group) > 1:
            for source in group:
                source.dependency_group = f"duplicate:{content_hash[:12]}"
                source.independence = "repost"

    evidence_by_source: dict[str, list[EvidenceItem]] = {}
    for item in evidence:
        evidence_by_source.setdefault(item.source_id, []).append(item)
    mentions = [
        mention
        for source in sources
        for mention in split_mentions(source, evidence_by_source.get(source.source_id, []))
    ]
    mentions_by_source: dict[str, list[IncidentMention]] = {}
    for mention in mentions:
        mentions_by_source.setdefault(mention.source_id, []).append(mention)
    # A paired image may provide bounded contextual evidence even when it does
    # not independently establish time or place. Inherit only from a parent HTML
    # with exactly one incident mention, avoiding ambiguous roundup-image assignment.
    for source in sources:
        if not source.parent_source_id:
            continue
        parents = mentions_by_source.get(source.parent_source_id, [])
        child_evidence = evidence_by_source.get(source.source_id, [])
        if len(parents) != 1 or not child_evidence:
            continue
        parent = parents[0]
        children = mentions_by_source.get(source.source_id, [])
        if not children:
            child = parent.model_copy(deep=True)
            child.mention_id = stable_id("men", source.source_id, parent.mention_id)
            child.source_id = source.source_id
            child.evidence_ids = [item.evidence_id for item in child_evidence]
            children = [child]
            mentions.append(child)
            mentions_by_source[source.source_id] = children
        for child in children:
            if not child.event_time.start:
                child.event_time = parent.event_time.model_copy(deep=True)
            if not child.locations:
                child.locations = [location.model_copy(deep=True) for location in parent.locations]
                for location in child.locations:
                    location.confidence = min(location.confidence, 0.45)
                    location.reason = (
                        "Inherited from the single paired HTML incident; image alone does not "
                        "establish crash location"
                    )
            # The file pairing is the bounded linkage signal. Image-description
            # vocabulary (crowd, wreckage, phones, etc.) must not dilute the
            # parent incident identity during lexical matching.
            child.lexical_features = list(parent.lexical_features)
            inherited_warning = "Incident linkage inherited from paired HTML source"
            if inherited_warning not in child.uncertainty:
                child.uncertainty.append(inherited_warning)
            child.completeness = min(child.completeness, 0.45)
    sentiments = extract_sentiment(evidence)
    write_jsonl(output_dir / "sources.jsonl", sources)
    write_jsonl(output_dir / "evidence.jsonl", evidence)
    write_jsonl(output_dir / "mentions.jsonl", mentions)
    write_jsonl(output_dir / "sentiment.jsonl", sentiments)

    provider = _provider(provider_name, settings, output_dir)
    decisions = decide_pairs(mentions, provider, settings)
    clusters = build_clusters(mentions, decisions)
    write_json(output_dir / "matches.json", [item.model_dump(mode="json") for item in decisions])
    write_json(output_dir / "clusters.json", {"clusters": clusters})

    mention_by_id = {item.mention_id: item for item in mentions}
    source_by_id = {item.source_id: item for item in sources}
    evidence_by_id = {item.evidence_id: item for item in evidence}
    incidents: list[FusedIncident] = []
    failed_clusters: list[dict[str, str]] = []
    for index, cluster in enumerate(clusters, start=1):
        cluster_id = f"cluster-{index:03d}"
        cluster_mentions = [mention_by_id[item] for item in cluster]
        source_ids = {item.source_id for item in cluster_mentions}
        cluster_evidence_ids = {
            evidence_id for item in cluster_mentions for evidence_id in item.evidence_ids
        }
        excerpts = []
        for evidence_id in cluster_evidence_ids:
            evidence_item = evidence_by_id.get(evidence_id)
            if evidence_item and evidence_item.provenance.block_id:
                excerpts.append(
                    {
                        "evidence_id": evidence_id,
                        "block_id": evidence_item.provenance.block_id,
                        "text": evidence_item.claim_text,
                    }
                )
        bundle = {
            "cluster_id": cluster_id,
            "mentions": [item.model_dump(mode="json") for item in cluster_mentions],
            "sources": [source_by_id[item].model_dump(mode="json") for item in sorted(source_ids)],
            "evidence": [
                evidence_by_id[item].model_dump(mode="json")
                for item in sorted(cluster_evidence_ids)
                if item in evidence_by_id
            ],
            "sentiment": [
                item.model_dump(mode="json") for item in sentiments if item.source_id in source_ids
            ],
            "relevant_markdown_blocks": excerpts,
        }
        try:
            incident = provider.fuse(cluster_id, bundle)
            provenance_errors = validate_fused_provenance(
                incident, cluster_evidence_ids, source_ids
            )
            if provenance_errors:
                raise ProviderFailure("; ".join(provenance_errors))
            incidents.append(incident)
            incident_dir = output_dir / "incidents" / incident.incident_id
            write_json(incident_dir / "incident.json", incident)
            (incident_dir / "report.md").write_text(
                render_incident_markdown(incident), encoding="utf-8"
            )
        except ProviderFailure as exc:
            failed_clusters.append(
                {"cluster_id": cluster_id, "error": str(exc), "retryable": "true"}
            )

    features = [feature for incident in incidents if (feature := incident_to_geojson(incident))]
    incident_root = output_dir / "incidents"
    accepted_ids = {incident.incident_id for incident in incidents}
    if incident_root.is_dir():
        for child_path in incident_root.iterdir():
            if (
                child_path.is_dir()
                and child_path.name.startswith("inc_")
                and child_path.name not in accepted_ids
            ):
                shutil.rmtree(child_path)
    write_json(output_dir / "incidents.json", [item.model_dump(mode="json") for item in incidents])
    write_json(
        output_dir / "incidents.geojson", {"type": "FeatureCollection", "features": features}
    )
    write_json(output_dir / "failed_clusters.json", failed_clusters)
    write_json(
        output_dir / "provider_runs.json", [item.model_dump(mode="json") for item in provider.runs]
    )
    summary.sources = len(sources)
    summary.evidence_items = len(evidence)
    summary.mentions = len(mentions)
    summary.incidents = len(incidents)
    summary.warnings = warnings
    summary.completed_at = utc_now()
    summary.status = (
        "failed"
        if not incidents and failed_clusters
        else "partial"
        if failed_clusters or warnings
        else "completed"
    )
    write_json(output_dir / "run.json", summary)
    export_schemas(Path("schemas"))
    return summary
