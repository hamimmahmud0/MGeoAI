from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from traffic_fusion.models import (
    FusedFact,
    FusedIncident,
    Geolocation,
    IncidentMention,
    LocationCandidate,
    MatchDecision,
    MatchFeatures,
    ProviderRun,
    SentimentEvidence,
    SentimentSummary,
    SourceRecord,
    TimeInterval,
)
from traffic_fusion.utils import canonical_json, stable_hash, stable_id


class RecordedFusionProvider:
    """Deterministic test/UI provider. Outputs are explicitly not live model results."""

    name = "recorded"
    model = "recorded-fixture-v2"

    def __init__(self) -> None:
        self._runs: list[ProviderRun] = []

    @property
    def runs(self) -> list[ProviderRun]:
        return self._runs

    def _record(self, operation: str, cluster_id: str, value: Any) -> str:
        request_hash = stable_hash(canonical_json(value), 64)
        run_id = stable_id("prun", operation, request_hash)
        self._runs.append(
            ProviderRun(
                run_id=run_id,
                cluster_id=cluster_id,
                operation=operation,
                provider=self.name,
                model=self.model,
                endpoint_mode="recorded",
                prompt_version="1.1.0",
                prompt_hash=stable_hash("recorded-provider-v2", 64),
                request_hash=request_hash,
                started_at=datetime(2000, 1, 1, tzinfo=UTC),
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0,
                retries=0,
                finish_status="recorded",
                validation_status="valid",
                cache_hit=True,
            )
        )
        return run_id

    def adjudicate(
        self, left: IncidentMention, right: IncidentMention, features: MatchFeatures
    ) -> MatchDecision:
        decision = (
            "same_incident"
            if (features.location_score == 1 and features.time_score >= 0.65)
            or (
                features.lexical_score >= 0.3
                and features.total_score >= 0.6
                and not features.hard_guard
            )
            else "uncertain"
        )
        confidence = (
            max(features.total_score, 0.82) if decision == "same_incident" else features.total_score
        )
        run_id = self._record(
            "match",
            f"{left.mention_id}:{right.mention_id}",
            {
                "left": left.mention_id,
                "right": right.mention_id,
                "features": features,
            },
        )
        return MatchDecision(
            left_mention_id=left.mention_id,
            right_mention_id=right.mention_id,
            decision=decision,
            confidence=confidence,
            decisive_evidence_ids=(left.evidence_ids[:1] + right.evidence_ids[:1]),
            rationale="Recorded adjudication: normalized date and location anchors agree."
            if decision == "same_incident"
            else "Recorded adjudication: evidence is insufficient for a precision-first merge.",
            features=features,
            provider_run_id=run_id,
        )

    def fuse(self, cluster_id: str, bundle: dict[str, Any]) -> FusedIncident:
        mentions = [IncidentMention.model_validate(item) for item in bundle["mentions"]]
        sources = [SourceRecord.model_validate(item) for item in bundle["sources"]]
        sentiments = [
            SentimentEvidence.model_validate(item) for item in bundle.get("sentiment", [])
        ]
        evidence_ids = sorted({item for mention in mentions for item in mention.evidence_ids})
        source_ids = sorted({mention.source_id for mention in mentions})
        run_id = self._record("fusion", cluster_id, bundle)

        location_candidates = [candidate for mention in mentions for candidate in mention.locations]
        geo = _fuse_location(location_candidates)
        event_time = _fuse_time(mentions)
        casualties = _fuse_casualties(mentions)
        anchor = next(
            (
                item.hierarchy.get("anchor")
                for item in location_candidates
                if item.hierarchy.get("anchor")
            ),
            None,
        ) or next(
            (
                feature
                for mention in mentions
                for feature in mention.lexical_features
                if feature
                in {
                    "purbachal",
                    "demra",
                    "tongi",
                    "sylhet",
                    "bogura",
                    "baniacho_shahrasti",
                    "fahim",
                }
            ),
            "unmapped",
        )
        title_names = {
            "purbachal": "BUET student crash on Purbachal 300 Feet Road",
            "demra": "DNCC garbage truck–motorcycle crash in Demra",
            "tongi": "Tongi student crash and highway blockade",
            "sylhet": "Passenger-bus collision in Osmaninagar, Sylhet",
            "bogura": "Bus crash involving labourers in Sherpur, Bogura",
            "baniacho_shahrasti": "Bus–truck collision in Baniacho, Shahrasti",
            "fahim": "Fatal crash involving student organizer Fahim Ahmed",
            "unmapped": "Reported traffic incident with unresolved location",
        }
        source_by_id = {source.source_id: source for source in sources}
        source_title = next(
            (
                source_by_id[source_id].title
                for source_id in source_ids
                if source_id in source_by_id and source_by_id[source_id].title
            ),
            None,
        )
        title = title_names.get(anchor) or source_title or title_names["unmapped"]
        independent_keys = {
            source_by_id[source_id].dependency_group or source_id
            for source_id in source_ids
            if source_id in source_by_id
        }
        duplicate_groups: list[list[str]] = []
        dependency: dict[str, list[str]] = defaultdict(list)
        for source_id in source_ids:
            source = source_by_id.get(source_id)
            if source and source.dependency_group:
                dependency[source.dependency_group].append(source_id)
        duplicate_groups = [sorted(items) for items in dependency.values() if len(items) > 1]
        traffic_effects = sorted(
            {effect for mention in mentions for effect in mention.traffic_effects}
        )
        vehicles = sorted({vehicle for mention in mentions for vehicle in mention.vehicles})
        facts = list(casualties)
        if traffic_effects:
            facts.append(
                FusedFact(
                    field="traffic_effect",
                    value="; ".join(traffic_effects),
                    support_evidence_ids=evidence_ids,
                    confidence=0.65,
                    selection_rationale="Retained from explicit source or analysis evidence; no quantitative delay inferred.",
                )
            )
        human_summary = _informative_summary(
            title=title,
            event_time=event_time,
            geolocation=geo,
            casualties=casualties,
            vehicles=vehicles,
            traffic_effects=traffic_effects,
            independent_source_count=len(independent_keys),
            source_count=len(source_ids),
            evidence_ids=evidence_ids,
        )
        sentiment_summary = _sentiment_summary(
            [item for item in sentiments if item.source_id in source_ids]
        )
        generated = (
            event_time.start.replace(tzinfo=UTC)
            if event_time.start
            else datetime(2000, 1, 1, tzinfo=UTC)
        )
        return FusedIncident(
            incident_id=stable_id("inc", *sorted(mention.mention_id for mention in mentions)),
            title=title,
            event_type="road_crash",
            event_time=event_time,
            geolocation=geo,
            facts=facts,
            vehicles=vehicles,
            collision=next(
                (
                    mention.collision_description
                    for mention in mentions
                    if mention.collision_description
                ),
                None,
            ),
            congestion_delay="; ".join(traffic_effects) if traffic_effects else None,
            source_ids=source_ids,
            evidence_ids=evidence_ids,
            independent_source_count=len(independent_keys),
            duplicate_groups=duplicate_groups,
            sentiment=sentiment_summary,
            unresolved_questions=["Exact crash geometry remains unverified."]
            if geo.granularity not in {"point", "intersection"}
            else [],
            data_quality_warnings=["RECORDED DEMO: this record was not fused by a live model."],
            human_summary=human_summary,
            generated_at=generated,
            provider_run_id=run_id,
        )


def _fuse_time(mentions: list[IncidentMention]) -> TimeInterval:
    times = [item.event_time for item in mentions if item.event_time.start]
    if not times:
        return TimeInterval()
    counts = Counter(item.start for item in times)
    selected = counts.most_common(1)[0][0]
    assert selected is not None
    duration = (
        times[0].end - times[0].start if times[0].end and times[0].start else timedelta(days=1)
    )
    return TimeInterval(
        start=selected,
        end=selected + duration,
        original_expression=times[0].original_expression,
        timezone=times[0].timezone,
        precision="day",
    )


def _fuse_location(candidates: list[LocationCandidate]) -> Geolocation:
    if not candidates:
        return Geolocation(ambiguity_reason="No incident-location evidence survived normalization")
    source_named = [candidate for candidate in candidates if candidate.granularity != "country"]
    eligible = source_named or candidates
    grouped = Counter(candidate.normalized_name for candidate in eligible)
    selected_name, count = grouped.most_common(1)[0]
    selected = next(
        candidate for candidate in eligible if candidate.normalized_name == selected_name
    )
    alternatives = [
        candidate for candidate in candidates if candidate.normalized_name != selected_name
    ]
    is_country_fallback = selected.granularity == "country"
    confidence = (
        min(0.2, selected.confidence + 0.02 * (count - 1))
        if is_country_fallback
        else min(0.9, selected.confidence + 0.05 * (count - 1))
    )
    radius = {"district": 35.0, "city": 12.0, "area": 3.0, "road_segment": 1.0}.get(
        selected.granularity
    )
    return Geolocation(
        display_name=selected.name,
        hierarchy=selected.hierarchy,
        latitude=selected.latitude,
        longitude=selected.longitude,
        granularity=selected.granularity,
        method=(
            "collection_country_fallback"
            if is_country_fallback
            else "source_named_offline_gazetteer_centroid"
        ),
        alternatives=alternatives,
        supporting_evidence_ids=sorted(
            {item for candidate in candidates for item in candidate.evidence_ids}
        ),
        confidence=confidence,
        ambiguity_reason=(
            "Incident place unresolved. This marker represents only the source's "
            "collection-country metadata and is not a reported crash location."
            if is_country_fallback
            else "Coordinates represent a named-area centroid, not the exact crash point."
            if radius
            else selected.reason
        ),
        uncertainty_radius_km=radius,
    )


def _fuse_casualties(mentions: list[IncidentMention]) -> list[FusedFact]:
    facts: list[FusedFact] = []
    for field in ("fatalities", "injuries"):
        values = [
            mention.casualties.get(field)
            for mention in mentions
            if mention.casualties.get(field) is not None
        ]
        numeric_values = [value for value in values if isinstance(value, int)]
        evidence_ids = sorted(
            {
                item
                for mention in mentions
                if mention.casualties.get(field) is not None
                for item in mention.evidence_ids
            }
        )
        if not numeric_values:
            facts.append(
                FusedFact(
                    field=field,
                    state="not_reported",
                    confidence=0,
                    selection_rationale="No explicit value was supplied in the normalized evidence.",
                )
            )
            continue
        counts = Counter(numeric_values)
        selected = counts.most_common(1)[0][0]
        alternatives = sorted(value for value in counts if value != selected)
        state = "reported_zero" if selected == 0 else "known"
        facts.append(
            FusedFact(
                field=field,
                value=selected,
                state=state,
                support_evidence_ids=evidence_ids,
                conflicting_values=alternatives,
                contradiction=bool(alternatives),
                confidence=min(0.9, 0.55 + counts[selected] * 0.08 - len(alternatives) * 0.12),
                selection_rationale="Most frequently reported value selected; alternatives retained without averaging.",
            )
        )
    return facts


def _sentiment_summary(items: list[SentimentEvidence]) -> SentimentSummary:
    aspects: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    unique: dict[str, SentimentEvidence] = {item.evidence_id: item for item in items}
    for item in unique.values():
        aspects[item.aspect][item.polarity] += 1
    return SentimentSummary(
        items=list(unique.values()),
        by_aspect={key: dict(value) for key, value in aspects.items()},
        sample_size=len(unique),
        traffic_relevant_count=sum(item.traffic_related for item in unique.values()),
        coverage_note=f"{len(unique)} unique visible or analyzed expression(s); reaction counts excluded."
        if unique
        else "No visible traffic-related sentiment was supplied.",
    )


def _informative_summary(
    *,
    title: str,
    event_time: TimeInterval,
    geolocation: Geolocation,
    casualties: list[FusedFact],
    vehicles: list[str],
    traffic_effects: list[str],
    independent_source_count: int,
    source_count: int,
    evidence_ids: list[str],
) -> str:
    sentences = [f"The fused record concerns this reported incident: {title}."]
    if event_time.start:
        sentences.append(
            f"The reported date is {event_time.start.strftime('%B')} "
            f"{event_time.start.day}, {event_time.start.year}, retained at "
            f"{event_time.precision.replace('_', ' ')} precision."
        )
    else:
        sentences.append("The event time was not established in the supplied evidence.")
    if geolocation.display_name:
        sentences.append(
            f"Reports identify the location as {geolocation.display_name}; fusion retains it at "
            f"{geolocation.granularity.replace('_', ' ')} precision with "
            f"{round(geolocation.confidence * 100)}% location confidence."
        )
    else:
        sentences.append("The incident location remains unresolved in the supplied evidence.")
    casualty_parts = []
    for fact in casualties:
        singular = "fatality" if fact.field == "fatalities" else "injury"
        plural = "fatalities" if fact.field == "fatalities" else "injuries"
        if fact.state == "known":
            count = fact.value if isinstance(fact.value, int) else None
            casualty_parts.append(
                f"{count} reported {singular if count == 1 else plural}"
                if count is not None
                else f"reported {plural} with an unresolved value"
            )
        elif fact.state == "reported_zero":
            casualty_parts.append(f"zero {plural} explicitly reported")
        else:
            casualty_parts.append(f"{plural} {fact.state.replace('_', ' ')}")
    sentences.append(
        "The reconciled casualty assessment records " + " and ".join(casualty_parts) + "."
    )
    if vehicles:
        sentences.append(
            "Identified vehicles or road users include "
            + ", ".join(item.replace("_", " ") for item in vehicles)
            + "."
        )
    if traffic_effects:
        sentences.append(
            "Explicitly reported traffic effects include " + "; ".join(traffic_effects) + "."
        )
    else:
        sentences.append("No explicit traffic congestion, delay, or obstruction was reported.")
    sentences.append(
        f"The record combines {source_count} source record(s) representing "
        f"{independent_source_count} independent source group(s) and "
        f"{len(evidence_ids)} cited evidence item(s)."
    )
    if geolocation.ambiguity_reason:
        uncertainty = geolocation.ambiguity_reason.rstrip(".")
        if geolocation.uncertainty_radius_km:
            uncertainty += f", with an approximate {geolocation.uncertainty_radius_km:g} km uncertainty radius"
        sentences.append(f"Important location limitation: {uncertainty}.")
    cited = " ".join(f"[{item}]" for item in evidence_ids[:3])
    if cited:
        sentences.append(f"Representative decisive evidence: {cited}.")
    return " ".join(sentences)
