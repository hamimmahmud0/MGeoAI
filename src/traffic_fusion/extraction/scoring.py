"""Gold construction, annotator agreement, and model scoring for article extraction.

Gold rule (documented in the journal and guidelines): a field is gold only if a strict
majority of the annotators who labelled the article (at least `MIN_LABELS`, default 3)
gave the same normalised value; otherwise it is unresolved and never guessed. Per-field
metrics are computed only on articles whose gold has exactly one accident. For
multi-accident articles only the accident flag and the accident count are scored.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

from traffic_fusion.annotation.stats import cohen_kappa, krippendorff_alpha_nominal
from traffic_fusion.extraction.annotation_store import ArticleLabel, ArticleStore

MIN_LABELS = 3
FIELDS = ("fatalities", "casualities", "vehicles", "date", "country", "location")
UNRESOLVED = "__unresolved__"


def _tokens(text: str | None) -> frozenset[str]:
    return frozenset(re.findall(r"\w+", (text or "").casefold()))


def norm(field: str, value: Any) -> Any:
    """Comparable form of one field value (None stays None)."""
    if value is None:
        return None
    if field == "vehicles":
        return tuple(sorted(value))
    if field == "date":
        return str(value)[:10]
    if field == "country":
        return str(value).strip().casefold()
    if field == "location":
        return tuple(sorted(_tokens(str(value))))
    return value


def _accidents(label: ArticleLabel) -> list[dict[str, Any]]:
    return [a.wire() for a in label.accidents if a.accident]


def majority(values: list[Any]) -> Any:
    """Strict majority (> half of all votes, None counts as a vote) or UNRESOLVED."""
    counts = Counter(values)
    top, votes = counts.most_common(1)[0]
    return top if votes * 2 > len(values) else UNRESOLVED


def build_gold(labels: dict[str, dict[str, ArticleLabel]], min_labels: int = MIN_LABELS
               ) -> dict[str, dict[str, Any]]:
    """{article_id: {...}} for articles with enough labels. Unresolved parts are marked."""
    by_article: dict[str, list[ArticleLabel]] = {}
    for per_user in labels.values():
        for article_id, label in per_user.items():
            by_article.setdefault(article_id, []).append(label)
    gold: dict[str, dict[str, Any]] = {}
    for article_id, group in by_article.items():
        if len(group) < min_labels:
            continue
        unusable = majority([g.unusable for g in group])
        if unusable is True:
            gold[article_id] = {"usable": False, "annotators": len(group)}
            continue
        flag = majority([bool(_accidents(g)) for g in group])
        count = majority([len(_accidents(g)) for g in group])
        row: dict[str, Any] = {"usable": unusable is not UNRESOLVED, "annotators": len(group),
                               "accident": flag, "accident_count": count, "fields": {}}
        if flag is True and count == 1:
            singles = [_accidents(g)[0] for g in group if len(_accidents(g)) == 1]
            for field in FIELDS:
                values = [norm(field, s[field]) for s in singles]
                row["fields"][field] = majority(values) if len(values) * 2 > len(group) else UNRESOLVED
            row["raw"] = {f: Counter(json.dumps(s[f]) for s in singles).most_common(1)[0][0]
                          for f in ("location", "country", "date", "longitude and latitude")}
        gold[article_id] = row
    return gold


def annotation_stats(store: ArticleStore) -> dict[str, Any]:
    labels = store.all_latest()
    total = len(store.article_ids())
    per_article: dict[str, list[ArticleLabel]] = {}
    for per_user in labels.values():
        for article_id, label in per_user.items():
            per_article.setdefault(article_id, []).append(label)
    flat = {u: {a: str(bool(_accidents(r))) for a, r in recs.items()} for u, recs in labels.items()}
    kappas = {}
    names = sorted(flat)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            kappa, n = cohen_kappa(flat[a], flat[b])
            kappas[f"{a}|{b}"] = {"kappa": None if kappa is None else round(kappa, 4), "articles": n}
    units = [[str(bool(_accidents(r))) for r in rows] for rows in per_article.values() if len(rows) >= 2]
    alpha = krippendorff_alpha_nominal(units)
    # pairwise exact agreement per field (both annotators gave exactly one accident)
    agree: dict[str, list[int]] = {f: [0, 0] for f in FIELDS}
    for rows in per_article.values():
        singles = [_accidents(r)[0] for r in rows if len(_accidents(r)) == 1]
        for i, left in enumerate(singles):
            for right in singles[i + 1:]:
                for f in FIELDS:
                    agree[f][1] += 1
                    agree[f][0] += norm(f, left[f]) == norm(f, right[f])
    gold = build_gold(labels)
    return {
        "articles_total": total,
        "annotators": {u: len(r) for u, r in labels.items()},
        "articles_with_1plus_labels": len(per_article),
        "articles_with_2plus_labels": sum(len(r) >= 2 for r in per_article.values()),
        "articles_with_3plus_labels": sum(len(r) >= 3 for r in per_article.values()),
        "accident_flag_alpha": None if alpha is None else round(alpha, 4),
        "accident_flag_cohen_kappa": kappas,
        "field_exact_agreement": {f: {"agree": v[0], "pairs": v[1],
                                      "rate": round(v[0] / v[1], 4) if v[1] else None}
                                  for f, v in agree.items()},
        "gold_articles": len(gold),
        "gold_unresolved_flag": sum(1 for g in gold.values() if g.get("accident") is UNRESOLVED),
        "min_labels_for_gold": MIN_LABELS,
    }


# ---- model scoring ---------------------------------------------------------------------
def _ci(values: list[float], seed: int = 7, resamples: int = 1000) -> list[float] | None:
    if len(values) < 5:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(resamples))
    return [round(means[int(0.025 * resamples)], 4), round(means[int(0.975 * resamples)], 4)]


def _rate(values: list[float]) -> dict[str, Any]:
    return {"n": len(values), "value": round(sum(values) / len(values), 4) if values else None,
            "ci95": _ci(values)}


def _prf(tp: int, fp: int, fn: int) -> dict[str, float | None]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else None
    return {"precision": p, "recall": r, "f1": f}


def model_metrics(config_dir: Path, gold: dict[str, dict[str, Any]], store: ArticleStore,
                  labels: dict[str, dict[str, ArticleLabel]]) -> dict[str, Any]:
    results = {p.stem: json.loads(p.read_text("utf-8"))
               for p in config_dir.glob("*.json") if p.name != "run.json"}
    ok = {k: v for k, v in results.items() if v.get("status") == "ok"}
    flag_rows: list[tuple[bool, bool]] = []
    count_hits: list[float] = []
    fields: dict[str, list[float]] = {f: [] for f in FIELDS}
    mae: list[float] = []
    jacc: list[float] = []
    loc_overlap: list[float] = []
    for aid, result in ok.items():
        g = gold.get(aid)
        if not g or not g.get("usable") or g.get("accident") is UNRESOLVED:
            continue
        model = [a for a in result["accidents"] if a["accident"]]
        flag_rows.append((bool(g["accident"]), bool(model)))
        if g["accident"] is True and g.get("accident_count") not in (UNRESOLVED, None):
            count_hits.append(float(len(model) == g["accident_count"]))
        if g["accident"] is True and g.get("accident_count") == 1 and len(model) == 1:
            for f in FIELDS:
                want = g["fields"].get(f, UNRESOLVED)
                if want is UNRESOLVED:
                    continue
                got = norm(f, model[0][f])
                fields[f].append(float(got == want))
                if f == "fatalities" and want is not None and got is not None:
                    mae.append(abs(float(got) - float(want)))
                if f == "vehicles" and want is not None and got is not None:
                    union = set(want) | set(got)
                    jacc.append(len(set(want) & set(got)) / len(union) if union else 1.0)
                if f == "location" and want and got:
                    union = set(want) | set(got)
                    loc_overlap.append(len(set(want) & set(got)) / len(union))
    tp = sum(1 for want, got in flag_rows if want and got)
    fp = sum(1 for want, got in flag_rows if not want and got)
    fn = sum(1 for want, got in flag_rows if want and not got)
    quotes = sum(v.get("quality", {}).get("quotes", 0) for v in ok.values())
    verbatim = sum(v.get("quality", {}).get("verbatim", 0) for v in ok.values())
    return {
        "articles_ok": len(ok), "articles_failed": sum(1 for v in results.values() if v.get("status") == "failed"),
        "scored_articles": len(flag_rows),
        "accident_flag": {**_prf(tp, fp, fn), "tp": tp, "fp": fp, "fn": fn,
                          "tn": sum(1 for want, got in flag_rows if not want and not got)},
        "accident_count_correct": _rate(count_hits),
        "fields_exact": {f: _rate(v) for f, v in fields.items()},
        "fatalities_mae": round(sum(mae) / len(mae), 3) if mae else None,
        "vehicles_jaccard": round(sum(jacc) / len(jacc), 4) if jacc else None,
        "location_token_overlap": round(sum(loc_overlap) / len(loc_overlap), 4) if loc_overlap else None,
        "evidence_quotes_verbatim": {"quotes": quotes, "verbatim": verbatim,
                                     "rate": round(verbatim / quotes, 4) if quotes else None},
        "mean_latency_ms": round(sum(v.get("latency_ms") or 0 for v in ok.values()) / len(ok)) if ok else None,
        "note": "Per-field metrics use only articles whose gold has exactly one accident and where "
                "the gold field is resolved (strict majority of >= 3 annotators).",
    }
