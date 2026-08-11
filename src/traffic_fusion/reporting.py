from __future__ import annotations

from typing import Any

from traffic_fusion.models import FusedIncident


def incident_to_geojson(incident: FusedIncident) -> dict[str, Any] | None:
    geo = incident.geolocation
    if geo.longitude is None or geo.latitude is None:
        return None
    return {
        "type": "Feature",
        "id": incident.incident_id,
        "geometry": {"type": "Point", "coordinates": [geo.longitude, geo.latitude]},
        "properties": {
            "incident_id": incident.incident_id,
            "title": incident.title,
            "event_type": incident.event_type,
            "status": incident.status,
            "event_start": incident.event_time.start.isoformat()
            if incident.event_time.start
            else None,
            "location_name": geo.display_name,
            "granularity": geo.granularity,
            "confidence": geo.confidence,
            "uncertainty_radius_km": geo.uncertainty_radius_km,
            "source_count": incident.independent_source_count,
            "sentiment_count": incident.sentiment.traffic_relevant_count,
        },
    }


def render_incident_markdown(incident: FusedIncident) -> str:
    geo = incident.geolocation
    lines = [
        f"# {incident.title}",
        "",
        "> Evidence-fusion output. This record does not independently verify the incident.",
        "",
        "## Summary",
        "",
        incident.human_summary,
        "",
        "## Time and location",
        "",
        f"- Time: {incident.event_time.start.isoformat() if incident.event_time.start else 'not reported'}",
        f"- Location: {geo.display_name or 'unmapped'}",
        f"- Precision: {geo.granularity}; confidence {geo.confidence:.2f}",
        f"- Method: {geo.method}",
    ]
    if geo.ambiguity_reason:
        lines.append(f"- Location caveat: {geo.ambiguity_reason}")
    lines.extend(["", "## Incident facts", ""])
    for fact in incident.facts:
        value = (
            fact.value if fact.state in {"known", "reported_zero"} else fact.state.replace("_", " ")
        )
        citations = " ".join(f"[{evidence_id}]" for evidence_id in fact.support_evidence_ids)
        lines.append(
            f"- **{fact.field.replace('_', ' ').title()}:** {value} (confidence {fact.confidence:.2f}) {citations}".rstrip()
        )
        if fact.conflicting_values:
            lines.append(
                f"  - Conflicting alternatives: {', '.join(map(str, fact.conflicting_values))}"
            )
    lines.extend(["", "## Traffic impact", "", incident.congestion_delay or "Not reported.", ""])
    lines.extend(["## Sentiment", "", incident.sentiment.coverage_note, ""])
    for aspect, values in incident.sentiment.by_aspect.items():
        lines.append(
            f"- {aspect}: " + ", ".join(f"{key}={value}" for key, value in sorted(values.items()))
        )
    lines.extend(["", "## Sources and provenance", ""])
    lines.append(f"- Independent source groups: {incident.independent_source_count}")
    lines.append(f"- Source IDs: {', '.join(incident.source_ids)}")
    lines.append(f"- Evidence IDs: {', '.join(incident.evidence_ids)}")
    if incident.unresolved_questions:
        lines.extend(["", "## Unresolved questions", ""])
        lines.extend(f"- {item}" for item in incident.unresolved_questions)
    if incident.data_quality_warnings:
        lines.extend(["", "## Data-quality warnings", ""])
        lines.extend(f"- {item}" for item in incident.data_quality_warnings)
    return "\n".join(lines).rstrip() + "\n"


def validate_fused_provenance(
    incident: FusedIncident, allowed_evidence: set[str], allowed_sources: set[str]
) -> list[str]:
    errors: list[str] = []
    unknown_evidence = set(incident.evidence_ids) - allowed_evidence
    unknown_sources = set(incident.source_ids) - allowed_sources
    if unknown_evidence:
        errors.append(f"record references unknown evidence IDs: {sorted(unknown_evidence)}")
    if unknown_sources:
        errors.append(f"record references unknown source IDs: {sorted(unknown_sources)}")
    for fact in incident.facts:
        unknown = set(fact.support_evidence_ids) - allowed_evidence
        if unknown:
            errors.append(f"fact {fact.field} references unknown evidence IDs: {sorted(unknown)}")
        if (
            fact.state in {"known", "reported_zero"}
            and fact.value is not None
            and not fact.support_evidence_ids
        ):
            errors.append(f"fact {fact.field} has a value without support evidence")
    if incident.geolocation.supporting_evidence_ids:
        unknown = set(incident.geolocation.supporting_evidence_ids) - allowed_evidence
        if unknown:
            errors.append(f"geolocation references unknown evidence IDs: {sorted(unknown)}")
    return errors
