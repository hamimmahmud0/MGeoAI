from __future__ import annotations

from typing import Any

from traffic_fusion.models import FusedIncident, MatchDecision


def matching_metrics(
    gold_pairs: list[dict[str, str]], decisions: list[MatchDecision]
) -> dict[str, float | int]:
    predicted = {
        frozenset((item.left_mention_id, item.right_mention_id)): item.decision == "same_incident"
        for item in decisions
    }
    true_positive = false_positive = false_negative = true_negative = 0
    ambiguous = 0
    for row in gold_pairs:
        if row["label"] == "ambiguous":
            ambiguous += 1
            continue
        actual = row["label"] == "same_incident"
        guess = predicted.get(frozenset((row["left"], row["right"])), False)
        if actual and guess:
            true_positive += 1
        elif actual:
            false_negative += 1
        elif guess:
            false_positive += 1
        else:
            true_negative += 1
    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive + false_negative else 0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "ambiguous_excluded": ambiguous,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def extraction_coverage(incidents: list[FusedIncident]) -> dict[str, Any]:
    fields = ("event_time", "geolocation", "fatalities", "injuries", "provenance")
    counts = dict.fromkeys(fields, 0)
    for incident in incidents:
        counts["event_time"] += incident.event_time.start is not None
        counts["geolocation"] += incident.geolocation.display_name is not None
        counts["fatalities"] += any(
            fact.field == "fatalities" and fact.state in {"known", "reported_zero"}
            for fact in incident.facts
        )
        counts["injuries"] += any(
            fact.field == "injuries" and fact.state in {"known", "reported_zero"}
            for fact in incident.facts
        )
        counts["provenance"] += bool(incident.evidence_ids)
    total = len(incidents)
    return {
        "sample_size": total,
        "field_coverage": {
            key: round(value / total, 4) if total else 0 for key, value in counts.items()
        },
    }
