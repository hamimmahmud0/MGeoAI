from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from itertools import combinations
from typing import Any

from traffic_fusion.annotation.store import LabelRecord

Labels = dict[str, dict[str, LabelRecord]]


def krippendorff_alpha_nominal(units: list[list[str]]) -> float | None:
    """Krippendorff's alpha for nominal data; units may have differing rater counts."""
    coincidence: dict[tuple[str, str], float] = defaultdict(float)
    for values in units:
        m = len(values)
        if m < 2:
            continue
        for i, a in enumerate(values):
            for j, b in enumerate(values):
                if i != j:
                    coincidence[(a, b)] += 1 / (m - 1)
    totals: dict[str, float] = defaultdict(float)
    for (a, _), weight in coincidence.items():
        totals[a] += weight
    n = sum(totals.values())
    if n <= 1:
        return None
    observed = sum(w for (a, b), w in coincidence.items() if a != b) / n
    expected = sum(totals[a] * totals[b] for a in totals for b in totals if a != b) / (n * (n - 1))
    if expected == 0:
        return None
    return 1 - observed / expected


def cohen_kappa(a: Mapping[str, str], b: Mapping[str, str]) -> tuple[float | None, int]:
    shared = sorted(set(a) & set(b))
    n = len(shared)
    if not n:
        return None, 0
    observed = sum(a[k] == b[k] for k in shared) / n
    categories = {a[k] for k in shared} | {b[k] for k in shared}
    expected = sum(
        (sum(a[k] == c for k in shared) / n) * (sum(b[k] == c for k in shared) / n)
        for c in categories
    )
    if expected == 1:
        return None, n
    return (observed - expected) / (1 - expected), n


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def agreement_report(labels: Labels) -> dict[str, Any]:
    flat = {user: {item: rec.label for item, rec in recs.items()} for user, recs in labels.items()}
    per_item: dict[str, list[str]] = defaultdict(list)
    for recs in flat.values():
        for item, label in recs.items():
            per_item[item].append(label)
    binary = [["same" if v == "same_incident" else "not" for v in vals] for vals in per_item.values()]
    pairwise = {}
    for left, right in combinations(sorted(flat), 2):
        kappa, n = cohen_kappa(flat[left], flat[right])
        pairwise[f"{left}|{right}"] = {"kappa": _round(kappa), "items": n}
    return {
        "annotators": {user: len(recs) for user, recs in flat.items()},
        "items_with_2plus_labels": sum(len(v) >= 2 for v in per_item.values()),
        "krippendorff_alpha_nominal": _round(krippendorff_alpha_nominal(list(per_item.values()))),
        "krippendorff_alpha_same_vs_not": _round(krippendorff_alpha_nominal(binary)),
        "pairwise_cohen_kappa": pairwise,
    }


def consensus(labels: Labels, min_labels: int = 3) -> dict[str, dict[str, Any]]:
    """Strict-majority consensus per item; items without one stay unresolved."""
    per_item: dict[str, list[str]] = defaultdict(list)
    for recs in labels.values():
        for item, rec in recs.items():
            per_item[item].append(rec.label)
    result: dict[str, dict[str, Any]] = {}
    for item, votes in per_item.items():
        top = max(set(votes), key=votes.count)
        resolved = len(votes) >= min_labels and votes.count(top) > len(votes) / 2
        result[item] = {"label": top if resolved else None, "votes": sorted(votes)}
    return result
