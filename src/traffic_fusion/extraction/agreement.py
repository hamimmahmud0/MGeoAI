"""Agreement statistics between annotators (nominal labels)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping


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
