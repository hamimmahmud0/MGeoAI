"""Scoring and report for the grouping benchmark (agreement with the human-checked reference groups)."""

from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from traffic_fusion.extraction.grouping import Corpus

NEG_STRATA = ("hard_decoy", "hard_near", "hard_similar", "easy")
RESAMPLES = 1000


def _tokens(text: str | None) -> set[str]:
    return set(re.findall(r"\w+", (text or "").casefold()))


def load(root: Path) -> tuple[dict[str, Any], Corpus]:
    pairs = json.loads((root / "matching" / "pairs.json").read_text("utf-8"))
    return pairs, Corpus(root)


# ---- predictions per method -----------------------------------------------------------------------
def pair_predictions(root: Path, name: str, pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """{pair_id: {pred: bool|None, ab, ba, ...}} for a pair-judge method folder."""
    folder = root / "matching" / name
    out: dict[str, Any] = {}
    for p in pairs:
        rows = {}
        for order in ("AB", "BA"):
            path = folder / f"{p['pair_id']}__{order}.json"
            if path.exists():
                rows[order] = json.loads(path.read_text("utf-8"))
        ab, ba = rows.get("AB"), rows.get("BA")
        if not ab or not ba or ab["status"] != "ok" or ba["status"] != "ok":
            out[p["pair_id"]] = {"pred": None, "missing": True}
            continue
        d1, d2 = ab["decision"], ba["decision"]
        out[p["pair_id"]] = {
            "pred": d1 == "same_incident" and d2 == "same_incident", "ab": d1, "ba": d2,
            "consistent": d1 == d2, "uncertain": "uncertain" in (d1, d2),
            "confidence": min(ab["confidence"], ba["confidence"]),
            "rationale": ab.get("rationale", ""), "tokens": (ab.get("input_tokens") or 0) + (ab.get("output_tokens") or 0)
            + (ba.get("input_tokens") or 0) + (ba.get("output_tokens") or 0),
        }
    return out


def cluster_runs(root: Path, variant: str, corpus: Corpus) -> list[dict[str, str]]:
    folder = root / "matching" / f"cluster-{variant}"
    runs = []
    for path in sorted(folder.glob("run*.json")) if folder.is_dir() else []:
        row = json.loads(path.read_text("utf-8"))
        if row.get("status") == "ok":
            assign = {}
            for n, cluster in enumerate(row["clusters"]):
                for a in cluster:
                    assign[a] = f"c{n}"
            for a in corpus.ids:
                assign.setdefault(a, f"s_{a}")
            runs.append(assign)
    return runs


def consensus(runs: list[dict[str, str]], ids: list[str]) -> dict[str, str]:
    """Same cluster if together in a strict majority of runs (transitive closure)."""
    parent = {a: a for a in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    need = len(runs) // 2 + 1
    members: dict[tuple[str, str], int] = Counter()
    for assign in runs:
        groups: dict[str, list[str]] = defaultdict(list)
        for a, c in assign.items():
            groups[c].append(a)
        for g in groups.values():
            for i, a in enumerate(sorted(g)):
                for b in sorted(g)[i + 1:]:
                    members[(a, b)] += 1
    for (a, b), n in members.items():
        if n >= need:
            parent[find(a)] = find(b)
    return {a: find(a) for a in ids}


# ---- metrics --------------------------------------------------------------------------------------
def weights(pairs: list[dict[str, Any]], population: dict[str, int]) -> np.ndarray:
    sampled = Counter(p["stratum"] for p in pairs)
    return np.array([1.0 if p["stratum"] == "positive" else population[p["stratum"]] / sampled[p["stratum"]] for p in pairs])


def prf(tp: float, fp: float, fn: float) -> dict[str, float | None]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else None
    return {"precision": p, "recall": r, "f1": f}


def cluster_bootstrap_weights(pairs: list[dict[str, Any]], seed: int = 11) -> np.ndarray:
    """(RESAMPLES x pairs) multiplicity of each pair when groups are resampled with replacement."""
    rng = np.random.default_rng(seed)
    groups = sorted({p["group_a"] for p in pairs} | {p["group_b"] for p in pairs})
    index = {g: i for i, g in enumerate(groups)}
    ga = np.array([index[p["group_a"]] for p in pairs])
    gb = np.array([index[p["group_b"]] for p in pairs])
    same = ga == gb
    counts = np.stack([np.bincount(rng.integers(0, len(groups), len(groups)), minlength=len(groups)) for _ in range(RESAMPLES)])
    return np.where(same, counts[:, ga], counts[:, ga] * counts[:, gb]).astype(float)


def score_method(pairs: list[dict[str, Any]], pred: Mapping[str, bool | None], w: np.ndarray, boot: np.ndarray) -> dict[str, Any]:
    keep = np.array([pred.get(p["pair_id"]) is not None for p in pairs])
    y = np.array([p["label"] == "same" for p in pairs])
    yhat = np.array([bool(pred.get(p["pair_id"])) for p in pairs])

    def est(wt: np.ndarray) -> dict[str, float | None]:
        m = keep.astype(float)
        return prf(float((wt * m * (y & yhat)).sum()), float((wt * m * (~y & yhat)).sum()), float((wt * m * (y & ~yhat)).sum()))

    point = est(w)
    resampled = [est(w * boot[i]) for i in range(boot.shape[0])]
    ci = {k: [float(np.nanpercentile([r[k] if r[k] is not None else np.nan for r in resampled], q)) for q in (2.5, 97.5)]
          for k in ("precision", "recall", "f1")}
    f1_samples = np.array([r["f1"] if r["f1"] is not None else np.nan for r in resampled])
    raw = prf(float((keep & y & yhat).sum()), float((keep & ~y & yhat).sum()), float((keep & y & ~yhat).sum()))
    by_stratum: dict[str, Any] = {}
    for s in ("positive", *NEG_STRATA):
        idx = np.array([p["stratum"] == s for p in pairs]) & keep
        n = int(idx.sum())
        hits = int((idx & yhat).sum())
        by_stratum[s] = {"n": n, "predicted_same": hits, "rate": hits / n if n else None}
    sub: dict[str, Any] = {}
    for key in ("cross_language", "toll_differs", "same_publisher"):
        idx = np.array([p["stratum"] == "positive" and p[key] for p in pairs]) & keep
        sub[key] = {"n": int(idx.sum()), "recall": float((idx & yhat).sum() / idx.sum()) if idx.sum() else None}
    return {"estimated": point, "ci95": ci, "raw_on_sample": raw, "by_stratum": by_stratum, "positive_subsets": sub,
            "pairs_scored": int(keep.sum()), "pairs_missing": int((~keep).sum()), "_f1_samples": f1_samples}


def tfidf_baseline(corpus: Corpus, pairs: list[dict[str, Any]], w: np.ndarray) -> dict[str, Any]:
    """Cosine threshold chosen to maximise weighted F1 on this same sample: an OPTIMISTIC reference."""
    scores = np.array([p["tfidf"] for p in pairs])
    y = np.array([p["label"] == "same" for p in pairs])
    best, thr = -1.0, 0.0
    for t in np.unique(scores):
        yh = scores >= t
        f = prf(float((w * (y & yh)).sum()), float((w * (~y & yh)).sum()), float((w * (y & ~yh)).sum()))["f1"] or 0
        if f > best:
            best, thr = f, float(t)
    return {p["pair_id"]: bool(p["tfidf"] >= thr) for p in pairs} | {"__threshold__": thr}


def embedding_baselines(root: Path, pairs: list[dict[str, Any]], w: np.ndarray) -> dict[str, dict[str, bool]]:
    """Cosine of multilingual sentence embeddings (scores stored by scripts/embedding_baseline.py).

    Two variants per model: the threshold that maximises weighted F1 on this same sample (optimistic, like
    TF-IDF), and a threshold learned on the other folds (accident groups split into 5 folds), which is the
    honest estimate of what a threshold chosen in advance would do.
    """
    path = root / "matching" / "embedding_baseline.json"
    if not path.exists():
        return {}
    y = np.array([p["label"] == "same" for p in pairs])

    def best(scores: np.ndarray, rows: np.ndarray) -> float:
        top, thr = -1.0, 0.0
        for t in np.unique(scores[rows]):
            yh = scores >= t
            f = prf(float((w * (y & yh))[rows].sum()), float((w * (~y & yh))[rows].sum()), float((w * (y & ~yh))[rows].sum()))["f1"] or 0
            if f > top:
                top, thr = f, float(t)
        return thr

    groups = sorted({p["group_a"] for p in pairs})
    fold = {g: i % 5 for i, g in enumerate(groups)}
    fold_of = np.array([fold[p["group_a"]] for p in pairs])
    out: dict[str, dict[str, bool]] = {}
    for name, entry in json.loads(path.read_text("utf-8"))["models"].items():
        scores = np.array([entry["cosine"][p["pair_id"]] for p in pairs])
        thr = best(scores, np.ones(len(pairs), dtype=bool))
        out[f"baseline embeddings {name} (oracle threshold)"] = {p["pair_id"]: bool(scores[i] >= thr) for i, p in enumerate(pairs)}
        cv: dict[str, bool] = {}
        for k in range(5):
            t = best(scores, fold_of != k)
            for i, p in enumerate(pairs):
                if fold_of[i] == k:
                    cv[p["pair_id"]] = bool(scores[i] >= t)
        out[f"baseline embeddings {name} (threshold learned on other folds)"] = cv
    return out


def fields_rule(corpus: Corpus, pairs: list[dict[str, Any]]) -> dict[str, bool]:
    """Rule fixed in advance on the model extraction: same country, dates within 1 day, location word overlap >= 0.3."""
    out = {}
    for p in pairs:
        ra, rb = corpus.model.get(p["a"], []), corpus.model.get(p["b"], [])
        ok = False
        if len(ra) == 1 and len(rb) == 1:
            ca, cb = (ra[0].get("country") or "").casefold(), (rb[0].get("country") or "").casefold()
            da, db = _d(ra[0].get("date")), _d(rb[0].get("date"))
            ta, tb = _tokens(ra[0].get("location")), _tokens(rb[0].get("location"))
            overlap = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
            ok = bool(ca and ca == cb and da and db and abs((da - db).days) <= 1 and overlap >= 0.3)
        out[p["pair_id"]] = ok
    return out


def _d(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _comb(x: int) -> float:
    return x * (x - 1) / 2


def cluster_metrics(corpus: Corpus, assign: dict[str, str]) -> dict[str, Any]:
    ids = corpus.ids
    truth = [corpus.group[a] for a in ids]
    pred = [assign[a] for a in ids]
    n = len(ids)
    tp = fp = fn = 0
    for i in range(n):
        for j in range(i + 1, n):
            s_t, s_p = truth[i] == truth[j], pred[i] == pred[j]
            tp += s_t and s_p
            fp += (not s_t) and s_p
            fn += s_t and (not s_p)
    pt: dict[str, set[int]] = defaultdict(set)
    pp: dict[str, set[int]] = defaultdict(set)
    for i in range(n):
        pt[truth[i]].add(i)
        pp[pred[i]].add(i)
    bp = br = 0.0
    for i in range(n):
        ct, cp = pt[truth[i]], pp[pred[i]]
        inter = len(ct & cp)
        bp += inter / len(cp)
        br += inter / len(ct)
    bp, br = bp / n, br / n
    # adjusted Rand index
    cont: Counter[tuple[str, str]] = Counter(zip(truth, pred, strict=True))
    sum_c = sum(_comb(v) for v in cont.values())
    sum_t = sum(_comb(len(v)) for v in pt.values())
    sum_p = sum(_comb(len(v)) for v in pp.values())
    expected = sum_t * sum_p / _comb(n)
    ari = (sum_c - expected) / (0.5 * (sum_t + sum_p) - expected) if (sum_t + sum_p) else 1.0
    exact = sum(1 for v in pt.values() if any(pp[p] == v for p in {pred[i] for i in v}))
    merged = sum(1 for v in pp.values() if len({truth[i] for i in v}) > 1)
    split = sum(1 for v in pt.values() if len({pred[i] for i in v}) > 1)
    return {"pairwise_all": prf(tp, fp, fn), "bcubed": {"precision": bp, "recall": br, "f1": 2 * bp * br / (bp + br) if bp + br else 0},
            "ari": ari, "clusters": len(pp), "true_groups": len(pt), "groups_recovered_exactly": exact,
            "predicted_clusters_merging_groups": merged, "true_groups_split": split}


def evaluate(root: Path) -> dict[str, Any]:
    doc, corpus = load(root)
    pairs = doc["pairs"]
    w = weights(pairs, doc["population"])
    boot = cluster_bootstrap_weights(pairs)
    methods: dict[str, Any] = {}
    preds: dict[str, Any] = {}
    details: dict[str, Any] = {}
    matching = root / "matching"
    suffixes = ["", *sorted({p.name[p.name.index("@"):] for p in matching.iterdir() if p.is_dir() and "@" in p.name})] if matching.is_dir() else [""]
    for suffix in suffixes:
        tag = f" [{suffix[1:]}]" if suffix else ""
        for base in ("pair-full", "pair-fields-both", "pair-fields-human", "pair-fields-model"):
            name, label = base + suffix, base + tag
            if (matching / name).is_dir():
                res = pair_predictions(root, name, pairs)
                details[label] = res
                preds[label] = {k: v["pred"] for k, v in res.items()}
                m = score_method(pairs, preds[label], w, boot)
                ok = [v for v in res.values() if not v.get("missing")]
                m["order_inconsistent"] = sum(1 for v in ok if not v["consistent"]) / len(ok) if ok else None
                m["uncertain_rate"] = sum(1 for v in ok if v["uncertain"]) / len(ok) if ok else None
                m["tokens"] = sum(v["tokens"] for v in ok)
                methods[label] = m
        for variant in ("cards", "full"):
            runs = cluster_runs(root, variant + suffix, corpus)
            if not runs:
                continue
            cons = consensus(runs, corpus.ids) if len(runs) >= 3 else None
            for label, assign in [*((f"cluster-{variant}{tag} run{k}", r) for k, r in enumerate(runs)), *([(f"cluster-{variant}{tag} consensus", cons)] if cons else [])]:
                pred = {p["pair_id"]: assign[p["a"]] == assign[p["b"]] for p in pairs}
                preds[label] = pred
                m = score_method(pairs, pred, w, boot)
                m["cluster"] = cluster_metrics(corpus, assign)
                methods[label] = m
    t = tfidf_baseline(corpus, pairs, w)
    thr = t.pop("__threshold__")
    methods["baseline tf-idf (oracle threshold)"] = score_method(pairs, t, w, boot) | {"threshold": thr}
    preds["baseline tf-idf (oracle threshold)"] = t
    for label, pred in embedding_baselines(root, pairs, w).items():
        preds[label] = pred
        methods[label] = score_method(pairs, pred, w, boot)
    fr = fields_rule(corpus, pairs)
    methods["baseline fields rule"] = score_method(pairs, fr, w, boot)
    preds["baseline fields rule"] = fr
    # paired difference in estimated F1 against pair-full
    if "pair-full" in methods:
        base = methods["pair-full"]["_f1_samples"]
        for name, m in methods.items():
            if name != "pair-full":
                d = m["_f1_samples"] - base
                m["f1_minus_pair_full_ci95"] = [float(np.nanpercentile(d, 2.5)), float(np.nanpercentile(d, 97.5))]
    # candidate gold errors: every LLM method disagrees with the label
    llm = [n for n in ("pair-full", "pair-fields-both") if n in preds]
    cons_names = [n for n in preds if n.endswith("consensus") and "[" not in n]
    suspects = []
    for p in pairs:
        votes = [bool(preds[n].get(p["pair_id"])) for n in llm + cons_names if preds[n].get(p["pair_id"]) is not None]
        if len(votes) >= 2 and all(v != (p["label"] == "same") for v in votes):
            suspects.append(p["pair_id"])
    for m in methods.values():
        m.pop("_f1_samples", None)
    return {"generated_utc": datetime.now(UTC).isoformat(timespec="seconds"), "methods": methods, "suspects": suspects,
            "population": doc["population"], "pairs": len(pairs), "details": {k: {a: {kk: vv for kk, vv in b.items() if kk != "tokens"} for a, b in v.items()} for k, v in details.items()}}


# ---- report ---------------------------------------------------------------------------------------
def _pc(v: float | None, ci: list[float] | None = None) -> str:
    if v is None:
        return "-"
    s = f"{v * 100:.1f}%"
    return s + (f" <small>[{ci[0] * 100:.0f}-{ci[1] * 100:.0f}]</small>" if ci and not np.isnan(ci).any() else "")


def render(root: Path, result: dict[str, Any]) -> str:
    doc, corpus = load(root)
    meta = json.loads((root / "matching" / "meta.json").read_text("utf-8"))
    pairs = {p["pair_id"]: p for p in doc["pairs"]}
    esc = html.escape
    rows = []
    for name, m in result["methods"].items():
        est, ci = m["estimated"], m["ci95"]
        bs = m["by_stratum"]
        rows.append(f"<tr><td>{esc(name)}</td><td>{_pc(est['precision'], ci['precision'])}</td><td>{_pc(est['recall'], ci['recall'])}</td>"
                    f"<td><b>{_pc(est['f1'], ci['f1'])}</b></td>"
                    + "".join(f"<td>{_pc(bs[s]['rate'])}</td>" for s in NEG_STRATA)
                    + f"<td>{_pc(m['positive_subsets']['cross_language']['recall'])}</td><td>{_pc(m['positive_subsets']['toll_differs']['recall'])}</td>"
                    f"<td>{_pc(m.get('order_inconsistent'))}</td><td>{_pc(m.get('uncertain_rate'))}</td><td>{m['pairs_missing']}</td></tr>")
    cl = [(n, m["cluster"]) for n, m in result["methods"].items() if "cluster" in m]
    crows = "".join(f"<tr><td>{esc(n)}</td><td>{_pc(c['pairwise_all']['precision'])}</td><td>{_pc(c['pairwise_all']['recall'])}</td><td>{_pc(c['pairwise_all']['f1'])}</td>"
                    f"<td>{_pc(c['bcubed']['f1'])}</td><td>{c['ari']:.3f}</td><td>{c['clusters']}/{c['true_groups']}</td><td>{c['groups_recovered_exactly']}</td>"
                    f"<td>{c['predicted_clusters_merging_groups']}</td><td>{c['true_groups_split']}</td></tr>" for n, c in cl)
    sus = []
    for pid in result["suspects"][:60]:
        p = pairs[pid]
        sus.append(f"<tr><td>{esc(p['label'])} ({esc(p['stratum'])})</td><td>{esc(str(corpus.meta[p['a']]['title']))}<br><small>{esc(str(corpus.meta[p['a']]['publisher']))} · <a href='{esc(str(corpus.meta[p['a']]['url']))}'>link</a></small></td>"
                   f"<td>{esc(str(corpus.meta[p['b']]['title']))}<br><small>{esc(str(corpus.meta[p['b']]['publisher']))} · <a href='{esc(str(corpus.meta[p['b']]['url']))}'>link</a></small></td>"
                   f"<td>{esc(str(result['details'].get('pair-full', {}).get(pid, {}).get('rationale', '')))}</td></tr>")
    pop = result["population"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Same-accident grouping benchmark</title><style>
body{{font:13px/1.45 ui-monospace,Menlo,Consolas,monospace;margin:24px;max-width:1500px;background:#f7f9fb;color:#16202e}}
table{{border-collapse:collapse;width:100%;margin:.5em 0 1.2em;background:#fff}}th,td{{border:1px solid #cfd8e3;padding:4px 7px;text-align:left;vertical-align:top}}
th{{background:#e9eff6}}.note{{border-left:4px solid #d58a12;background:#fff9ec;padding:8px 12px;margin:10px 0}}small{{color:#66758a}}a{{color:#0369a1}}</style></head><body>
<h1>Same-accident grouping benchmark</h1><p>Generated {result['generated_utc']} UTC · model: deepseek-flash · pair set sha256 <code>{meta['pairs_sha256'][:16]}…</code></p>
<div class="note"><b>Read this first.</b> The reference groups were assembled by a browser agent and then <b>checked by people</b>. Every number is
<b>agreement with those groups</b>. Pairs where all LLM methods contradict a group label are listed at the bottom as
<b>possible gold errors</b> for a human to review; they are still counted as mistakes in the tables. Prompts, the pair set and the decision rule were frozen before any
model call: {esc(meta['decision_rule'])}</div>
<h2>Design</h2><p>{result['pairs']} sampled pairs ({meta['positive_pairs']} positive, {meta['negative_pairs']} negative) out of {sum(pop.values())} possible.
Population by stratum: {', '.join(f'{k} {v}' for k, v in pop.items())}. Negatives are sampled, so precision, recall and F1 are <b>re-weighted to the full population</b>
(each sampled negative stands for population/sample pairs of its stratum); brackets are 95% intervals from resampling whole incident groups ({RESAMPLES} resamples).
Human records for the fields methods came from: {esc(json.dumps(meta['human_record_from']))}; model fields from {esc(meta['extraction_run_used_for_model_fields'])}.</p>
<h2>Headline: pair methods and clustering on the shared sampled pair set</h2>
<table><thead><tr><th>Method</th><th>Precision (est.)</th><th>Recall</th><th>F1 (est.)</th><th>Pairs called SAME: decoy-vs-main</th><th>same country ±4 d</th><th>TF-IDF neighbours</th><th>random</th>
<th>Recall: cross-language</th><th>Recall: toll differs</th><th>Order-inconsistent</th><th>Uncertain</th><th>Missing</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p><small>Columns 5-8 are the share of sampled negatives wrongly called SAME (lower is better) in each stratum. tf-idf uses a threshold tuned on this same sample (optimistic). fields rule: same country, dates within 1 day, location word overlap &ge; 0.3 on the model fields.</small></p>
<h2>Clustering on all {meta.get('population', {}) and sum(pop.values())} pairs of the corpus</h2>
<table><thead><tr><th>Run</th><th>Pair precision</th><th>Pair recall</th><th>Pair F1</th><th>B-cubed F1</th><th>ARI</th><th>Clusters/true groups</th><th>Groups recovered exactly</th><th>Clusters merging groups</th><th>Groups split</th></tr></thead><tbody>{crows}</tbody></table>
<h2>Possible gold errors ({len(result['suspects'])}) for human review</h2>
<table><thead><tr><th>Group label</th><th>Article A</th><th>Article B</th><th>Judge rationale (pair-full)</th></tr></thead><tbody>{''.join(sus)}</tbody></table>
</body></html>"""
