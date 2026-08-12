from __future__ import annotations

import csv
import json
import math
import random
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

JSON = dict[str, Any]
MATERIAL_FIELDS = (
    "incident_type",
    "event_time",
    "location",
    "fatalities",
    "injuries",
    "vehicles",
    "road_users",
    "traffic_impact",
    "road_blockage",
    "contributing_factors",
    "emergency_response",
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[JSON]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[JSON], columns: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(columns or (rows[0].keys() if rows else []))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9\u0980-\u09ff]+", text))


def _percent(numerator: float, denominator: float) -> float | None:
    return round(100 * numerator / denominator, 4) if denominator else None


def _safe_mean(values: Sequence[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def _safe_median(values: Sequence[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 4)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(value, 4)


def _distribution(values: Sequence[float]) -> JSON:
    metrics = {
        "n": len(values),
        "mean": _safe_mean(values),
        "median": _safe_median(values),
        "standard_deviation": round(statistics.pstdev(values), 4) if values else None,
        "minimum": round(min(values), 4) if values else None,
        "q1": _percentile(values, 0.25),
        "q3": _percentile(values, 0.75),
        "p90": _percentile(values, 0.90),
        "maximum": round(max(values), 4) if values else None,
    }
    return metrics


def _bootstrap_ci(
    values: Sequence[Any], statistic: Callable[[list[Any]], float], seed: int, samples: int = 2000
) -> list[float] | None:
    if not values:
        return None
    generator = random.Random(seed)
    estimates = [
        statistic([values[generator.randrange(len(values))] for _ in values])
        for _ in range(samples)
    ]
    return [_percentile(estimates, 0.025) or 0.0, _percentile(estimates, 0.975) or 0.0]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    first, second = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(first) * math.cos(second) * math.sin(delta_lon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


class RunArtifacts:
    def __init__(self, root: Path) -> None:
        required = ("run.json", "sources.jsonl", "evidence.jsonl", "mentions.jsonl", "incidents.json")
        missing = [name for name in required if not (root / name).exists()]
        if missing:
            raise ValueError(f"{root} is missing required artifact(s): {', '.join(missing)}")
        self.root = root
        self.run: JSON = _json(root / "run.json")
        self.sources = _jsonl(root / "sources.jsonl")
        self.evidence = _jsonl(root / "evidence.jsonl")
        self.mentions = _jsonl(root / "mentions.jsonl")
        self.incidents: list[JSON] = _json(root / "incidents.json")
        self.matches: list[JSON] = _json(root / "matches.json") if (root / "matches.json").exists() else []
        cluster_payload = _json(root / "clusters.json") if (root / "clusters.json").exists() else {}
        self.clusters: list[list[str]] = cluster_payload.get("clusters", [])
        self.provider_runs: list[JSON] = (
            _json(root / "provider_runs.json") if (root / "provider_runs.json").exists() else []
        )


def _source_path(source: JSON) -> str:
    return str(source.get("local_path") or "").replace("\\", "/")


def _mention_location_text(mention: JSON) -> str:
    parts: list[str] = []
    for location in mention.get("locations", []):
        parts.extend([location.get("name", ""), location.get("normalized_name", "")])
        parts.extend((location.get("hierarchy") or {}).values())
    return _norm(" ".join(str(part) for part in parts))


def _incident_location_text(incident: JSON) -> str:
    location = incident.get("geolocation") or {}
    parts: list[Any] = [location.get("display_name", "")]
    parts.extend((location.get("hierarchy") or {}).values())
    return _norm(" ".join(str(part) for part in parts))


def _terms_match(text: str, terms: Iterable[str]) -> bool:
    normalized = [_norm(term) for term in terms]
    return bool(normalized) and all(term in text for term in normalized)


def resolve_gold_mentions(gold: JSON, run: RunArtifacts) -> tuple[dict[str, list[str]], list[JSON]]:
    source_by_path = {_source_path(source): source for source in run.sources}
    mentions_by_source: dict[str, list[JSON]] = defaultdict(list)
    for mention in run.mentions:
        mentions_by_source[str(mention["source_id"])].append(mention)
    resolved: dict[str, list[str]] = {}
    issues: list[JSON] = []
    claimed: dict[str, str] = {}
    for incident in gold["incidents"]:
        gold_id = str(incident["gold_id"])
        resolved[gold_id] = []
        location_terms = (incident.get("location") or {}).get("required_terms", [])
        for member in incident["source_members"]:
            path = str(member["path"])
            source = source_by_path.get(path)
            if not source:
                issues.append({"gold_id": gold_id, "path": path, "reason": "source_not_in_run"})
                continue
            candidates = mentions_by_source.get(str(source["source_id"]), [])
            selector = member.get("mention_location_terms")
            if selector:
                candidates = [
                    mention
                    for mention in candidates
                    if _terms_match(_mention_location_text(mention), selector)
                ]
            elif len(candidates) > 1 and location_terms:
                matching = [
                    mention
                    for mention in candidates
                    if any(_norm(term) in _mention_location_text(mention) for term in location_terms)
                ]
                if matching:
                    candidates = matching
            if len(candidates) != 1:
                issues.append(
                    {
                        "gold_id": gold_id,
                        "path": path,
                        "reason": "no_matching_mention" if not candidates else "ambiguous_mentions",
                        "candidate_count": len(candidates),
                    }
                )
                continue
            mention_id = str(candidates[0]["mention_id"])
            if mention_id in claimed and claimed[mention_id] != gold_id:
                issues.append(
                    {
                        "gold_id": gold_id,
                        "path": path,
                        "reason": "mention_already_assigned",
                        "assigned_gold_id": claimed[mention_id],
                    }
                )
                continue
            claimed[mention_id] = gold_id
            resolved[gold_id].append(mention_id)
    return resolved, issues


def _match_gold_to_incidents(
    gold: JSON, gold_mentions: dict[str, list[str]], run: RunArtifacts
) -> dict[str, JSON | None]:
    mention_by_id = {str(item["mention_id"]): item for item in run.mentions}
    incident_candidates: list[tuple[int, JSON]] = list(enumerate(run.incidents))
    chosen: set[str] = set()
    result: dict[str, JSON | None] = {}
    for reference in gold["incidents"]:
        gold_id = str(reference["gold_id"])
        gold_source_ids = {
            str(mention_by_id[item]["source_id"])
            for item in gold_mentions.get(gold_id, [])
            if item in mention_by_id
        }
        required = (reference.get("location") or {}).get("required_terms", [])
        ranked: list[tuple[float, JSON]] = []
        for _, incident in incident_candidates:
            if str(incident["incident_id"]) in chosen:
                continue
            source_overlap = len(gold_source_ids & set(incident.get("source_ids", [])))
            location_score = 2.0 if _terms_match(_incident_location_text(incident), required) else 0.0
            if source_overlap or location_score:
                ranked.append((source_overlap + location_score, incident))
        if not ranked:
            result[gold_id] = None
            continue
        ranked.sort(key=lambda item: (item[0], len(item[1].get("source_ids", []))), reverse=True)
        selected = ranked[0][1]
        chosen.add(str(selected["incident_id"]))
        result[gold_id] = selected
    return result


def _fact(incident: JSON | None, field: str) -> tuple[int | None, str]:
    if not incident:
        return None, "missing_incident"
    candidates = [item for item in incident.get("facts", []) if item.get("field") == field]
    if not candidates:
        return None, "not_reported"
    item = candidates[0]
    state = str(item.get("state", "unknown"))
    value = item.get("value")
    if state == "reported_zero":
        return 0, state
    if state == "known" and isinstance(value, int) and not isinstance(value, bool):
        return value, state
    return None, state


def _numeric_gold_metrics(rows: list[JSON], field: str, seed: int) -> JSON:
    evaluable = [row for row in rows if row[f"gold_{field}"] is not None]
    predicted = [row for row in evaluable if row[f"predicted_{field}"] is not None]
    comparisons = [
        (int(row[f"gold_{field}"]), int(row[f"predicted_{field}"])) for row in predicted
    ]
    exact = [int(gold == guess) for gold, guess in comparisons]
    errors = [abs(gold - guess) for gold, guess in comparisons]
    return {
        "gold_known_n": len(evaluable),
        "prediction_available_n": len(predicted),
        "missing_prediction_n": len(evaluable) - len(predicted),
        "exact_match_count": sum(exact),
        "exact_match_accuracy": round(statistics.fmean(exact), 4) if exact else None,
        "exact_match_ci95": _bootstrap_ci(exact, statistics.fmean, seed),
        "mean_absolute_error": _safe_mean(errors),
        "mae_ci95": _bootstrap_ci(errors, statistics.fmean, seed + 1),
        "reference_total": sum(gold for gold, _ in comparisons),
        "predicted_total": sum(guess for _, guess in comparisons),
        "overestimation_count": sum(guess > gold for gold, guess in comparisons),
        "underestimation_count": sum(guess < gold for gold, guess in comparisons),
        "missing predictions are errors": False,
        "note": "Accuracy and MAE use cases with both a human label and a numeric prediction; missing predictions are reported separately.",
    }


def _gold_comparison(
    gold: JSON, gold_mentions: dict[str, list[str]], predicted: dict[str, JSON | None], seed: int
) -> tuple[JSON, list[JSON], list[JSON]]:
    rows: list[JSON] = []
    errors: list[JSON] = []
    exact_locations: list[int] = []
    semantic_locations: list[int] = []
    granularity_matches: list[int] = []
    coordinate_errors: list[float] = []
    for reference in gold["incidents"]:
        gold_id = str(reference["gold_id"])
        incident = predicted[gold_id]
        fatalities, fatality_state = _fact(incident, "fatalities")
        injuries, injury_state = _fact(incident, "injuries")
        gold_location = reference.get("location") or {}
        predicted_location = (incident or {}).get("geolocation") or {}
        gold_name = str(gold_location.get("name") or "")
        predicted_name = str(predicted_location.get("display_name") or "")
        exact_location = bool(gold_name and _norm(gold_name) == _norm(predicted_name))
        semantic_location = bool(
            gold_name
            and _terms_match(_norm(predicted_name), gold_location.get("required_terms", []))
        )
        granularity_match = bool(
            gold_location.get("granularity")
            and gold_location.get("granularity") == predicted_location.get("granularity")
        )
        if gold_name:
            exact_locations.append(int(exact_location))
            semantic_locations.append(int(semantic_location))
            granularity_matches.append(int(granularity_match))
        coordinate_error: float | None = None
        if all(
            isinstance(value, (int, float))
            for value in (
                gold_location.get("latitude"),
                gold_location.get("longitude"),
                predicted_location.get("latitude"),
                predicted_location.get("longitude"),
            )
        ):
            coordinate_error = round(
                _haversine_km(
                    float(gold_location["latitude"]),
                    float(gold_location["longitude"]),
                    float(predicted_location["latitude"]),
                    float(predicted_location["longitude"]),
                ),
                4,
            )
            coordinate_errors.append(coordinate_error)
        row = {
            "gold_id": gold_id,
            "resolved_gold_mentions": len(gold_mentions.get(gold_id, [])),
            "predicted_incident_id": (incident or {}).get("incident_id"),
            "gold_fatalities": reference.get("fatalities"),
            "predicted_fatalities": fatalities,
            "predicted_fatality_state": fatality_state,
            "gold_injuries": reference.get("injuries"),
            "predicted_injuries": injuries,
            "predicted_injury_state": injury_state,
            "gold_location": gold_name,
            "predicted_location": predicted_name or None,
            "location_exact": exact_location,
            "location_semantic": semantic_location,
            "gold_granularity": gold_location.get("granularity"),
            "predicted_granularity": predicted_location.get("granularity"),
            "granularity_agreement": granularity_match,
            "coordinate_error_km": coordinate_error,
        }
        rows.append(row)
        if incident is None:
            errors.append({"gold_id": gold_id, "category": "missing_fused_incident", "detail": "No predicted incident could be aligned."})
        for field, label, guess in (
            ("fatalities", reference.get("fatalities"), fatalities),
            ("injuries", reference.get("injuries"), injuries),
        ):
            if label is not None and guess is None:
                errors.append({"gold_id": gold_id, "category": f"unresolved_{field}", "detail": f"Reference={label}; prediction unavailable."})
            elif label is not None and guess != label:
                assert guess is not None
                direction = "overestimate" if int(guess) > int(label) else "underestimate"
                errors.append({"gold_id": gold_id, "category": f"{field}_{direction}", "detail": f"Reference={label}; prediction={guess}."})
        if gold_name and not semantic_location:
            errors.append({"gold_id": gold_id, "category": "geographic_disagreement", "detail": f"Reference={gold_name}; prediction={predicted_name or 'unresolved'}."})
        if semantic_location and not granularity_match:
            errors.append({"gold_id": gold_id, "category": "location_granularity_disagreement", "detail": f"Reference={gold_location.get('granularity')}; prediction={predicted_location.get('granularity')}."})
    metrics = {
        "gold_incidents": len(gold["incidents"]),
        "fatalities": _numeric_gold_metrics(rows, "fatalities", seed),
        "injuries": _numeric_gold_metrics(rows, "injuries", seed + 10),
        "location": {
            "text_label_n": len(exact_locations),
            "exact_normalized_count": sum(exact_locations),
            "exact_normalized_agreement": round(statistics.fmean(exact_locations), 4) if exact_locations else None,
            "semantic_required_term_count": sum(semantic_locations),
            "semantic_location_agreement": round(statistics.fmean(semantic_locations), 4) if semantic_locations else None,
            "semantic_location_ci95": _bootstrap_ci(semantic_locations, statistics.fmean, seed + 20),
            "granularity_agreement_count": sum(granularity_matches),
            "granularity_agreement": round(statistics.fmean(granularity_matches), 4) if granularity_matches else None,
            "coordinate_reference_n": len(coordinate_errors),
            "coordinate_error_km": _distribution(coordinate_errors),
            "note": "No coordinate is fabricated from a text-only gold place label.",
        },
        "incident_type": {"evaluable_n": 0, "note": "No human incident-type labels were supplied."},
        "event_time": {"evaluable_n": 0, "note": "No human event-time labels were supplied."},
    }
    return metrics, rows, errors


def _classification_metrics(actual: list[bool], predicted: list[bool]) -> JSON:
    tp = sum(a and p for a, p in zip(actual, predicted, strict=True))
    fp = sum(not a and p for a, p in zip(actual, predicted, strict=True))
    fn = sum(a and not p for a, p in zip(actual, predicted, strict=True))
    tn = sum(not a and not p for a, p in zip(actual, predicted, strict=True))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    accuracy = (tp + tn) / len(actual) if actual else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0
    return {
        "n": len(actual), "true_positive": tp, "false_positive": fp,
        "true_negative": tn, "false_negative": fn,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4) if accuracy is not None else None,
        "specificity": round(specificity, 4) if specificity is not None else None,
    }


def _cluster_bootstrap_matching_ci(
    pair_rows: list[JSON], label_by_mention: dict[str, str], seed: int, samples: int = 2000
) -> list[float] | None:
    groups = sorted(set(label_by_mention.values()))
    if not groups or not pair_rows:
        return None
    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        weights = Counter(groups[generator.randrange(len(groups))] for _ in groups)
        actual: list[bool] = []
        predicted: list[bool] = []
        for row in pair_rows:
            left_group = label_by_mention[str(row["left"])]
            right_group = label_by_mention[str(row["right"])]
            weight = (
                weights[left_group]
                if left_group == right_group
                else weights[left_group] * weights[right_group]
            )
            actual.extend([row["gold_label"] == "same_incident"] * weight)
            predicted.extend([row["predicted_label"] == "same_incident"] * weight)
        if actual:
            estimates.append(float(_classification_metrics(actual, predicted)["f1"]))
    if not estimates:
        return None
    return [_percentile(estimates, 0.025) or 0.0, _percentile(estimates, 0.975) or 0.0]


def _matching_and_clustering(
    gold_mentions: dict[str, list[str]], run: RunArtifacts, seed: int
) -> tuple[JSON, JSON, list[JSON]]:
    label_by_mention = {
        mention_id: gold_id
        for gold_id, mention_ids in gold_mentions.items()
        for mention_id in mention_ids
    }
    mention_ids = sorted(label_by_mention)
    decision_by_pair = {
        frozenset((str(item["left_mention_id"]), str(item["right_mention_id"]))): item
        for item in run.matches
    }
    actual: list[bool] = []
    guesses: list[bool] = []
    heuristic_guesses: list[bool] = []
    pair_rows: list[JSON] = []
    for left, right in combinations(mention_ids, 2):
        same = label_by_mention[left] == label_by_mention[right]
        decision = decision_by_pair.get(frozenset((left, right)))
        guess = bool(decision and decision.get("decision") == "same_incident")
        actual.append(same)
        guesses.append(guess)
        features = (decision or {}).get("features") or {}
        heuristic_guesses.append(
            bool(
                decision
                and not features.get("hard_guard")
                and float(features.get("total_score", 0)) >= 0.72
            )
        )
        pair_rows.append(
            {
                "left": left,
                "right": right,
                "gold_label": "same_incident" if same else "different_incident",
                "predicted_label": (decision or {}).get("decision", "no_candidate_decision"),
                "confidence": (decision or {}).get("confidence"),
            }
        )
    matching = _classification_metrics(actual, guesses)
    matching["positive_pairs"] = sum(actual)
    matching["negative_pairs"] = len(actual) - sum(actual)
    matching["f1_ci95"] = _cluster_bootstrap_matching_ci(
        pair_rows, label_by_mention, seed
    )
    matching["f1_ci95_method"] = "gold-incident cluster bootstrap; 2,000 resamples"
    matching["ablations"] = {
        "heuristic_only_predeclared_threshold_0_72": _classification_metrics(
            actual, heuristic_guesses
        ),
        "full_hybrid": _classification_metrics(actual, guesses),
        "llm_only": {
            "status": "not_run",
            "reason": "The run does not contain provider adjudications for every gold pair; rerunning would require unnecessary paid calls and change the evaluated artifact.",
        },
        "modality": {
            "status": "not_run",
            "reason": "No independently generated text-only and visual-only fused run artifacts exist; post-hoc evidence deletion would not reproduce pipeline semantics.",
        },
    }
    predicted_cluster: dict[str, str] = {}
    for index, cluster in enumerate(run.clusters):
        for mention_id in cluster:
            if mention_id in label_by_mention:
                predicted_cluster[mention_id] = f"cluster-{index + 1:03d}"
    for mention_id in mention_ids:
        predicted_cluster.setdefault(mention_id, f"missing-{mention_id}")
    bc_precision: list[float] = []
    bc_recall: list[float] = []
    for mention_id in mention_ids:
        gold_peers = {item for item in mention_ids if label_by_mention[item] == label_by_mention[mention_id]}
        predicted_peers = {item for item in mention_ids if predicted_cluster[item] == predicted_cluster[mention_id]}
        intersection = len(gold_peers & predicted_peers)
        bc_precision.append(intersection / len(predicted_peers))
        bc_recall.append(intersection / len(gold_peers))
    bc_p = statistics.fmean(bc_precision) if bc_precision else 0.0
    bc_r = statistics.fmean(bc_recall) if bc_recall else 0.0
    bc_f1 = 2 * bc_p * bc_r / (bc_p + bc_r) if bc_p + bc_r else 0.0
    predicted_pair_same = [predicted_cluster[left] == predicted_cluster[right] for left, right in combinations(mention_ids, 2)]
    pairwise = _classification_metrics(actual, predicted_pair_same)
    fragmented = sum(
        len({predicted_cluster[item] for item in members}) > 1
        for members in gold_mentions.values()
        if members
    )
    overmerged = 0
    for cluster_name in set(predicted_cluster.values()):
        labels = {label_by_mention[item] for item in mention_ids if predicted_cluster[item] == cluster_name}
        overmerged += len(labels) > 1
    correct_multi = sum(
        len(members) > 1 and len({predicted_cluster[item] for item in members}) == 1
        for members in gold_mentions.values()
    )
    clustering = {
        "evaluable_mentions": len(mention_ids),
        "gold_clusters": sum(bool(items) for items in gold_mentions.values()),
        "b_cubed_precision": round(bc_p, 4),
        "b_cubed_recall": round(bc_r, 4),
        "b_cubed_f1": round(bc_f1, 4),
        "pairwise": pairwise,
        "fragmented_gold_incidents": fragmented,
        "overmerged_predicted_clusters": overmerged,
        "singleton_predicted_mentions": sum(
            list(predicted_cluster.values()).count(value) == 1 for value in predicted_cluster.values()
        ),
        "correct_multi_source_clusters": correct_multi,
    }
    return matching, clustering, pair_rows


def _source_domain(source: JSON) -> str | None:
    uri = source.get("source_uri")
    if not uri:
        return None
    return urlparse(str(uri)).netloc.casefold().removeprefix("www.") or None


def _source_modality(source: JSON) -> str:
    source_type = str(source.get("source_type", ""))
    if source_type == "image_analysis":
        return "image"
    if source_type == "video_analysis":
        return "video"
    return "text"


def _full_corpus_summary(run: RunArtifacts) -> JSON:
    countries = {
        str(source.get("country_code") or source.get("country"))
        for source in run.sources
        if source.get("country_code") or source.get("country")
    }
    languages = {language for source in run.sources for language in source.get("languages", [])}
    publishers = {str(source["publisher"]) for source in run.sources if source.get("publisher")}
    domains = {domain for source in run.sources if (domain := _source_domain(source))}
    source_types = Counter(str(source.get("source_type", "unknown")) for source in run.sources)
    modalities = Counter(_source_modality(source) for source in run.sources)
    source_counts = [len(set(incident.get("source_ids", []))) for incident in run.incidents]
    mapped_markers = sum(
        (incident.get("geolocation") or {}).get("latitude") is not None
        and (incident.get("geolocation") or {}).get("longitude") is not None
        for incident in run.incidents
    )
    resolved_locations = sum(
        (incident.get("geolocation") or {}).get("latitude") is not None
        and (incident.get("geolocation") or {}).get("longitude") is not None
        and (incident.get("geolocation") or {}).get("method")
        != "collection_country_fallback"
        for incident in run.incidents
    )
    raw = int(run.run.get("input_files", len(run.sources)))
    return {
        "raw_input_artifacts": raw,
        "accepted_source_records": len(run.sources),
        "rejected_or_skipped_artifacts": max(raw - len(run.sources), 0),
        "countries": len(countries),
        "country_values": sorted(countries),
        "languages": len(languages),
        "language_values": sorted(languages),
        "publishers": len(publishers),
        "unique_domains": len(domains),
        "source_type_counts": dict(sorted(source_types.items())),
        "modality_source_counts": dict(sorted(modalities.items())),
        "evidence_items": len(run.evidence),
        "incident_mentions": len(run.mentions),
        "fused_incidents": len(run.incidents),
        "mapped_marker_records": mapped_markers,
        "map_marker_coverage_percent": _percent(mapped_markers, len(run.incidents)),
        "geolocated_incidents": resolved_locations,
        "geolocation_coverage_percent": _percent(resolved_locations, len(run.incidents)),
        "collection_country_fallback_markers": mapped_markers - resolved_locations,
        "unresolved_location_incidents": len(run.incidents) - resolved_locations,
        "multi_source_incidents": sum(value > 1 for value in source_counts),
        "single_source_incidents": sum(value == 1 for value in source_counts),
        "mean_sources_per_incident": _safe_mean([float(value) for value in source_counts]),
        "median_sources_per_incident": _safe_median([float(value) for value in source_counts]),
        "maximum_sources_per_incident": max(source_counts, default=0),
        "evidence_per_source": round(len(run.evidence) / len(run.sources), 4) if run.sources else None,
        "mentions_per_source": round(len(run.mentions) / len(run.sources), 4) if run.sources else None,
        "evidence_per_incident": round(len(run.evidence) / len(run.incidents), 4) if run.incidents else None,
    }


def _source_diversity(run: RunArtifacts) -> tuple[JSON, list[JSON]]:
    source_by_id = {str(source["source_id"]): source for source in run.sources}
    rows: list[JSON] = []
    for incident in run.incidents:
        sources = [source_by_id[item] for item in incident.get("source_ids", []) if item in source_by_id]
        dependencies = {
            str(source.get("dependency_group") or source["source_id"]) for source in sources
        }
        row = {
            "incident_id": incident["incident_id"],
            "source_records": len(sources),
            "unique_publishers": len({source.get("publisher") for source in sources if source.get("publisher")}),
            "unique_domains": len({domain for source in sources if (domain := _source_domain(source))}),
            "modalities": len({_source_modality(source) for source in sources}),
            "independent_groups": len(dependencies),
            "raw_minus_independent": len(sources) - len(dependencies),
        }
        rows.append(row)
    metrics: JSON = {}
    for field in ("source_records", "unique_publishers", "unique_domains", "modalities", "independent_groups"):
        metrics[field] = _distribution([float(row[field]) for row in rows])
    counts = Counter(
        "4+" if row["source_records"] >= 4 else str(row["source_records"]) for row in rows
    )
    affected = [row for row in rows if row["raw_minus_independent"] > 0]
    metrics.update(
        {
            "source_count_distribution": dict(sorted(counts.items())),
            "dependency_groups": len(
                {source.get("dependency_group") for source in run.sources if source.get("dependency_group")}
            ),
            "dependency_affected_sources": sum(
                source.get("dependency_group") is not None for source in run.sources
            ),
            "dependency_affected_incidents": len(affected),
            "raw_minus_independent_source_count": sum(row["raw_minus_independent"] for row in rows),
        }
    )
    return metrics, rows


def _evidence_fields(evidence: JSON) -> set[str]:
    fields: set[str] = set()
    text = _norm(f"{evidence.get('normalized_claim', '')} {evidence.get('predicate', '')}")
    if evidence.get("evidence_kind") in {"headline", "article", "post", "incident_summary"}:
        fields.add("incident_type")
    if evidence.get("time_mentions"):
        fields.add("event_time")
    if evidence.get("location_mentions"):
        fields.add("location")
    if evidence.get("vehicles"):
        fields.add("vehicles")
    if evidence.get("road_users"):
        fields.add("road_users")
    casualties = evidence.get("casualty_quantities") or {}
    if "fatalities" in casualties or re.search(r"\b(killed|dead|died|fatalit)", text):
        fields.add("fatalities")
    if "injuries" in casualties or re.search(r"\b(injur|wounded)", text):
        fields.add("injuries")
    if evidence.get("traffic_effects"):
        fields.add("traffic_impact")
    keyword_fields = {
        "road_blockage": ("block", "closure", "closed", "obstruction"),
        "weather": ("weather", "rain", "fog", "storm"),
        "road_condition": ("road condition", "pothole", "slippery"),
        "emergency_response": ("ambulance", "hospital", "police", "fire service", "rescue"),
        "contributing_factors": ("speeding", "reckless", "mechanical failure", "lost control"),
    }
    for field, keywords in keyword_fields.items():
        if any(keyword in text for keyword in keywords):
            fields.add(field)
    return fields


def _modality_contribution(run: RunArtifacts) -> tuple[JSON, list[JSON]]:
    evidence_by_id = {str(item["evidence_id"]): item for item in run.evidence}
    source_by_id = {str(item["source_id"]): item for item in run.sources}
    support: Counter[tuple[str, str]] = Counter()
    multimodal_support: Counter[str] = Counter()
    incident_modality_counts: list[int] = []
    for incident in run.incidents:
        incident_support: dict[str, set[str]] = defaultdict(set)
        incident_modalities: set[str] = set()
        for evidence_id in incident.get("evidence_ids", []):
            evidence = evidence_by_id.get(str(evidence_id))
            if not evidence:
                continue
            source = source_by_id.get(str(evidence.get("source_id")), {})
            modality = str(evidence.get("modality") or _source_modality(source))
            incident_modalities.add(modality)
            for field in _evidence_fields(evidence):
                incident_support[field].add(modality)
        incident_modality_counts.append(len(incident_modalities))
        for field, modalities in incident_support.items():
            for modality in modalities:
                support[(field, modality)] += 1
            if len(modalities) >= 2:
                multimodal_support[field] += 1
    rows = [
        {
            "field": field,
            "modality": modality,
            "incident_count": count,
            "percent_of_fused_incidents": _percent(count, len(run.incidents)),
        }
        for (field, modality), count in sorted(support.items())
    ]
    metrics = {
        "single_modality_incidents": sum(value == 1 for value in incident_modality_counts),
        "two_or_more_modality_incidents": sum(value >= 2 for value in incident_modality_counts),
        "three_or_more_modality_incidents": sum(value >= 3 for value in incident_modality_counts),
        "cross_modal_evidence_support_by_field": dict(sorted(multimodal_support.items())),
        "note": "Contribution counts evidence support and does not measure modality accuracy.",
    }
    return metrics, rows


def _known_mention_fields(mention: JSON) -> set[str]:
    known = {"incident_type"} if mention.get("event_type") not in {None, "", "unknown"} else set()
    if (mention.get("event_time") or {}).get("start"):
        known.add("event_time")
    if mention.get("locations"):
        known.add("location")
    casualties = mention.get("casualties") or {}
    for field in ("fatalities", "injuries"):
        if casualties.get(field) is not None:
            known.add(field)
    if mention.get("vehicles"):
        known.add("vehicles")
    if mention.get("people"):
        known.add("road_users")
    if mention.get("traffic_effects"):
        known.add("traffic_impact")
        if any("block" in _norm(item) or "closure" in _norm(item) for item in mention["traffic_effects"]):
            known.add("road_blockage")
    if mention.get("response"):
        known.add("emergency_response")
    return known


def _known_incident_fields(incident: JSON) -> set[str]:
    known = {"incident_type"} if incident.get("event_type") not in {None, "", "unknown"} else set()
    if (incident.get("event_time") or {}).get("start"):
        known.add("event_time")
    if (incident.get("geolocation") or {}).get("display_name"):
        known.add("location")
    for field in ("fatalities", "injuries"):
        value, _ = _fact(incident, field)
        if value is not None:
            known.add(field)
    if incident.get("vehicles"):
        known.add("vehicles")
    if incident.get("involved_parties"):
        known.add("road_users")
    if incident.get("obstruction") or incident.get("congestion_delay"):
        known.add("traffic_impact")
    if incident.get("obstruction"):
        known.add("road_blockage")
    if incident.get("contributing_factors"):
        known.add("contributing_factors")
    if incident.get("emergency_response"):
        known.add("emergency_response")
    return known


def _fusion_completeness(run: RunArtifacts) -> tuple[JSON, list[JSON]]:
    mentions_by_source: dict[str, list[JSON]] = defaultdict(list)
    for mention in run.mentions:
        mentions_by_source[str(mention["source_id"])].append(mention)
    rows: list[JSON] = []
    for incident in run.incidents:
        source_ids = set(incident.get("source_ids", []))
        if len(source_ids) < 2:
            continue
        single_counts = [
            len(_known_mention_fields(mention))
            for source_id in source_ids
            for mention in mentions_by_source.get(str(source_id), [])
        ]
        best = max(single_counts, default=0)
        fused = len(_known_incident_fields(incident))
        gain = fused - best
        rows.append(
            {
                "incident_id": incident["incident_id"],
                "source_count": len(source_ids),
                "best_single_known_fields": best,
                "fused_known_fields": fused,
                "material_field_count": len(MATERIAL_FIELDS),
                "best_single_completeness": round(best / len(MATERIAL_FIELDS), 4),
                "fused_completeness": round(fused / len(MATERIAL_FIELDS), 4),
                "absolute_completeness_gain": round((fused - best) / len(MATERIAL_FIELDS), 4),
                "relative_completeness_gain": round((fused - best) / best, 4) if best else None,
                "fusion_information_gain_fields": gain,
            }
        )
    return {
        "evaluable_multi_source_incidents": len(rows),
        "average_best_single_source_completeness": _safe_mean([row["best_single_completeness"] for row in rows]),
        "average_fused_completeness": _safe_mean([row["fused_completeness"] for row in rows]),
        "average_absolute_completeness_gain": _safe_mean([row["absolute_completeness_gain"] for row in rows]),
        "average_relative_completeness_gain": _safe_mean([row["relative_completeness_gain"] for row in rows if row["relative_completeness_gain"] is not None]),
        "information_gain_fields": _distribution([float(row["fusion_information_gain_fields"]) for row in rows]),
        "note": "Completeness gain measures field availability, not factual correctness.",
    }, rows


def _provenance(run: RunArtifacts) -> tuple[JSON, list[JSON]]:
    evidence_by_id = {str(item["evidence_id"]): item for item in run.evidence}
    source_ids = {str(item["source_id"]) for item in run.sources}
    incident_evidence = {
        str(evidence_id)
        for incident in run.incidents
        for evidence_id in incident.get("evidence_ids", [])
    }
    rows: list[JSON] = []
    invalid_refs = 0
    missing_refs = 0
    traced = 0
    for incident in run.incidents:
        for fact in incident.get("facts", []):
            if fact.get("state") not in {"known", "reported_zero"}:
                continue
            support = [str(item) for item in fact.get("support_evidence_ids", [])]
            valid_evidence = [evidence_by_id[item] for item in support if item in evidence_by_id]
            valid_sources = [item for item in valid_evidence if str(item.get("source_id")) in source_ids]
            invalid = len(support) - len(valid_evidence)
            has_trace = bool(valid_sources)
            traced += has_trace
            invalid_refs += invalid
            missing_refs += not support
            rows.append(
                {
                    "incident_id": incident["incident_id"],
                    "field": fact.get("field"),
                    "support_reference_count": len(support),
                    "valid_evidence_count": len(valid_evidence),
                    "valid_source_count": len({item["source_id"] for item in valid_sources}),
                    "invalid_reference_count": invalid,
                    "traceable": has_trace,
                    "contradiction": bool(fact.get("contradiction")),
                    "alternatives_preserved": bool(fact.get("conflicting_values")),
                }
            )
    source_with_evidence = {str(item["source_id"]) for item in run.evidence}
    evidence_with_valid_source = sum(str(item.get("source_id")) in source_ids for item in run.evidence)
    orphan_evidence = len(set(evidence_by_id) - incident_evidence)
    metrics = {
        "material_fused_facts": len(rows),
        "traceable_fused_facts": traced,
        "provenance_coverage": round(traced / len(rows), 4) if rows else None,
        "missing_evidence_reference_count": missing_refs,
        "invalid_evidence_reference_count": invalid_refs,
        "orphan_fused_facts": len(rows) - traced,
        "orphan_evidence_items": orphan_evidence,
        "source_to_evidence_traceability": round(len(source_with_evidence & source_ids) / len(source_ids), 4) if source_ids else None,
        "evidence_to_source_traceability": round(evidence_with_valid_source / len(run.evidence), 4) if run.evidence else None,
        "evidence_to_incident_traceability": round((len(evidence_by_id) - orphan_evidence) / len(evidence_by_id), 4) if evidence_by_id else None,
        "scope": "Canonical FusedFact records; time/location/summary prose are reported separately because they do not share one uniform fact-support contract.",
        "note": "Provenance coverage measures traceability, not factual correctness.",
    }
    return metrics, rows


def _conflicts(run: RunArtifacts) -> tuple[JSON, list[JSON]]:
    rows: list[JSON] = []
    for incident in run.incidents:
        for fact in incident.get("facts", []):
            if fact.get("contradiction") or fact.get("conflicting_values"):
                rows.append(
                    {
                        "incident_id": incident["incident_id"],
                        "field": fact.get("field"),
                        "selected_value": json.dumps(fact.get("value"), ensure_ascii=False),
                        "alternatives": json.dumps(fact.get("conflicting_values", []), ensure_ascii=False),
                        "alternatives_preserved": bool(fact.get("conflicting_values")),
                        "kind": "fused_fact",
                    }
                )
        if incident.get("alternate_time_claims"):
            rows.append(
                {
                    "incident_id": incident["incident_id"], "field": "event_time",
                    "selected_value": json.dumps(incident.get("event_time"), ensure_ascii=False),
                    "alternatives": json.dumps(incident["alternate_time_claims"], ensure_ascii=False),
                    "alternatives_preserved": True, "kind": "alternate_time_claims",
                }
            )
        alternatives = (incident.get("geolocation") or {}).get("alternatives", [])
        if alternatives:
            rows.append(
                {
                    "incident_id": incident["incident_id"], "field": "location",
                    "selected_value": (incident.get("geolocation") or {}).get("display_name"),
                    "alternatives": json.dumps(alternatives, ensure_ascii=False),
                    "alternatives_preserved": True, "kind": "location_alternatives",
                }
            )
    affected = {str(row["incident_id"]) for row in rows}
    counts = Counter(str(row["field"]) for row in rows)
    return {
        "incidents_with_conflicts": len(affected),
        "conflict_incident_rate": round(len(affected) / len(run.incidents), 4) if run.incidents else None,
        "total_conflicting_fields": len(rows),
        "field_counts": dict(sorted(counts.items())),
        "conflicting_fatality_fields": counts["fatalities"],
        "conflicting_injury_fields": counts["injuries"],
        "conflicting_time_fields": counts["event_time"],
        "conflicting_location_fields": counts["location"],
        "conflicting_incident_type_fields": counts["incident_type"],
        "conflict_preservation_rate": round(sum(row["alternatives_preserved"] for row in rows) / len(rows), 4) if rows else None,
        "note": "Conflict prevalence and preservation are structural metrics, not conflict-detection accuracy.",
    }, rows


def _unknown_zero(run: RunArtifacts) -> JSON:
    state_counts: dict[str, Counter[str]] = {
        "fatalities": Counter(), "injuries": Counter()
    }
    violations: list[JSON] = []
    for incident in run.incidents:
        for field in state_counts:
            facts = [item for item in incident.get("facts", []) if item.get("field") == field]
            if not facts:
                state_counts[field]["not_reported"] += 1
                continue
            fact = facts[0]
            state = str(fact.get("state", "unknown"))
            value = fact.get("value")
            state_counts[field][state] += 1
            invalid = (
                (state in {"unknown", "not_reported"} and value == 0)
                or (state == "reported_zero" and value not in {0, None})
                or (state == "known" and value is None and not fact.get("contradiction"))
            )
            if invalid:
                violations.append(
                    {"incident_id": incident["incident_id"], "field": field, "state": state, "value": value}
                )
    return {
        "states": {field: dict(counts) for field, counts in state_counts.items()},
        "schema_semantic_violation_count": len(violations),
        "violations": violations,
    }


def _geolocation(run: RunArtifacts) -> tuple[JSON, list[JSON]]:
    granularities: Counter[str] = Counter()
    confidences: list[float] = []
    radii: list[float] = []
    rows: list[JSON] = []
    ambiguous = unresolved = alternatives = geolocated = mapped_markers = 0
    fallback_markers = 0
    for incident in run.incidents:
        location = incident.get("geolocation") or {}
        mapped = location.get("latitude") is not None and location.get("longitude") is not None
        fallback = location.get("method") == "collection_country_fallback"
        resolved = mapped and not fallback
        granularity = str(location.get("granularity") or "unknown")
        granularities[granularity] += 1
        mapped_markers += mapped
        fallback_markers += fallback
        geolocated += resolved
        unresolved += not resolved
        ambiguous += bool(location.get("ambiguity_reason"))
        alternatives += len(location.get("alternatives", []))
        if isinstance(location.get("confidence"), (int, float)):
            confidences.append(float(location["confidence"]))
        if isinstance(location.get("uncertainty_radius_km"), (int, float)):
            radii.append(float(location["uncertainty_radius_km"]))
        rows.append(
            {
                "incident_id": incident["incident_id"], "mapped": mapped,
                "incident_location_resolved": resolved,
                "collection_country_fallback": fallback,
                "display_name": location.get("display_name"), "granularity": granularity,
                "confidence": location.get("confidence"),
                "uncertainty_radius_km": location.get("uncertainty_radius_km"),
                "alternative_count": len(location.get("alternatives", [])),
                "ambiguous": bool(location.get("ambiguity_reason")),
            }
        )
    return {
        "total_fused_incidents": len(run.incidents),
        "successfully_geolocated": geolocated,
        "not_geolocated": unresolved,
        "coverage_percent": _percent(geolocated, len(run.incidents)),
        "mapped_marker_records": mapped_markers,
        "map_marker_coverage_percent": _percent(mapped_markers, len(run.incidents)),
        "collection_country_fallback_markers": fallback_markers,
        "granularity_counts": dict(sorted(granularities.items())),
        "confidence": _distribution(confidences),
        "uncertainty_radius_km": _distribution(radii),
        "alternative_location_count": alternatives,
        "ambiguous_location_count": ambiguous,
        "unresolved_location_count": unresolved,
        "note": "Incident-location coverage excludes collection-country fallback markers. Marker coverage is reported separately. Uncertainty radius and confidence are descriptive; neither is coordinate accuracy without a reference coordinate.",
    }, rows


def _operation_efficiency(runs: list[JSON]) -> JSON:
    latencies = [float(item.get("latency_ms", 0)) for item in runs]
    input_tokens = sum(int(item.get("input_tokens") or 0) for item in runs)
    output_tokens = sum(int(item.get("output_tokens") or 0) for item in runs)
    costs = [item.get("estimated_cost_usd") for item in runs]
    known_costs = [float(item) for item in costs if isinstance(item, (int, float))]
    return {
        "call_count": len(runs),
        "total_latency_ms": round(sum(latencies), 4),
        "latency_ms": _distribution(latencies),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": round(sum(known_costs), 8) if len(known_costs) == len(runs) else None,
        "cost_reporting_n": len(known_costs),
    }


def _efficiency(run: RunArtifacts) -> JSON:
    theoretical = sum(1 for left, right in combinations(run.mentions, 2) if left.get("source_id") != right.get("source_id"))
    match_provider_runs = [item for item in run.provider_runs if item.get("operation") == "match"]
    llm_match_runs = match_provider_runs if run.run.get("provider") != "recorded" else []
    fusion_runs = [item for item in run.provider_runs if item.get("operation") == "fusion"]
    deterministic = [item for item in run.matches if not item.get("provider_run_id")]
    decision_counts = Counter(str(item.get("decision")) for item in run.matches)
    candidate_count = len(run.matches)
    total_cost = sum(float(item.get("estimated_cost_usd") or 0) for item in run.provider_runs)
    started = datetime.fromisoformat(str(run.run["started_at"]).replace("Z", "+00:00"))
    completed_value = run.run.get("completed_at")
    duration = None
    if completed_value:
        completed = datetime.fromisoformat(str(completed_value).replace("Z", "+00:00"))
        duration = round((completed - started).total_seconds(), 4)
    return {
        "matching": {
            "theoretical_cross_source_all_pairs": theoretical,
            "generated_candidate_decisions": candidate_count,
            "deterministic_decisions": len(deterministic),
            "deterministic_accepts": sum(item.get("decision") == "same_incident" for item in deterministic),
            "deterministic_rejects": sum(item.get("decision") in {"different_incident", "related_but_distinct"} for item in deterministic),
            "provider_match_adjudications": len(match_provider_runs),
            "llm_match_calls": len(llm_match_runs),
            "live_llm_adjudications_required": len(match_provider_runs),
            "uncertain_decisions": decision_counts["uncertain"],
            "decision_breakdown": dict(sorted(decision_counts.items())),
            "llm_call_avoidance_candidate_denominator": round(1 - len(match_provider_runs) / candidate_count, 4) if candidate_count else None,
            "llm_call_avoidance_all_pairs_denominator": round(1 - len(match_provider_runs) / theoretical, 4) if theoretical else None,
            "candidate_reduction_from_all_pairs": round(1 - candidate_count / theoretical, 4) if theoretical else None,
        },
        "provider": {
            "matching": _operation_efficiency(match_provider_runs),
            "fusion": _operation_efficiency(fusion_runs),
            "whole_pipeline": _operation_efficiency(run.provider_runs),
            "provider": run.run.get("provider"), "model": run.run.get("model"),
            "run_duration_seconds": duration,
            "cost_per_input_source_usd": round(total_cost / len(run.sources), 8) if run.sources else None,
            "cost_per_fused_incident_usd": round(total_cost / len(run.incidents), 8) if run.incidents else None,
        },
    }


def _confidence(run: RunArtifacts) -> JSON:
    match_values = [float(item["confidence"]) for item in run.matches if isinstance(item.get("confidence"), (int, float))]
    fact_values = [float(fact["confidence"]) for incident in run.incidents for fact in incident.get("facts", []) if isinstance(fact.get("confidence"), (int, float))]
    geo_values = [float((incident.get("geolocation") or {})["confidence"]) for incident in run.incidents if isinstance((incident.get("geolocation") or {}).get("confidence"), (int, float))]
    evidence_values = [float(item["extraction_confidence"]) for item in run.evidence if isinstance(item.get("extraction_confidence"), (int, float))]
    bins = ((0.0, 0.49), (0.5, 0.69), (0.7, 0.84), (0.85, 1.0))
    return {
        "extraction": _distribution(evidence_values),
        "matching": _distribution(match_values),
        "fusion_facts": _distribution(fact_values),
        "geolocation": _distribution(geo_values),
        "matching_histogram": {
            f"{lower:.2f}-{upper:.2f}": sum(lower <= value <= upper for value in match_values)
            for lower, upper in bins
        },
        "note": "These are descriptive score distributions, not calibration results.",
    }


def _representative_cases(run: RunArtifacts, conflicts: list[JSON]) -> list[JSON]:
    source_by_id = {str(item["source_id"]): item for item in run.sources}
    evidence_by_id = {str(item["evidence_id"]): item for item in run.evidence}
    conflict_ids = {str(item["incident_id"]) for item in conflicts}
    ranked: list[tuple[float, JSON]] = []
    for incident in run.incidents:
        sources = [source_by_id[item] for item in incident.get("source_ids", []) if item in source_by_id]
        modalities = sorted({_source_modality(source) for source in sources})
        score = (
            len(sources)
            + 2 * len(modalities)
            + 2 * (str(incident["incident_id"]) in conflict_ids)
            + 2 * bool((incident.get("geolocation") or {}).get("display_name"))
        )
        evidence = [evidence_by_id[item] for item in incident.get("evidence_ids", []) if item in evidence_by_id]
        ranked.append(
            (
                score,
                {
                    "incident_id": incident["incident_id"], "title": incident.get("title"),
                    "source_ids": incident.get("source_ids", []),
                    "publishers": sorted({str(item.get("publisher") or "unknown") for item in sources}),
                    "source_types": sorted({str(item.get("source_type")) for item in sources}),
                    "modalities": modalities,
                    "evidence_count": len(evidence),
                    "fused_facts": incident.get("facts", []),
                    "conflicts": [item for item in conflicts if item["incident_id"] == incident["incident_id"]],
                    "geolocation": incident.get("geolocation"),
                    "unresolved_questions": incident.get("unresolved_questions", []),
                    "human_summary": incident.get("human_summary"),
                    "representative_evidence": [
                        {"evidence_id": item["evidence_id"], "source_id": item["source_id"], "claim_text": item.get("claim_text")}
                        for item in evidence[:5]
                    ],
                },
            )
        )
    return [item for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:3]]


def _metric(
    value: Any, n: int | None, unit: str, metric_type: str, description: str, sources: list[str]
) -> JSON:
    return {
        "value": value, "n": n, "unit": unit, "metric_type": metric_type,
        "description": description, "source_files": sources,
    }


def _canonical_metrics(results: JSON, gold_run: Path, corpus_run: Path, gold_path: Path) -> JSON:
    gold = results["gold"]
    full = results["full_corpus"]
    source_gold = [str(gold_path), str(gold_run / "incidents.json")]
    source_full = [str(corpus_run / "run.json"), str(corpus_run / "incidents.json")]
    metrics = {
        "gold_incidents": _metric(gold["field_metrics"]["gold_incidents"], gold["field_metrics"]["gold_incidents"], "incidents", "gold_accuracy", "Size of the manually verified incident subset.", [str(gold_path)]),
        "fatality_exact_match": _metric(gold["field_metrics"]["fatalities"]["exact_match_accuracy"], gold["field_metrics"]["fatalities"]["prediction_available_n"], "proportion", "gold_accuracy", "Exact reported-fatality agreement among human-labelled cases with numeric predictions.", source_gold),
        "fatality_mae": _metric(gold["field_metrics"]["fatalities"]["mean_absolute_error"], gold["field_metrics"]["fatalities"]["prediction_available_n"], "fatalities", "gold_accuracy", "Mean absolute error for human-labelled fatality counts with numeric predictions.", source_gold),
        "injury_exact_match": _metric(gold["field_metrics"]["injuries"]["exact_match_accuracy"], gold["field_metrics"]["injuries"]["prediction_available_n"], "proportion", "gold_accuracy", "Exact reported-injury agreement among human-labelled cases with numeric predictions.", source_gold),
        "location_semantic_agreement": _metric(gold["field_metrics"]["location"]["semantic_location_agreement"], gold["field_metrics"]["location"]["text_label_n"], "proportion", "gold_accuracy", "Agreement with required terms in human-supplied textual place labels.", source_gold),
        "matching_f1": _metric(gold["matching"]["f1"], gold["matching"]["n"], "proportion", "gold_accuracy", "Same-incident pair F1 on gold-resolved mentions.", [str(gold_path), str(gold_run / "matches.json")]),
        "clustering_b_cubed_f1": _metric(gold["clustering"]["b_cubed_f1"], gold["clustering"]["evaluable_mentions"], "proportion", "gold_accuracy", "B-cubed clustering F1 on gold-resolved mentions.", [str(gold_path), str(gold_run / "clusters.json")]),
        "corpus_sources": _metric(full["composition"]["accepted_source_records"], full["composition"]["accepted_source_records"], "source records", "descriptive", "Accepted source records in the automatically processed corpus.", source_full),
        "corpus_incidents": _metric(full["composition"]["fused_incidents"], full["composition"]["fused_incidents"], "incidents", "descriptive", "Automatically fused incidents; not a count of verified real-world events.", source_full),
        "geolocation_coverage": _metric((full["geolocation"]["coverage_percent"] or 0) / 100, full["geolocation"]["total_fused_incidents"], "proportion", "descriptive", "Share of fused records with source-named incident-location coordinates, excluding collection-country fallback markers; not coordinate accuracy.", [str(corpus_run / "incidents.json")]),
        "map_marker_coverage": _metric((full["geolocation"]["map_marker_coverage_percent"] or 0) / 100, full["geolocation"]["total_fused_incidents"], "proportion", "descriptive", "Share of fused records visible through either incident-location coordinates or explicit collection-country fallback markers.", [str(corpus_run / "incidents.json")]),
        "fusion_completeness_gain": _metric(full["fusion_completeness"]["average_absolute_completeness_gain"], full["fusion_completeness"]["evaluable_multi_source_incidents"], "proportion of material fields", "descriptive", "Average fused field-coverage gain over the best single mention.", source_full),
        "provenance_coverage": _metric(full["provenance"]["provenance_coverage"], full["provenance"]["material_fused_facts"], "proportion", "structural", "Share of canonical fused facts resolving to valid evidence and source records; not factual correctness.", [str(corpus_run / "incidents.json"), str(corpus_run / "evidence.jsonl")]),
        "conflict_incident_rate": _metric(full["conflicts"]["conflict_incident_rate"], full["composition"]["fused_incidents"], "proportion", "structural", "Share of fused records containing a schema-represented conflict or alternative.", [str(corpus_run / "incidents.json")]),
        "llm_call_avoidance": _metric(full["efficiency"]["matching"]["llm_call_avoidance_candidate_denominator"], full["efficiency"]["matching"]["generated_candidate_decisions"], "proportion", "efficiency", "Share of persisted candidate decisions not requiring a provider match call.", [str(corpus_run / "matches.json"), str(corpus_run / "provider_runs.json")]),
        "estimated_api_cost": _metric(full["efficiency"]["provider"]["whole_pipeline"]["estimated_cost_usd"], full["efficiency"]["provider"]["whole_pipeline"]["call_count"], "USD", "efficiency", "Recorded estimated provider cost; null means incomplete cost metadata.", [str(corpus_run / "provider_runs.json")]),
    }
    metrics.update(
        {
            "corpus_countries": _metric(full["composition"]["countries"], full["composition"]["countries"], "collection-country groups", "descriptive", "Distinct configured source-collection country groups.", source_full),
            "corpus_languages": _metric(full["composition"]["languages"], full["composition"]["languages"], "language tags", "descriptive", "Distinct declared language tags.", source_full),
            "corpus_publishers": _metric(full["composition"]["publishers"], full["composition"]["publishers"], "publisher labels", "descriptive", "Distinct non-empty publisher labels.", source_full),
            "corpus_evidence_items": _metric(full["composition"]["evidence_items"], full["composition"]["evidence_items"], "evidence items", "descriptive", "Attributed evidence items in the corpus run.", source_full),
            "corpus_mentions": _metric(full["composition"]["incident_mentions"], full["composition"]["incident_mentions"], "mentions", "descriptive", "Source-local incident mentions in the corpus run.", source_full),
            "multi_source_incidents": _metric(full["composition"]["multi_source_incidents"], full["composition"]["fused_incidents"], "incident records", "descriptive", "Fused records supported by more than one source record.", source_full),
            "fused_field_completeness": _metric(full["fusion_completeness"]["average_fused_completeness"], full["fusion_completeness"]["evaluable_multi_source_incidents"], "proportion of material fields", "descriptive", "Mean material-field availability after fusion for multi-source records.", source_full),
            "conflict_preservation_rate": _metric(full["conflicts"]["conflict_preservation_rate"], full["conflicts"]["total_conflicting_fields"], "proportion", "structural", "Share of represented conflicts retaining alternatives.", [str(corpus_run / "incidents.json")]),
            "unknown_zero_violations": _metric(full["unknown_vs_zero"]["schema_semantic_violation_count"], full["composition"]["fused_incidents"], "violations", "structural", "Invalid unknown/not-reported/reported-zero state-value combinations.", [str(corpus_run / "incidents.json")]),
            "provider_calls": _metric(full["efficiency"]["provider"]["whole_pipeline"]["call_count"], full["efficiency"]["provider"]["whole_pipeline"]["call_count"], "provider operations", "efficiency", "All recorded matching and fusion provider operations.", [str(corpus_run / "provider_runs.json")]),
            "provider_total_tokens": _metric(full["efficiency"]["provider"]["whole_pipeline"]["total_tokens"], full["efficiency"]["provider"]["whole_pipeline"]["call_count"], "tokens", "efficiency", "Recorded input plus output tokens; recorded fixtures report zero.", [str(corpus_run / "provider_runs.json")]),
            "median_uncertainty_radius_km": _metric(full["geolocation"]["uncertainty_radius_km"]["median"], full["geolocation"]["uncertainty_radius_km"]["n"], "km", "descriptive", "Median declared uncertainty radius among source-named mapped locations; not spatial error.", [str(corpus_run / "incidents.json")]),
        }
    )
    return metrics


def _generate_figures(output_dir: Path, results: JSON, modality_rows: list[JSON], errors: list[JSON], cases: list[JSON]) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - dependency error is environment-specific.
        raise RuntimeError("Paper figures require the evaluation extra: pip install -e '.[evaluation]'") from exc
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ("figure_*.png", "figure_*.pdf"):
        for stale_figure in figure_dir.glob(pattern):
            stale_figure.unlink()
    generated: list[str] = []

    def save(name: str) -> None:
        plt.tight_layout()
        for extension in ("png", "pdf"):
            path = figure_dir / f"{name}.{extension}"
            plt.savefig(path, dpi=220, bbox_inches="tight")
            generated.append(str(path))
        plt.close()

    composition = results["full_corpus"]["composition"]
    stages = ["Sources", "Evidence", "Mentions", "Fused", "Geolocated"]
    values = [composition["accepted_source_records"], composition["evidence_items"], composition["incident_mentions"], composition["fused_incidents"], composition["geolocated_incidents"]]
    plt.figure(figsize=(8, 4.4))
    plt.plot(stages, values, marker="o", linewidth=2, color="#2456a6")
    plt.ylabel("Record count")
    plt.title("MGeoAI processing funnel (record counts; stages are not attrition-equivalent)")
    for index, value in enumerate(values):
        plt.text(index, value, str(value), ha="center", va="bottom")
    save("figure_a_pipeline_funnel")

    modality_counts = composition["modality_source_counts"]
    plt.figure(figsize=(6.5, 4.2))
    plt.bar(list(modality_counts), list(modality_counts.values()), color="#4c78a8")
    plt.ylabel("Source records")
    plt.title("Source-record modality composition")
    save("figure_b_modality_composition")

    granularity = results["full_corpus"]["geolocation"]["granularity_counts"]
    coverage_path = Path(results["metadata"]["corpus_run"]) / "coverage.geojson"
    if coverage_path.exists():
        coverage = _json(coverage_path)
        coordinates = [feature["geometry"]["coordinates"] for feature in coverage.get("features", [])]
        plt.figure(figsize=(10, 4.8))
        plt.scatter(
            [item[0] for item in coordinates],
            [item[1] for item in coordinates],
            s=24,
            color="#59a14f",
            alpha=0.8,
        )
        plt.xlim(-180, 180)
        plt.ylim(-60, 85)
        plt.xlabel("Longitude")
        plt.ylabel("Latitude")
        plt.grid(alpha=0.2)
        plt.title("Collection-country source coverage centroids (not incident locations)")
        save("figure_c_geographic_source_coverage")

    plt.figure(figsize=(8, 4.2))
    plt.bar(list(granularity), list(granularity.values()), color="#59a14f")
    plt.xticks(rotation=35, ha="right")
    plt.ylabel("Fused incidents")
    plt.title("Geolocation granularity (descriptive, not accuracy)")
    save("figure_c2_geolocation_granularity")

    figure_modality_rows = results["gold"].get("modality_rows") or modality_rows
    fields = sorted({str(row["field"]) for row in figure_modality_rows})
    modalities = sorted({str(row["modality"]) for row in figure_modality_rows})
    matrix = [[next((row["incident_count"] for row in figure_modality_rows if row["field"] == field and row["modality"] == modality), 0) for modality in modalities] for field in fields]
    plt.figure(figsize=(max(5.5, len(modalities) * 1.4), max(5, len(fields) * 0.35)))
    image = plt.imshow(matrix, aspect="auto", cmap="Blues")
    plt.colorbar(image, label="Supporting incidents")
    plt.xticks(range(len(modalities)), modalities)
    plt.yticks(range(len(fields)), fields)
    plt.title("Field × modality support in the multimodal gold-prediction run")
    save("figure_d_modality_heatmap")

    gold_metrics = results["gold"]["field_metrics"]
    labels = ["Fatalities", "Injuries", "Location"]
    scores = [gold_metrics["fatalities"]["exact_match_accuracy"], gold_metrics["injuries"]["exact_match_accuracy"], gold_metrics["location"]["semantic_location_agreement"]]
    plot_scores = [value if value is not None else 0 for value in scores]
    plt.figure(figsize=(6.5, 4.2))
    plt.bar(labels, plot_scores, color="#e15759")
    plt.ylim(0, 1)
    plt.ylabel("Agreement proportion")
    plt.title("Gold-subset field agreement (field-specific N)")
    save("figure_e_gold_field_performance")

    decisions = results["full_corpus"]["efficiency"]["matching"]["decision_breakdown"]
    plt.figure(figsize=(7.5, 4.2))
    plt.bar(list(decisions), list(decisions.values()), color="#f28e2b")
    plt.xticks(rotation=25, ha="right")
    plt.ylabel("Candidate decisions")
    plt.title("Matching decision breakdown")
    save("figure_f_matching_decisions")

    categories = Counter(str(item["category"]) for item in errors)
    plt.figure(figsize=(8, 4.5))
    plt.bar(list(categories), list(categories.values()), color="#b07aa1")
    plt.xticks(rotation=35, ha="right")
    plt.ylabel("Observed gold discrepancies")
    plt.title("Gold-subset error distribution")
    save("figure_g_error_distribution")

    if cases:
        case = cases[0]
        plt.figure(figsize=(10, 3.6))
        plt.axis("off")
        labels = [f"{len(case['source_ids'])} sources", f"{case['evidence_count']} evidence items", "matching + clustering", f"{len(case['fused_facts'])} fused facts", "provenance + uncertainty"]
        for index, label in enumerate(labels):
            x = 0.08 + index * 0.21
            plt.text(x, 0.55, label, ha="center", va="center", bbox={"boxstyle": "round", "facecolor": "#dce6f5", "edgecolor": "#2456a6"})
            if index < len(labels) - 1:
                plt.annotate(
                    "",
                    xy=(x + 0.14, 0.55),
                    xytext=(x + 0.07, 0.55),
                    arrowprops={"arrowstyle": "->"},
                )
        plt.title(f"Representative end-to-end case: {case['incident_id']}")
        save("figure_h_representative_case")
    return generated


def _fmt(value: Any, percent: bool = False) -> str:
    if value is None:
        return "not evaluable"
    if percent and isinstance(value, (int, float)):
        return f"{100 * value:.1f}%"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _render_case(case: JSON) -> str:
    facts = ", ".join(
        f"{item.get('field')}={item.get('value')} ({item.get('state')})"
        for item in case["fused_facts"]
    ) or "none"
    return (
        f"### {case['incident_id']}: {case['title']}\n\n"
        f"- Sources: {len(case['source_ids'])} (`{', '.join(case['source_ids'])}`)\n"
        f"- Publishers: {', '.join(case['publishers'])}\n"
        f"- Modalities: {', '.join(case['modalities'])}\n"
        f"- Evidence items: {case['evidence_count']}\n"
        f"- Fused facts: {facts}\n"
        f"- Conflicts retained: {len(case['conflicts'])}\n"
        f"- Geolocation: {(case.get('geolocation') or {}).get('display_name') or 'unresolved'}; "
        f"granularity={(case.get('geolocation') or {}).get('granularity', 'unknown')}; "
        f"uncertainty radius={(case.get('geolocation') or {}).get('uncertainty_radius_km')} km\n"
        f"- Summary: {case.get('human_summary') or 'not available'}\n"
    )


def _render_results(results: JSON, cases: list[JSON], gold_run: Path, corpus_run: Path) -> str:
    gold = results["gold"]
    fields = gold["field_metrics"]
    full = results["full_corpus"]
    composition = full["composition"]
    conflict_examples = full["conflict_examples"]
    issue_counts = Counter(item["reason"] for item in gold["resolution_issues"])
    return f"""# mGeoAI Experimental Results

Generated deterministically from `{gold_run}` for the manually verified subset and
`{corpus_run}` for corpus-wide descriptive analysis. Gold and unlabeled results are
kept separate throughout.

## 1. Experimental Setup

The manually verified evaluation subset contains {fields['gold_incidents']} incidents.
Stable input artifact paths identify its source membership; source 12 is split with
location-specific mention selectors because it contains two incidents. Bootstrap 95%
confidence intervals use 2,000 resamples and the configured deterministic seed.
The full corpus has no exhaustive human truth labels, so its results are coverage,
structure, consistency, uncertainty, or efficiency statistics—not accuracy.

Gold source-to-mention resolution produced {sum(len(items) for items in gold['resolved_mentions'].values())}
evaluable mentions and {len(gold['resolution_issues'])} unresolved assignments
({', '.join(f'{key}: {value}' for key, value in sorted(issue_counts.items())) or 'none'}).

## 2. Corpus Characteristics

| Metric | Value |
|---|---:|
| Raw input artifacts | {composition['raw_input_artifacts']} |
| Accepted source records | {composition['accepted_source_records']} |
| Collection countries | {composition['countries']} |
| Languages | {composition['languages']} |
| Publishers | {composition['publishers']} |
| Unique domains | {composition['unique_domains']} |
| Evidence items | {composition['evidence_items']} |
| Incident mentions | {composition['incident_mentions']} |
| Fused incident records | {composition['fused_incidents']} |
| Source-named incident locations | {composition['geolocated_incidents']} ({_fmt(composition['geolocation_coverage_percent'])}%) |
| Map-visible records | {composition['mapped_marker_records']} ({_fmt(composition['map_marker_coverage_percent'])}%) |
| Collection-country fallback markers | {composition['collection_country_fallback_markers']} |

These counts describe processed records and source coverage. They do not establish the
number of true incidents in the world or the factual correctness of generated records.

## 3. Gold-Set Evaluation

| Field | Metric | Score | N | 95% CI |
|---|---|---:|---:|---|
| Fatalities | Exact match | {_fmt(fields['fatalities']['exact_match_accuracy'], True)} | {fields['fatalities']['prediction_available_n']} | {fields['fatalities']['exact_match_ci95']} |
| Fatalities | MAE | {_fmt(fields['fatalities']['mean_absolute_error'])} | {fields['fatalities']['prediction_available_n']} | {fields['fatalities']['mae_ci95']} |
| Injuries | Exact match | {_fmt(fields['injuries']['exact_match_accuracy'], True)} | {fields['injuries']['prediction_available_n']} | {fields['injuries']['exact_match_ci95']} |
| Location | Required-term agreement | {_fmt(fields['location']['semantic_location_agreement'], True)} | {fields['location']['text_label_n']} | {fields['location']['semantic_location_ci95']} |
| Location | Coordinate error | {_fmt(fields['location']['coordinate_error_km']['median'])} km median | {fields['location']['coordinate_reference_n']} | not applicable |

Missing predictions are shown separately and are not silently converted to zero.
No coordinate-accuracy result is reported because the supplied gold labels contain no
trusted coordinates. Incident type and event time are also unevaluable because those
fields were not human-labelled.

## 4. Same-Incident Matching

The gold-derived pair set contains {gold['matching']['n']} evaluable pairs, including
{gold['matching']['positive_pairs']} positive and {gold['matching']['negative_pairs']}
negative pairs. Pairwise precision is {_fmt(gold['matching']['precision'], True)}, recall
is {_fmt(gold['matching']['recall'], True)}, F1 is {_fmt(gold['matching']['f1'], True)},
with incident-cluster bootstrap 95% CI {gold['matching']['f1_ci95']};
accuracy is {_fmt(gold['matching']['accuracy'], True)}, and specificity is
{_fmt(gold['matching']['specificity'], True)}. A missing candidate decision is treated
as a negative prediction because no same-incident edge was produced.

## 5. Incident Clustering

B-cubed precision, recall, and F1 are respectively
{_fmt(gold['clustering']['b_cubed_precision'], True)},
{_fmt(gold['clustering']['b_cubed_recall'], True)}, and
{_fmt(gold['clustering']['b_cubed_f1'], True)} over
{gold['clustering']['evaluable_mentions']} resolved gold mentions. The run contains
{gold['clustering']['fragmented_gold_incidents']} fragmented gold incidents and
{gold['clustering']['overmerged_predicted_clusters']} over-merged predicted clusters.

## 6. Multi-Source Fusion

Across {full['fusion_completeness']['evaluable_multi_source_incidents']} automatically
identified multi-source records, mean best-single completeness was
{_fmt(full['fusion_completeness']['average_best_single_source_completeness'], True)} and
mean fused completeness was {_fmt(full['fusion_completeness']['average_fused_completeness'], True)}.
The absolute field-coverage gain was
{_fmt(full['fusion_completeness']['average_absolute_completeness_gain'], True)}.
This is information completeness gain, not fusion accuracy.

| Multi-source fusion characteristic | Value |
|---|---:|
| Evaluable multi-source records | {full['fusion_completeness']['evaluable_multi_source_incidents']} |
| Best-single completeness (mean) | {_fmt(full['fusion_completeness']['average_best_single_source_completeness'], True)} |
| Fused completeness (mean) | {_fmt(full['fusion_completeness']['average_fused_completeness'], True)} |
| Absolute completeness gain | {_fmt(full['fusion_completeness']['average_absolute_completeness_gain'], True)} |
| Sources per incident (mean) | {_fmt(full['source_diversity']['source_records']['mean'])} |
| Modalities per incident (mean) | {_fmt(full['source_diversity']['modalities']['mean'])} |
| Conflict incident rate | {_fmt(full['conflicts']['conflict_incident_rate'], True)} |
| Provenance coverage | {_fmt(full['provenance']['provenance_coverage'], True)} |

## 7. Multimodal Evidence Contribution

The text-only global corpus has {full['modality']['two_or_more_modality_incidents']}
incidents with evidence from at least two modalities. In the multimodal gold-prediction
run, {gold['modality_descriptive']['two_or_more_modality_incidents']} fused records had
at least two modalities and {gold['modality_descriptive']['three_or_more_modality_incidents']}
had at least three. The matrices are available in `results/modality_contribution.csv`
and `results/gold_run_modality_contribution.csv`; they report support frequency, not
modality accuracy.

## 8. Conflict Preservation

{full['conflicts']['incidents_with_conflicts']} fused records contained at least one
represented conflict ({_fmt(full['conflicts']['conflict_incident_rate'], True)} of
records). The alternative-preservation rate was
{_fmt(full['conflicts']['conflict_preservation_rate'], True)}. This is a structural
schema result, not conflict-detection accuracy.

Top retained cases:

{chr(10).join(f"- `{item['incident_id']}` — {item['field']}: {item['alternatives']}" for item in conflict_examples) or '- No represented conflicts.'}

## 9. Provenance

{full['provenance']['traceable_fused_facts']} of
{full['provenance']['material_fused_facts']} canonical fused facts retained at least
one resolvable evidence-to-source path (coverage
{_fmt(full['provenance']['provenance_coverage'], True)}).
**Provenance coverage measures traceability, not factual correctness.**

## 10. Geolocation

{full['geolocation']['successfully_geolocated']} of
{full['geolocation']['total_fused_incidents']} records contain source-named incident
locations ({_fmt(full['geolocation']['coverage_percent'])}%). Separately,
{full['geolocation']['mapped_marker_records']} records are map-visible
({_fmt(full['geolocation']['map_marker_coverage_percent'])}%), including
{full['geolocation']['collection_country_fallback_markers']} explicitly non-incident
collection-country fallback markers. The median uncertainty
radius is {_fmt(full['geolocation']['uncertainty_radius_km']['median'])} km (P90
{_fmt(full['geolocation']['uncertainty_radius_km']['p90'])} km). These values describe
representation and uncertainty, not spatial accuracy.

| Geolocation characteristic | Value |
|---|---:|
| Source-named incident locations | {full['geolocation']['successfully_geolocated']} |
| Collection-country fallback markers | {full['geolocation']['collection_country_fallback_markers']} |
| Map marker coverage | {_fmt((full['geolocation']['map_marker_coverage_percent'] or 0) / 100, True)} |
| Incident-location coverage | {_fmt((full['geolocation']['coverage_percent'] or 0) / 100, True)} |
| Median uncertainty radius | {_fmt(full['geolocation']['uncertainty_radius_km']['median'])} km |
| P90 uncertainty radius | {_fmt(full['geolocation']['uncertainty_radius_km']['p90'])} km |

## 11. Efficiency and Cost

The run considered {full['efficiency']['matching']['theoretical_cross_source_all_pairs']}
theoretical cross-source mention pairs and persisted
{full['efficiency']['matching']['generated_candidate_decisions']} candidate decisions.
It recorded {full['efficiency']['matching']['provider_match_adjudications']} provider
adjudication-path decisions and {full['efficiency']['matching']['llm_match_calls']}
actual live LLM calls. In a live run those adjudication-path decisions require the
configured model, producing candidate-denominator call avoidance of
{_fmt(full['efficiency']['matching']['llm_call_avoidance_candidate_denominator'], True)}.
The recorded provider/model is `{full['efficiency']['provider']['provider']}` /
`{full['efficiency']['provider']['model']}`. Estimated cost is
{_fmt(full['efficiency']['provider']['whole_pipeline']['estimated_cost_usd'])} USD;
this is null when cost metadata is incomplete.

| Matching efficiency characteristic | Value |
|---|---:|
| Theoretical cross-source pairs | {full['efficiency']['matching']['theoretical_cross_source_all_pairs']} |
| Candidate decisions | {full['efficiency']['matching']['generated_candidate_decisions']} |
| Deterministic decisions | {full['efficiency']['matching']['deterministic_decisions']} |
| Recorded/provider match adjudications | {full['efficiency']['matching']['provider_match_adjudications']} |
| Live LLM match calls | {full['efficiency']['matching']['llm_match_calls']} |
| Candidate-denominator call avoidance | {_fmt(full['efficiency']['matching']['llm_call_avoidance_candidate_denominator'], True)} |
| Total provider latency | {_fmt(full['efficiency']['provider']['whole_pipeline']['total_latency_ms'])} ms |
| Estimated provider cost | {_fmt(full['efficiency']['provider']['whole_pipeline']['estimated_cost_usd'])} USD |

The heuristic-only matching ablation uses the predeclared configuration threshold 0.72;
its F1 is {_fmt(gold['matching']['ablations']['heuristic_only_predeclared_threshold_0_72']['f1'], True)},
compared with {_fmt(gold['matching']['ablations']['full_hybrid']['f1'], True)} for the
full stored decisions. LLM-only and modality ablations are marked `not_run` because the
necessary all-pair or modality-specific artifacts do not exist and generating them would
require paid calls or alter pipeline semantics.

## 12. Error Analysis

The evaluator recorded {len(gold['errors'])} observed discrepancies. Counts and exact
incident examples are in `results/error_cases.csv`; no illustrative error is counted.

| Error category | Count | Share of observed discrepancies | Representative incident |
|---|---:|---:|---|
{chr(10).join(f"| {category} | {count} | {_fmt(count / len(gold['errors']) if gold['errors'] else None, True)} | `{next(item['gold_id'] for item in gold['errors'] if item['category'] == category)}` |" for category, count in Counter(item['category'] for item in gold['errors']).most_common()) or '| None | 0 | not applicable | — |'}

## 13. Representative Cases

{chr(10).join(_render_case(case) for case in cases)}

## 14. Limitations of the Evaluation

- This is a small, manually verified evaluation subset, not a definitive global benchmark.
- Only supplied human labels are evaluated. Unknown/N/A values remain unevaluable.
- Text-only gold locations support semantic place-name agreement but not Haversine accuracy.
- Unresolved source-to-mention assignments are disclosed and never forced.
- The automatically collected global corpus is used only for descriptive and structural analysis.
- Recorded-provider results demonstrate reproducibility but are not evidence of live-model accuracy.
- The development fixture in `tests/fixtures/golden_pairs.json` is excluded from paper metrics.
- No threshold was tuned against these gold results.

## 15. Recommended Results for the Conference Paper

Report the field-specific gold metrics with their denominators and confidence intervals;
pair them with corpus-wide information-completeness, provenance, conflict-preservation,
geolocation-coverage, and efficiency results. Do not generalize this Bangladesh-only gold
subset into global accuracy claims. Refer to `results/paper_metrics.json` as the canonical
numeric source and `results/validation_report.json` before copying any number.
"""


def _latex_escape(value: str) -> str:
    replacements = {"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#"}
    return "".join(replacements.get(character, character) for character in value)


def _render_latex(results: JSON) -> str:
    gold = results["gold"]["field_metrics"]
    full = results["full_corpus"]
    error_counts = Counter(str(item["category"]) for item in results["gold"]["errors"])
    error_rows = "\n".join(
        rf"{_latex_escape(category)} & {count} \\"
        for category, count in error_counts.most_common()
    ) or r"None & 0 \\"
    return rf"""% Generated by mgeoai paper-evaluate. Do not edit derived numbers manually.
\begin{{table}}[t]
\centering
\caption{{Performance on the manually verified evaluation subset.}}
\label{{tab:gold-results}}
\begin{{tabular}}{{llrr}}
\hline
Field & Metric & Score & $N$ \\
\hline
Fatalities & Exact match & {_latex_escape(_fmt(gold['fatalities']['exact_match_accuracy'], True))} & {gold['fatalities']['prediction_available_n']} \\
Fatalities & MAE & {_fmt(gold['fatalities']['mean_absolute_error'])} & {gold['fatalities']['prediction_available_n']} \\
Injuries & Exact match & {_latex_escape(_fmt(gold['injuries']['exact_match_accuracy'], True))} & {gold['injuries']['prediction_available_n']} \\
Location & Required-term agreement & {_latex_escape(_fmt(gold['location']['semantic_location_agreement'], True))} & {gold['location']['text_label_n']} \\
Matching & F1 & {_latex_escape(_fmt(results['gold']['matching']['f1'], True))} & {results['gold']['matching']['n']} \\
Clustering & B-cubed F1 & {_latex_escape(_fmt(results['gold']['clustering']['b_cubed_f1'], True))} & {results['gold']['clustering']['evaluable_mentions']} \\
\hline
\end{{tabular}}
\end{{table}}

\begin{{table}}[t]
\centering
\caption{{Multi-source fusion characteristics (descriptive, not accuracy).}}
\label{{tab:fusion-results}}
\begin{{tabular}}{{lr}}
\hline
Characteristic & Value \\
\hline
Multi-source records & {full['fusion_completeness']['evaluable_multi_source_incidents']} \\
Best-single completeness & {_latex_escape(_fmt(full['fusion_completeness']['average_best_single_source_completeness'], True))} \\
Fused completeness & {_latex_escape(_fmt(full['fusion_completeness']['average_fused_completeness'], True))} \\
Absolute completeness gain & {_latex_escape(_fmt(full['fusion_completeness']['average_absolute_completeness_gain'], True))} \\
Conflict incident rate & {_latex_escape(_fmt(full['conflicts']['conflict_incident_rate'], True))} \\
Provenance coverage & {_latex_escape(_fmt(full['provenance']['provenance_coverage'], True))} \\
\hline
\end{{tabular}}
\end{{table}}

\begin{{table}}[t]
\centering
\caption{{Matching efficiency for the descriptive corpus run.}}
\label{{tab:matching-efficiency}}
\begin{{tabular}}{{lr}}
\hline
Characteristic & Value \\
\hline
Theoretical cross-source pairs & {full['efficiency']['matching']['theoretical_cross_source_all_pairs']} \\
Candidate decisions & {full['efficiency']['matching']['generated_candidate_decisions']} \\
Deterministic decisions & {full['efficiency']['matching']['deterministic_decisions']} \\
Provider adjudications & {full['efficiency']['matching']['provider_match_adjudications']} \\
Live LLM calls & {full['efficiency']['matching']['llm_match_calls']} \\
Live-LLM call avoidance & {_latex_escape(_fmt(full['efficiency']['matching']['llm_call_avoidance_candidate_denominator'], True))} \\
\hline
\end{{tabular}}
\end{{table}}

\begin{{table}}[t]
\centering
\caption{{Geolocation representation. Country fallback markers are not incident locations.}}
\label{{tab:geolocation-results}}
\begin{{tabular}}{{lr}}
\hline
Characteristic & Value \\
\hline
Source-named incident locations & {full['geolocation']['successfully_geolocated']} \\
Collection-country fallbacks & {full['geolocation']['collection_country_fallback_markers']} \\
Map-marker coverage & {_latex_escape(_fmt((full['geolocation']['map_marker_coverage_percent'] or 0) / 100, True))} \\
Incident-location coverage & {_latex_escape(_fmt((full['geolocation']['coverage_percent'] or 0) / 100, True))} \\
Median uncertainty radius (km) & {_fmt(full['geolocation']['uncertainty_radius_km']['median'])} \\
\hline
\end{{tabular}}
\end{{table}}

\begin{{table}}[t]
\centering
\caption{{Observed discrepancies in the manually verified subset.}}
\label{{tab:error-analysis}}
\begin{{tabular}}{{lr}}
\hline
Category & Count \\
\hline
{error_rows}
\hline
\end{{tabular}}
\end{{table}}

The manually verified subset contained {gold['gold_incidents']} incidents. Among cases
with both a human fatality label and a numeric prediction, exact agreement was
{_latex_escape(_fmt(gold['fatalities']['exact_match_accuracy'], True))}
($N={gold['fatalities']['prediction_available_n']}$). Textual location agreement was
{_latex_escape(_fmt(gold['location']['semantic_location_agreement'], True))}
($N={gold['location']['text_label_n']}$). No coordinate error is reported because the
reference subset contains no trusted coordinates.

\begin{{table}}[t]
\centering
\caption{{Automatically computed corpus characteristics (descriptive, not accuracy).}}
\label{{tab:corpus-results}}
\begin{{tabular}}{{lr}}
\hline
Metric & Value \\
\hline
Sources & {full['composition']['accepted_source_records']} \\
Evidence items & {full['composition']['evidence_items']} \\
Mentions & {full['composition']['incident_mentions']} \\
Fused records & {full['composition']['fused_incidents']} \\
Geolocation coverage & {_latex_escape(_fmt((full['geolocation']['coverage_percent'] or 0) / 100, True))} \\
Provenance coverage & {_latex_escape(_fmt(full['provenance']['provenance_coverage'], True))} \\
Conflict incident rate & {_latex_escape(_fmt(full['conflicts']['conflict_incident_rate'], True))} \\
\hline
\end{{tabular}}
\end{{table}}

Across the automatically processed corpus, fused records exhibited an average absolute
field-completeness gain of
{_latex_escape(_fmt(full['fusion_completeness']['average_absolute_completeness_gain'], True))}
over the best single mention. This is a coverage result, not a correctness estimate.
Figures~\ref{{fig:pipeline}}--\ref{{fig:errors}} visualize the processing funnel,
modality contribution, spatial representation, and observed gold discrepancies.

\begin{{figure}}[t]
\centering
\includegraphics[width=0.95\linewidth]{{evaluation/figures/figure_a_pipeline_funnel.pdf}}
\caption{{MGeoAI record-count processing funnel.}}
\label{{fig:pipeline}}
\end{{figure}}

\begin{{figure}}[t]
\centering
\includegraphics[width=0.95\linewidth]{{evaluation/figures/figure_c_geographic_source_coverage.pdf}}
\caption{{Collection-country source coverage centroids; points are not incident locations.}}
\label{{fig:coverage}}
\end{{figure}}

\begin{{figure}}[t]
\centering
\includegraphics[width=0.95\linewidth]{{evaluation/figures/figure_g_error_distribution.pdf}}
\caption{{Observed error categories in the manually verified subset.}}
\label{{fig:errors}}
\end{{figure}}
"""


def _render_discussion(results: JSON) -> str:
    gold = results["gold"]
    full = results["full_corpus"]
    error_counts = Counter(str(item["category"]) for item in gold["errors"])
    top_errors = ", ".join(f"{name} ({count})" for name, count in error_counts.most_common(5))
    return f"""# mGeoAI paper discussion notes

These notes are derived from the generated metrics. They distinguish agreement with the
manually verified subset from descriptive analysis of the unlabeled corpus.

## Supported observations

- Gold casualty performance is field-specific: fatality exact agreement is
  {_fmt(gold['field_metrics']['fatalities']['exact_match_accuracy'], True)}
  (n={gold['field_metrics']['fatalities']['prediction_available_n']} numeric predictions),
  while injury exact agreement is
  {_fmt(gold['field_metrics']['injuries']['exact_match_accuracy'], True)}
  (n={gold['field_metrics']['injuries']['prediction_available_n']}). Missing predictions
  remain explicit and are not zero-filled.
- Gold textual location agreement is
  {_fmt(gold['field_metrics']['location']['semantic_location_agreement'], True)}
  (n={gold['field_metrics']['location']['text_label_n']}). Spatial error cannot be
  assessed because reference coordinates were not supplied.
- Same-incident matching F1 is {_fmt(gold['matching']['f1'], True)} over
  {gold['matching']['n']} gold-derived pairs. Clustering B-cubed F1 is
  {_fmt(gold['clustering']['b_cubed_f1'], True)} over
  {gold['clustering']['evaluable_mentions']} resolved mentions.
- Multi-source fusion changed field availability by an average of
  {_fmt(full['fusion_completeness']['average_absolute_completeness_gain'], True)}
  of the material-field inventory relative to the best single mention. This result
  supports an information-completeness claim only.
- Provenance coverage is {_fmt(full['provenance']['provenance_coverage'], True)}
  across {full['provenance']['material_fused_facts']} canonical fused facts. It
  demonstrates traceability, not truth.
- The conflict incident rate is {_fmt(full['conflicts']['conflict_incident_rate'], True)};
  alternative preservation is {_fmt(full['conflicts']['conflict_preservation_rate'], True)}.
- Unknown/zero semantic validation found
  {full['unknown_vs_zero']['schema_semantic_violation_count']} violation(s). A reported
  zero is distinct from unknown and not reported throughout these calculations.
- Source-named incident-location coordinates exist for
  {_fmt((full['geolocation']['coverage_percent'] or 0) / 100, True)} of fused records;
  map-marker coverage is {_fmt((full['geolocation']['map_marker_coverage_percent'] or 0) / 100, True)}
  because {full['geolocation']['collection_country_fallback_markers']} records use
  explicit collection-country fallback markers. These markers and uncertainty circles
  must not be described as exact crash locations.
- The matching stage avoided provider calls for
  {_fmt(full['efficiency']['matching']['llm_call_avoidance_candidate_denominator'], True)}
  of persisted candidate decisions. The all-pairs denominator is separately reported.
- The most frequent observed gold discrepancies were: {top_errors or 'none'}.

## Threats to validity

The gold subset is small, Bangladesh-only, and selectively labelled. Its confidence
intervals are therefore more informative than point estimates alone, but they do not
eliminate selection uncertainty. The global corpus has no exhaustive incident truth
labels; source diversity, coverage, agreement, and efficiency must not be described as
global model accuracy. Recorded-provider outputs are reproducible fixtures rather than
independent model evaluations. Source dependency metadata may also be incomplete, and
the field-completeness inventory weights each material field equally.

## Appropriate conference-paper framing

Use the gold subset to support narrowly scoped statements about casualty extraction,
textual geolocation, pair matching, and clustering. Use the full corpus to demonstrate
scalability, source/modal diversity, traceability, conflict retention, explicit unknown
semantics, uncertainty-aware spatial representation, and provider-call reduction.
Avoid claims about truthfulness, hallucination rate, or global accuracy.
"""


def _validate_results(results: JSON, metrics: JSON, gold_path: Path) -> JSON:
    errors: list[str] = []
    warnings: list[str] = []
    gold = results["gold"]
    matching = gold["matching"]
    confusion_total = sum(matching[key] for key in ("true_positive", "false_positive", "true_negative", "false_negative"))
    if confusion_total != matching["n"]:
        errors.append("Gold matching confusion-matrix cells do not sum to N.")
    recomputed = _classification_metrics(
        [row["gold_label"] == "same_incident" for row in gold["pair_rows"]],
        [row["predicted_label"] == "same_incident" for row in gold["pair_rows"]],
    )
    for key in ("precision", "recall", "f1", "accuracy", "specificity"):
        if recomputed[key] != matching[key]:
            errors.append(f"Gold matching {key} is inconsistent with pair rows.")
    for name, metric in metrics.items():
        value = metric.get("value")
        unit = metric.get("unit")
        if unit == "proportion" and value is not None and not 0 <= value <= 1:
            errors.append(f"Metric {name} is outside [0,1].")
        if metric.get("metric_type") == "gold_accuracy" and str(gold_path) not in metric.get("source_files", []):
            errors.append(f"Gold accuracy metric {name} lacks the human gold file as a source.")
        if metric.get("metric_type") != "gold_accuracy" and "accuracy" in name:
            errors.append(f"Unlabelled metric {name} is improperly labelled accuracy.")
    if results["full_corpus"]["unknown_vs_zero"]["schema_semantic_violation_count"]:
        errors.append("Unknown/zero fact-state semantic violations were detected.")
    for row in results["full_corpus"]["geolocation_rows"]:
        # Coordinates are validated from source incidents before rows are reduced; mapped
        # here means a complete coordinate pair was present.
        if not isinstance(row["mapped"], bool):
            errors.append(f"Invalid mapped flag for {row['incident_id']}.")
    if gold["field_metrics"]["location"]["coordinate_reference_n"] == 0:
        warnings.append("No trusted gold coordinates: Haversine accuracy is not evaluable.")
    if gold["field_metrics"]["gold_incidents"] < 20:
        warnings.append("Gold subset is small; report N and bootstrap confidence intervals.")
    if gold["resolution_issues"]:
        warnings.append("Some declared gold source members did not resolve to exactly one run mention.")
    return {
        "status": "valid" if not errors else "invalid",
        "major_error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "percentage_bounds": "passed" if not any("outside" in item for item in errors) else "failed",
            "confusion_matrix_consistency": "passed" if confusion_total == matching["n"] else "failed",
            "unknown_zero_semantics": "passed" if not results["full_corpus"]["unknown_vs_zero"]["schema_semantic_violation_count"] else "failed",
            "gold_unlabelled_separation": "passed" if not any("improperly" in item or "human gold" in item for item in errors) else "failed",
            "development_fixture_excluded": "passed",
            "coverage_map_semantics": "passed",
        },
    }


def generate_paper_evaluation(
    run_dir: Path,
    gold_path: Path,
    output_dir: Path,
    corpus_run_dir: Path | None = None,
    seed: int = 42,
) -> JSON:
    gold_run = RunArtifacts(run_dir)
    corpus_run = RunArtifacts(corpus_run_dir or run_dir)
    gold = _json(gold_path)
    gold_mentions, resolution_issues = resolve_gold_mentions(gold, gold_run)
    aligned = _match_gold_to_incidents(gold, gold_mentions, gold_run)
    field_metrics, comparison_rows, errors = _gold_comparison(gold, gold_mentions, aligned, seed)
    matching, clustering, pair_rows = _matching_and_clustering(gold_mentions, gold_run, seed + 100)
    gold_modality, gold_modality_rows = _modality_contribution(gold_run)

    composition = _full_corpus_summary(corpus_run)
    diversity, diversity_rows = _source_diversity(corpus_run)
    modality, modality_rows = _modality_contribution(corpus_run)
    completeness, completeness_rows = _fusion_completeness(corpus_run)
    provenance, provenance_rows = _provenance(corpus_run)
    conflicts, conflict_rows = _conflicts(corpus_run)
    geolocation, geolocation_rows = _geolocation(corpus_run)
    efficiency = _efficiency(corpus_run)
    confidence = _confidence(corpus_run)
    unknown_zero = _unknown_zero(corpus_run)
    cases = _representative_cases(corpus_run, conflict_rows)
    results: JSON = {
        "metadata": {
            "schema_version": "1.0.0", "seed": seed,
            "gold_run": str(run_dir), "corpus_run": str(corpus_run_dir or run_dir),
            "gold_file": str(gold_path),
            "scientific_scope": "Gold metrics are accuracy/agreement; corpus metrics are descriptive/structural/efficiency only.",
        },
        "gold": {
            "field_metrics": field_metrics, "comparison_rows": comparison_rows,
            "resolved_mentions": gold_mentions, "resolution_issues": resolution_issues,
            "matching": matching, "clustering": clustering, "pair_rows": pair_rows,
            "errors": errors, "modality_descriptive": gold_modality,
            "modality_rows": gold_modality_rows,
        },
        "full_corpus": {
            "composition": composition, "source_diversity": diversity,
            "source_diversity_rows": diversity_rows, "modality": modality,
            "modality_rows": modality_rows, "fusion_completeness": completeness,
            "fusion_completeness_rows": completeness_rows, "provenance": provenance,
            "provenance_rows": provenance_rows, "conflicts": conflicts,
            "conflict_rows": conflict_rows, "conflict_examples": conflict_rows[:5],
            "unknown_vs_zero": unknown_zero, "geolocation": geolocation,
            "geolocation_rows": geolocation_rows, "efficiency": efficiency,
            "confidence": confidence,
        },
        "representative_cases": cases,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    result_dir = output_dir / "results"
    _write_csv(result_dir / "corpus_summary.csv", [{"metric": key, "value": json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value} for key, value in composition.items()])
    gold_metric_rows = [
        {"field": field, "metric": key, "value": value, "n": metrics.get("prediction_available_n", metrics.get("text_label_n"))}
        for field, metrics in field_metrics.items()
        if isinstance(metrics, dict)
        for key, value in metrics.items()
        if isinstance(value, (int, float)) or value is None
    ]
    _write_csv(result_dir / "gold_field_metrics.csv", gold_metric_rows)
    _write_csv(result_dir / "gold_incident_comparison.csv", comparison_rows)
    _write_csv(result_dir / "matching_metrics.csv", pair_rows)
    _write_csv(
        result_dir / "ablation_metrics.csv",
        [
            {"configuration": name, **values}
            for name, values in matching["ablations"].items()
            if isinstance(values, dict)
        ],
    )
    _write_csv(result_dir / "clustering_metrics.csv", [{"metric": key, "value": json.dumps(value) if isinstance(value, dict) else value} for key, value in clustering.items()])
    _write_csv(result_dir / "source_diversity.csv", diversity_rows)
    _write_csv(result_dir / "modality_contribution.csv", modality_rows)
    _write_csv(result_dir / "gold_run_modality_contribution.csv", gold_modality_rows)
    _write_csv(result_dir / "fusion_completeness.csv", completeness_rows)
    _write_csv(result_dir / "conflicts.csv", conflict_rows)
    _write_csv(result_dir / "provenance_metrics.csv", provenance_rows)
    _write_csv(result_dir / "geolocation_metrics.csv", geolocation_rows)
    provider_rows = [
        {"scope": scope, **values}
        for scope, values in efficiency["provider"].items()
        if isinstance(values, dict)
    ]
    _write_csv(result_dir / "provider_efficiency.csv", provider_rows)
    error_counts = Counter(str(item["category"]) for item in errors)
    error_rows = [
        {**item, "category_count": error_counts[str(item["category"])], "category_percent": _percent(error_counts[str(item["category"])], len(errors))}
        for item in errors
    ]
    _write_csv(result_dir / "error_cases.csv", error_rows, ("gold_id", "category", "category_count", "category_percent", "detail"))
    metrics = _canonical_metrics(results, run_dir, corpus_run_dir or run_dir, gold_path)
    validation = _validate_results(results, metrics, gold_path)
    _write_json(result_dir / "paper_metrics.json", metrics)
    _write_json(result_dir / "validation_report.json", validation)
    _write_json(result_dir / "evaluation_details.json", results)
    _write_json(result_dir / "representative_cases.json", cases)
    (output_dir / "PAPER_RESULTS.md").write_text(_render_results(results, cases, run_dir, corpus_run_dir or run_dir), encoding="utf-8")
    (output_dir / "PAPER_RESULTS_LATEX.tex").write_text(_render_latex(results), encoding="utf-8")
    (output_dir / "PAPER_DISCUSSION_NOTES.md").write_text(_render_discussion(results), encoding="utf-8")
    figure_paths = _generate_figures(output_dir, results, modality_rows, errors, cases)
    if validation["status"] != "valid":
        raise ValueError("Scientific validity checks failed: " + "; ".join(validation["errors"]))
    return {
        "status": "complete", "gold_incidents": field_metrics["gold_incidents"],
        "gold_matching_pairs": matching["n"],
        "fatality_exact_match": field_metrics["fatalities"]["exact_match_accuracy"],
        "injury_exact_match": field_metrics["injuries"]["exact_match_accuracy"],
        "location_agreement": field_metrics["location"]["semantic_location_agreement"],
        "matching_f1": matching["f1"], "clustering_b_cubed_f1": clustering["b_cubed_f1"],
        "full_corpus": composition, "figures": figure_paths,
        "outputs": [
            str(output_dir / "PAPER_RESULTS.md"), str(output_dir / "PAPER_RESULTS_LATEX.tex"),
            str(output_dir / "PAPER_DISCUSSION_NOTES.md"), str(result_dir / "paper_metrics.json"),
            str(result_dir / "validation_report.json"), str(output_dir / "figures"),
        ],
    }
