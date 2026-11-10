"""Error analysis for the paper, computed from the public dataset (no article text needed).

Usage: python writeups/error_analysis.py <dataset slug or local folder> <out.json>
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from traffic_fusion.extraction.reproduce import fetch
from traffic_fusion.extraction.scoring import FIELDS, norm

RUNS = {
    "deepseek_T": "deepseek__deepseek-flash__markdown__txt",
    "deepseek_TP": "deepseek__deepseek-flash__markdown__txt__meta",
    "deepseek_TP_off": "deepseek__deepseek-flash__markdown__txt__meta__nothink",
    "qwen_TPI": "custom__qwen3-8-27b__markdown__img__meta",
    "lfm_TP": "custom__lfm3-1-7b__markdown__txt__meta",
    "lfm_TP_on": "custom__lfm3-1-7b__markdown__txt__meta__think",
}


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def day(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value)
    try:
        if text.isdigit() and len(text) >= 12:  # a Unix time in milliseconds, as scraped for a few pages
            return datetime.fromtimestamp(int(text) / 1000, tz=UTC).date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def main(source: str, out: Path) -> None:
    ds = fetch(source, out.parent / ".dl") / "data"
    articles = {a["article_id"]: a for a in rows(ds / "articles.jsonl")}
    ann = rows(ds / "annotations.jsonl")
    by_art: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in ann:
        by_art[r["article_id"]].append(r)
    ref = {a: sorted(rs, key=lambda r: r["annotator"])[0] for a, rs in by_art.items()}
    ref_acc = {a: [x for x in r["accidents"] if x["accident"]] for a, r in ref.items()}
    single = {a: x[0] for a, x in ref_acc.items() if len(x) == 1 and not ref[a]["unusable"]}
    ext = rows(ds / "model_extractions.jsonl")
    res: dict[str, Any] = {"reference_single_accident": len(single)}
    present = {k: [e for e in ext if e["run_id"] == run] for k, run in RUNS.items()}
    present = {k: v for k, v in present.items() if v}

    # ---- failures, by cause ----------------------------------------------------------------------
    res["failures"] = {k: {"articles": len(v), "ok": sum(e["status"] == "ok" for e in v),
                           "by_cause": dict(Counter(e["error_kind"] for e in v if e["status"] != "ok"))} for k, v in present.items()}

    model: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for k, v in present.items():
        model[k] = {e["article_id"]: [x for x in e["accidents"] if x["accident"]] for e in v if e["status"] == "ok"}

    # ---- scores with failures counted as misses (end to end) -------------------------------------------
    end: dict[str, Any] = {}
    for k in present:
        n_ok = 0
        hits: dict[str, int] = {f: 0 for f in FIELDS}
        for a, r in single.items():
            got = model[k].get(a)
            if got and len(got) == 1:
                n_ok += 1
                for f in FIELDS:
                    hits[f] += norm(f, got[0].get(f)) == norm(f, r.get(f))
        end[k] = {"reference_articles": len(single), "answered_with_one_accident": n_ok,
                  **{f: round(hits[f] / len(single), 4) for f in FIELDS if f != "location"}}
    res["end_to_end"] = end

    own = {k: [a for a in single if len(model[k].get(a, [])) == 1] for k in present}

    # ---- killed plus injured -------------------------------------------------------------------------
    cas: dict[str, Any] = {}
    for k in present:
        c: Counter[str] = Counter()
        for a in own[k]:
            r, m = single[a], model[k][a][0]
            if r["casualities"] == m["casualities"]:
                continue
            if m["casualities"] is None:
                c["model gave no total"] += 1
            elif r["casualities"] is None:
                c["reference gave no total"] += 1
            elif m["casualities"] == m["fatalities"] and r["casualities"] > (r["fatalities"] or 0):
                c["total equals the model's killed count (injured not added)"] += 1
            elif m["casualities"] > r["casualities"]:
                c["model total higher"] += 1
            else:
                c["model total lower"] += 1
        cas[k] = {"scored": len(own[k]), "errors": sum(c.values()), "by_type": dict(c)}
    res["killed_plus_injured_errors"] = cas
    res["reference_total_equals_killed"] = sum(1 for r in single.values() if r["casualities"] is not None and r["casualities"] == r["fatalities"])
    res["reference_total_missing"] = sum(1 for r in single.values() if r["casualities"] is None)

    # ---- date ---------------------------------------------------------------------------------------
    dat: dict[str, Any] = {}
    for k in present:
        c = Counter()
        for a in own[k]:
            want, got = day(single[a]["date"]), day(model[k][a][0]["date"])
            if want == got:
                continue
            pub = day(articles[a]["published_at"])
            if got is None:
                c["model gave no date"] += 1
            elif want is None:
                c["reference gave no date"] += 1
            elif pub is not None and got == pub:
                c["model returned the publication day"] += 1
            elif abs((got - want).days) == 1:
                c["off by one day"] += 1
            else:
                c["off by more than one day"] += 1
        dat[k] = {"scored": len(own[k]), "errors": sum(c.values()), "by_type": dict(c)}
    res["date_errors"] = dat

    # ---- vehicles -----------------------------------------------------------------------------------
    veh: dict[str, Any] = {}
    for k in present:
        missing: Counter[str] = Counter()
        extra: Counter[str] = Counter()
        kinds: Counter[str] = Counter()
        other_used = 0
        for a in own[k]:
            want, got = set(single[a]["vehicles"] or ()), set(model[k][a][0]["vehicles"] or ())
            other_used += any(v.startswith("other:") for v in got)
            if want == got:
                continue
            missing.update(want - got)
            extra.update(got - want)
            kinds["model list is a subset (vehicles left out)" if got < want else "model list is a superset (extra vehicles)" if got > want else "different vehicles"] += 1
        veh[k] = {"scored": len(own[k]), "errors": sum(kinds.values()), "by_type": dict(kinds), "most_often_missing": dict(missing.most_common(5)),
                  "most_often_extra": dict(extra.most_common(5)), "articles_using_other": other_used}
    res["vehicle_errors"] = veh

    # ---- fatalities misses and accident counts ---------------------------------------------------------
    miss: dict[str, Any] = {}
    for k in present:
        miss[k] = sorted(((single[a]["fatalities"], model[k][a][0]["fatalities"]) for a in own[k] if single[a]["fatalities"] != model[k][a][0]["fatalities"]), key=str)
    res["killed_misses_reference_vs_model"] = {k: [list(x) for x in v] for k, v in miss.items()}
    cnt: dict[str, Any] = {}
    for k in present:
        c = Counter()
        for a, r in ref_acc.items():
            if a not in model[k]:
                continue
            want, got = len(r), len(model[k][a])
            if want == got:
                continue
            c["model found more accidents" if got > want else "model found fewer accidents"] += 1
        cnt[k] = dict(c)
    res["accident_count_errors"] = cnt
    out.write_text(json.dumps(res, indent=1, default=str) + "\n", "utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
