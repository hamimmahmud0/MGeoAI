"""One command that reproduces the whole same-accident grouping benchmark.

    mgeoai x group-benchmark --root <extraction dir> --yes

Steps: check annotation coverage -> verify or build the frozen pair set -> run every method
(resumable, failed calls get one more pass) -> score -> write report.html, results.json,
public_summary.json and run_manifest.json. See docs/GROUPING_BENCHMARK.md.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from traffic_fusion.extraction import grouping
from traffic_fusion.extraction.grouping_eval import evaluate, render

METHODS = ("pair-full", "pair-fields-both", "pair-fields-human", "pair-fields-model", "cluster-cards", "cluster-full")
# Measured in the pilot of 2026-11-09 (tokens per call): used only for the cost projection.
PER_CALL = {"pair-full": (1943, 393), "pair-fields-both": (763, 235), "pair-fields-human": (584, 233),
            "pair-fields-model": (582, 255)}
PER_CLUSTER_RUN = {"cluster-cards": (82351, 17000), "cluster-full": (168757, 21000)}
PRICE_IN, PRICE_OUT = (0.15, 0.30), (0.60, 1.20)  # USD per million tokens (DeepSeek flash, off-peak / peak)


def annotation_coverage(root: Path) -> tuple[int, int]:
    ids = {p.name for p in (root / "articles").iterdir() if (p / "meta.json").exists()}
    seen: set[str] = set()
    for path in (root / "labels").glob("*.jsonl"):
        for line in path.read_text("utf-8").splitlines():
            if line.strip():
                seen.add(json.loads(line)["article_id"])
    return len(ids & seen), len(ids)


def projection(n_pairs: int, methods: tuple[str, ...], repeats: int) -> dict[str, Any]:
    tin = tout = 0
    for m in methods:
        if m in PER_CALL:
            tin += 2 * n_pairs * PER_CALL[m][0]
            tout += 2 * n_pairs * PER_CALL[m][1]
        else:
            tin += repeats * PER_CLUSTER_RUN[m][0]
            tout += repeats * PER_CLUSTER_RUN[m][1]
    low = tin / 1e6 * PRICE_IN[0] + tout / 1e6 * PRICE_OUT[0]
    high = tin / 1e6 * PRICE_IN[1] + tout / 1e6 * PRICE_OUT[1]
    return {"tokens_in": tin, "tokens_out": tout, "usd_low": round(low, 2), "usd_high": round(high, 2)}


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def public_summary(result: dict[str, Any], meta: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """Aggregates only: no article ids, titles, links, group ids, pair ids or raw model replies."""
    methods = []
    for name, m in result["methods"].items():
        row: dict[str, Any] = {
            "method": name, "precision": m["estimated"]["precision"], "recall": m["estimated"]["recall"], "f1": m["estimated"]["f1"],
            "ci95": m["ci95"], "false_same_rate": {s: m["by_stratum"][s]["rate"] for s in grouping_strata()},
            "recall_cross_language": m["positive_subsets"]["cross_language"]["recall"],
            "recall_toll_differs": m["positive_subsets"]["toll_differs"]["recall"],
            "order_inconsistent": m.get("order_inconsistent"), "uncertain_rate": m.get("uncertain_rate"),
            "pairs_missing": m["pairs_missing"],
        }
        if "cluster" in m:
            c = m["cluster"]
            row["cluster"] = {"pair_f1_all": c["pairwise_all"]["f1"], "bcubed_f1": c["bcubed"]["f1"], "ari": c["ari"],
                              "clusters": c["clusters"], "true_groups": c["true_groups"],
                              "groups_recovered_exactly": c["groups_recovered_exactly"],
                              "clusters_merging_groups": c["predicted_clusters_merging_groups"], "groups_split": c["true_groups_split"]}
        methods.append(row)
    return {
        "generated_utc": result["generated_utc"], "title": "Same-accident grouping benchmark",
        "reading_note": "The reference groups were assembled by a browser agent and are not human-verified. All numbers are agreement with "
                        "those groups, not accuracy. Prompts, the pair set and the decision rule were frozen before any model call.",
        "design": {"articles": None, "sampled_pairs": result["pairs"],
                   "positive_pairs": meta["positive_pairs"], "negative_pairs": meta["negative_pairs"], "population_by_stratum": meta["population"],
                   "pairs_sha256": meta["pairs_sha256"], "decision_rule": meta["decision_rule"],
                   "human_records_from": meta.get("human_record_from")},
        "model": manifest["model"], "tokens": manifest.get("tokens"), "methods": methods,
        "limitations": [
            "The reference groups come from an LLM browser agent, which also chose the hard negatives; LLM errors and the labels may be correlated.",
            "LLM methods are within each other's confidence intervals, so the benchmark does not rank them.",
            "Negatives are sampled; precision, recall and F1 are re-weighted to the full pair population and bootstrapped over incident groups.",
            "tf-idf uses a threshold tuned on this same sample (optimistic).",
            "Hard negatives that are roundup articles mentioning several crashes are ambiguous and may be counted wrongly.",
        ],
        "reproduce": "mgeoai x group-benchmark --root <extraction dir> --yes   (docs/GROUPING_BENCHMARK.md)",
    }


def grouping_strata() -> tuple[str, ...]:
    return ("hard_decoy", "hard_near", "hard_similar", "easy")


def run_benchmark(root: Path, methods: tuple[str, ...] = METHODS, refresh_pairs: bool = False, concurrency: int = 25,
                  repeats: int = 3, token_limit: int = 8_000_000, skip_annotation_check: bool = False,
                  log: Any = print) -> dict[str, Any]:
    started = datetime.now(UTC)
    done, total = annotation_coverage(root)
    log(f"annotation coverage: {done}/{total} articles have at least one label")
    if done < total and not skip_annotation_check:
        raise RuntimeError(f"{total - done} articles have no annotation; finish annotating or pass --skip-annotation-check")
    matching = root / "matching"
    pairs_file, sha_file = matching / "pairs.json", matching / "pairs.sha256"
    if pairs_file.exists() and not refresh_pairs:
        actual = hashlib.sha256(pairs_file.read_bytes()).hexdigest()
        if sha_file.read_text("utf-8").strip() != actual:
            raise RuntimeError("matching/pairs.json no longer matches pairs.sha256: the frozen pair set was modified")
        log(f"frozen pair set verified ({actual[:12]}…)")
    else:
        log("building the pair set (this freezes it)")
        grouping.prepare(root)
    n_pairs = len(json.loads(pairs_file.read_text("utf-8"))["pairs"])
    proj = projection(n_pairs, methods, repeats)
    log(f"projected: {proj['tokens_in']:,} tokens in, {proj['tokens_out']:,} out, about ${proj['usd_low']} to ${proj['usd_high']}")
    usage: dict[str, Any] = {}
    for m in methods:
        for attempt in (1, 2):  # the second pass only redoes failed calls
            if m.startswith("pair-"):
                variant = m.split("-", 2)[2] if m.startswith("pair-fields-") else "both"
                out = grouping.run_pair_jobs(root, "pair-full" if m == "pair-full" else "pair-fields", None, concurrency,
                                             token_limit, variant=variant)
            else:
                out = grouping.run_cluster_jobs(root, m.split("-", 1)[1], repeats, token_limit)
            log(f"{m} pass {attempt}: {json.dumps(out)}")
            usage[m] = out
            if out.get("failed", 0) == 0 and out.get("ok", repeats) >= out.get("runs", out.get("ok", 0)):
                break
    result = evaluate(root)
    meta = json.loads((matching / "meta.json").read_text("utf-8"))
    manifest = {
        "started_utc": started.isoformat(timespec="seconds"), "finished_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(), "python": sys.version.split()[0], "numpy": np.__version__, "platform": platform.platform(),
        "model": {"provider": "deepseek", "model": "deepseek-flash", "temperature": 0, "thinking": "default",
                  "max_output_tokens_pair": 16000, "max_output_tokens_cluster": 32000},
        "seeds": {"pairs": grouping.SEED, "cluster_orders": [grouping.SEED + k for k in range(repeats)]},
        "prompt_sha256": {"pair": hashlib.sha256(grouping.SYSTEM_PAIR.encode()).hexdigest()[:12],
                          "pair_fields": hashlib.sha256(grouping.SYSTEM_PAIR_FIELDS.encode()).hexdigest()[:12],
                          "cluster": hashlib.sha256(grouping.SYSTEM_CLUSTER.encode()).hexdigest()[:12]},
        "pairs_sha256": meta["pairs_sha256"], "label_lines": meta.get("label_lines"), "methods": list(methods),
        "tokens": {k: {"in": v.get("tokens_in"), "out": v.get("tokens_out")} for k, v in usage.items()},
        "note": "LLM output is not bit-for-bit repeatable even at temperature 0; per-call replies are stored in matching/<method>/ as the record.",
    }
    (matching / "run_manifest.json").write_text(json.dumps(manifest, indent=1, default=float) + "\n", "utf-8")
    (matching / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=float) + "\n", "utf-8")
    (matching / "report.html").write_text(render(root, result), "utf-8")
    summary = public_summary(result, meta, manifest)
    summary["design"]["articles"] = total
    (matching / "public_summary.json").write_text(json.dumps(summary, indent=1, default=float) + "\n", "utf-8")
    log("wrote report.html, results.json, public_summary.json, run_manifest.json")
    return {"projection": proj, "manifest": manifest, "summary": summary}
