"""Every number in the paper that is not already in `mgeoai x reproduce` output, from the public dataset.

Usage: python writeups/paper_numbers.py <dataset slug or local folder> <reproduced-dir> <out.json>
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from traffic_fusion.extraction.agreement import cohen_kappa
from traffic_fusion.extraction.reproduce import fetch
from traffic_fusion.extraction.scoring import FIELDS, norm

RUNS = {"deepseek": "deepseek__deepseek-flash__markdown__txt", "deepseek_date": "deepseek__deepseek-flash__markdown__txt__meta",
        "qwen": "custom__qwen3-8-27b__markdown__img__meta", "lfm": "custom__lfm3-1-7b__markdown__txt__meta",
        "deepseek_off": "deepseek__deepseek-flash__markdown__txt__meta__nothink", "lfm_think": "custom__lfm3-1-7b__markdown__txt__meta__think"}
BASE = ("deepseek", "deepseek_date", "qwen")  # the runs compared on one shared article set
SHORT = {"fatalities": "fatalities", "casualities": "casualties", "vehicles": "vehicles", "date": "date", "country": "country", "location": "location"}


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def acc(record: dict[str, Any]) -> dict[str, Any]:
    return {f: norm(f, record.get(f)) for f in FIELDS}


def boot(values_by_group: dict[str, list[float]], seed: int = 3, n: int = 2000) -> list[float]:
    """95 % interval of the mean, resampling whole incident groups."""
    rng, keys = random.Random(seed), list(values_by_group)
    means = []
    for _ in range(n):
        picked = [v for k in rng.choices(keys, k=len(keys)) for v in values_by_group[k]]
        means.append(sum(picked) / len(picked))
    means.sort()
    return [round(means[int(0.025 * n)], 4), round(means[int(0.975 * n)], 4)]


def main(source: str, reproduced: Path, out: Path) -> None:
    ds = fetch(source, out.parent / ".dl") / "data"
    articles = {a["article_id"]: a for a in rows(ds / "articles.jsonl")}
    ann = rows(ds / "annotations.jsonl")
    ext = rows(ds / "model_extractions.jsonl")
    by_art: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in ann:
        by_art[r["article_id"]].append(r)
    for rs in by_art.values():
        rs.sort(key=lambda r: r["annotator"])  # annotator_1 labelled most: it is the reference
    ref = {a: rs[0] for a, rs in by_art.items()}
    single = {a: acc([x for x in r["accidents"] if x["accident"]][0]) for a, r in ref.items()
              if not r["unusable"] and sum(1 for x in r["accidents"] if x["accident"]) == 1}
    model: dict[str, dict[str, dict[str, Any]]] = {k: {} for k in RUNS}
    for e in ext:
        for key, run in RUNS.items():
            if e["run_id"] == run and e["status"] == "ok":
                hits = [x for x in e["accidents"] if x["accident"]]
                model[key][e["article_id"]] = {"n": len(hits), "rec": acc(hits[0]) if len(hits) == 1 else None}
    res: dict[str, Any] = {}

    # ---- the data -------------------------------------------------------------------------
    n_acc = Counter(sum(1 for x in r["accidents"] if x["accident"]) for r in ref.values())
    groups = Counter(a["reference_group_id"] for a in articles.values())
    real = {g for g, a in ((a["reference_group_id"], a) for a in articles.values()) if a["reference_group_kind"] == "same_incident"}
    res["data"] = {
        "articles": len(articles), "languages": Counter(a["language"] for a in articles.values()),
        "regions": Counter(a["region"] for a in articles.values()), "publishers": len({a["publisher"] for a in articles.values()}),
        "groups": len(groups), "articles_per_group_mean": round(len(articles) / len(groups), 2), "group_size_counts": dict(sorted(Counter(groups.values()).items())),
        "real_incident_groups": len(real), "decoy_groups": len(groups) - len(real),
        "annotators": len({r["annotator"] for r in ann}), "annotation_rows": len(ann), "articles_with_2plus": sum(len(v) >= 2 for v in by_art.values()),
        "reference_accident_counts": dict(sorted(n_acc.items())), "reference_unusable": sum(r["unusable"] for r in ref.values()),
        "reference_single_accident": len(single), "reference_with_coordinates": sum(1 for r in ref.values() for x in r["accidents"] if x.get("coordinates")),
        "articles_with_images": sum(1 for a in articles.values() if a["images_saved"]), "images_total": sum(a["images_saved"] for a in articles.values()),
    }

    # ---- extraction: every annotated article whose reference has one accident and where the run returned one accident ----
    common = sorted(a for a in single if all(a in model[k] and model[k][a]["rec"] for k in BASE))  # shared set, for paired differences only
    res["common_articles"] = len(common)
    own = {k: sorted(a for a in single if a in model[k] and model[k][a]["rec"]) for k in RUNS}
    active = [k for k in RUNS if own[k]]
    per: dict[str, Any] = {}
    for key in active:
        arts = own[key]
        entry: dict[str, Any] = {"n": len(arts)}
        for f in FIELDS:
            by_group: dict[str, list[float]] = defaultdict(list)
            for a in arts:
                by_group[articles[a]["reference_group_id"]].append(float(model[key][a]["rec"][f] == single[a][f]))
            vals = [v for vs in by_group.values() for v in vs]
            entry[SHORT[f]] = {"value": round(sum(vals) / len(vals), 4), "ci95": boot(by_group)}
        fat = [abs(model[key][a]["rec"]["fatalities"] - single[a]["fatalities"]) for a in arts
               if None not in (model[key][a]["rec"]["fatalities"], single[a]["fatalities"])]
        entry["fatalities_mae"] = round(sum(fat) / len(fat), 3)
        jac, ov = [], []
        for a in arts:
            w, g = set(single[a]["vehicles"] or ()), set(model[key][a]["rec"]["vehicles"] or ())
            jac.append(len(w & g) / len(w | g) if w | g else 1.0)
            w, g = set(single[a]["location"] or ()), set(model[key][a]["rec"]["location"] or ())
            ov.append(len(w & g) / len(w | g) if w | g else 1.0)
        entry["vehicles_jaccard"] = round(sum(jac) / len(jac), 4)
        entry["location_word_overlap"] = round(sum(ov) / len(ov), 4)
        per[key] = entry
    res["extraction"] = per

    # paired differences (Qwen minus DeepSeek+date), resampling incident groups
    pairs: dict[str, Any] = {}
    for a_key, b_key in (("qwen", "deepseek_date"), ("deepseek_date", "deepseek")):
        for f in FIELDS:
            by_group = defaultdict(list)
            for a in common:
                by_group[articles[a]["reference_group_id"]].append(float(model[a_key][a]["rec"][f] == single[a][f]) - float(model[b_key][a]["rec"][f] == single[a][f]))
            vals = [v for vs in by_group.values() for v in vs]
            pairs[f"{a_key}-{b_key}:{SHORT[f]}"] = {"diff": round(sum(vals) / len(vals), 4), "ci95": boot(by_group)}
    for a_key, b_key in (("deepseek_off", "deepseek_date"),):
        shared = sorted(a for a in own.get(a_key, []) if a in own["deepseek_date"])
        for f in FIELDS:
            by_group = defaultdict(list)
            for a in shared:
                by_group[articles[a]["reference_group_id"]].append(float(model[a_key][a]["rec"][f] == single[a][f]) - float(model[b_key][a]["rec"][f] == single[a][f]))
            vals = [v for vs in by_group.values() for v in vs]
            if vals:
                pairs[f"{a_key}-{b_key}:{SHORT[f]}"] = {"diff": round(sum(vals) / len(vals), 4), "ci95": boot(by_group), "articles": len(shared)}
    shared_lfm = sorted(a for a in own["lfm"] if a in own["deepseek_date"]) if own.get("lfm") else []
    for f in FIELDS:
        if shared_lfm:
            by_group = defaultdict(list)
            for a in shared_lfm:
                by_group[articles[a]["reference_group_id"]].append(float(model["lfm"][a]["rec"][f] == single[a][f]) - float(model["deepseek_date"][a]["rec"][f] == single[a][f]))
            vals = [v for vs in by_group.values() for v in vs]
            pairs[f"lfm-deepseek_date:{SHORT[f]}"] = {"diff": round(sum(vals) / len(vals), 4), "ci95": boot(by_group), "articles": len(shared_lfm)}
    res["paired_differences"] = pairs

    # ---- chance-corrected agreement (Cohen's kappa) of each run with the reference ----
    def kappa_of(left: dict[str, Any], right: dict[str, Any]) -> float | None:
        value, _ = cohen_kappa({k: str(v) for k, v in left.items()}, {k: str(v) for k, v in right.items()})
        return None if value is None else round(value, 3)

    kap: dict[str, Any] = {}
    for f in ("fatalities", "casualities", "country"):
        kap[SHORT[f]] = {k: kappa_of({a: single[a][f] for a in own[k]}, {a: model[k][a]["rec"][f] for a in own[k]}) for k in active}
    types = [v for v in ("bus", "truck", "microbus", "car", "cng_autorickshaw") if sum(1 for a in single if v in (single[a]["vehicles"] or ())) >= 5]
    per_type = {v: {k: kappa_of({a: v in (single[a]["vehicles"] or ()) for a in own[k]}, {a: v in (model[k][a]["rec"]["vehicles"] or ()) for a in own[k]}) for k in active} for v in types}
    kap["vehicle_types"] = per_type
    kap["vehicle_types_mean"] = {k: round(sum(t[k] for t in per_type.values() if t[k] is not None) / len(per_type), 3) for k in active}
    res["kappa"] = kap

    # ---- by region and language (runs that received the publish time) ----
    split: dict[str, Any] = {}
    for label in ("region", "language"):
        for value in sorted({a[label] for a in articles.values()}):
            split[f"{label}={value}"] = {}
            for k in ("deepseek_date", "qwen"):
                ids = [a for a in own[k] if articles[a][label] == value]
                split[f"{label}={value}"][k] = {"articles": len(ids), **{SHORT[f]: round(sum(model[k][a]["rec"][f] == single[a][f] for a in ids) / len(ids), 3)
                                                                         for f in ("fatalities", "casualities", "vehicles", "date", "country")}}
    res["extraction_by_subset"] = split

    # ---- accident flag and failures ----------------------------------------------------------
    flags: dict[str, Any] = {}
    for key, run in RUNS.items():
        runrows = [e for e in ext if e["run_id"] == run]
        ok = [e for e in runrows if e["status"] == "ok"]
        if not ok:
            continue
        flags[key] = {"articles": len(runrows), "ok": len(ok), "failed": len(runrows) - len(ok),
                      "failure_kinds": dict(Counter(e["error_kind"] for e in runrows if e["status"] != "ok")),
                      "flagged_accident": sum(1 for e in ok if any(x["accident"] for x in e["accidents"])),
                      "multi_accident": sum(1 for e in ok if sum(1 for x in e["accidents"] if x["accident"]) > 1),
                      "median_latency_s": round(sorted((e["latency_ms"] or 0) for e in ok)[len(ok) // 2] / 1000, 1),
                      "input_tokens": sum(e["input_tokens"] or 0 for e in ok), "output_tokens": sum(e["output_tokens"] or 0 for e in ok),
                      "quotes": sum((e["quote_check"] or {}).get("quotes", 0) for e in ok), "verbatim": sum((e["quote_check"] or {}).get("verbatim", 0) for e in ok)}
    res["runs"] = flags
    ref_multi = [a for a, r in ref.items() if sum(1 for x in r["accidents"] if x["accident"]) > 1]
    res["accident_count_agreement"] = {k: {"articles": len([a for a in ref if a in model[k]]),
                                           "same_count": sum(1 for a in ref if a in model[k] and model[k][a]["n"] == sum(1 for x in ref[a]["accidents"] if x["accident"]))} for k in active}
    res["reference_multi_accident_articles"] = len(ref_multi)

    # ---- images --------------------------------------------------------------------------------
    qwen_img = {i["image_id"]: i for e in ext if e["run_id"] == RUNS["qwen"] and e["status"] == "ok" for i in e["images"]}
    human_img = {i["image_id"]: i for r in ref.values() for i in r["images"] if i["shows_accident"] is not None}
    both = sorted(set(qwen_img) & set(human_img))
    agree = sum(1 for i in both if bool(qwen_img[i]["shows_accident"]) == bool(human_img[i]["shows_accident"]))
    tp = sum(1 for i in both if qwen_img[i]["shows_accident"] and human_img[i]["shows_accident"])
    fp = sum(1 for i in both if qwen_img[i]["shows_accident"] and not human_img[i]["shows_accident"])
    fn = sum(1 for i in both if not qwen_img[i]["shows_accident"] and human_img[i]["shows_accident"])
    res["images"] = {"images_saved": res["data"]["images_total"], "articles_with_images": res["data"]["articles_with_images"],
                     "images_analysed_by_qwen": len(qwen_img), "images_labelled_by_reference_annotator": len(human_img), "compared": len(both),
                     "agree": agree, "agreement": round(agree / len(both), 4) if both else None, "tp": tp, "fp": fp, "fn": fn,
                     "human_says_accident": sum(1 for i in both if human_img[i]["shows_accident"])}
    reproduced_results = json.loads((reproduced / "grouping_results.json").read_text("utf-8"))
    res["grouping_population"] = reproduced_results["population"]
    out.write_text(json.dumps(res, indent=1, default=lambda o: dict(o) if isinstance(o, Counter) else str(o)) + "\n", "utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
