"""Self-contained HTML report: model output vs each annotator vs each other.

Agreement is not accuracy: until three annotators label an article there is no gold, so
every number here compares two sources with each other. Field metrics use only articles
where both sides report exactly one accident (same rule as scoring.py).
"""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from traffic_fusion.extraction.annotation_store import ArticleStore
from traffic_fusion.extraction.scoring import FIELDS, _ci, norm

Record = dict[str, Any]


def _load_models(root: Path) -> dict[str, dict[str, Record]]:
    models: dict[str, dict[str, Record]] = {}
    runs = root / "runs"
    for folder in sorted(runs.iterdir()) if runs.is_dir() else []:
        if folder.name.startswith("_") or not (folder / "run.json").exists():
            continue
        models[folder.name] = {
            p.stem: json.loads(p.read_text("utf-8"))
            for p in folder.glob("*.json") if p.name != "run.json"
        }
    return models


def _first(accidents: list[Record]) -> Record | None:
    hits = [a for a in accidents if a.get("accident")]
    return hits[0] if len(hits) == 1 else None


def _source_view(accidents: list[Record] | None) -> tuple[bool | None, int | None, Record | None]:
    """(accident flag, accident count, the single accident record if exactly one)."""
    if accidents is None:
        return None, None, None
    hits = [a for a in accidents if a.get("accident")]
    return bool(hits), len(hits), _first(accidents)


def _match(field: str, left: Record, right: Record) -> bool | None:
    a, b = norm(field, left.get(field)), norm(field, right.get(field))
    if field == "location":
        sa, sb = set(a or ()), set(b or ())
        return None if not sa and not sb else (len(sa & sb) / len(sa | sb) >= 0.5 if sa and sb else False)
    return bool(a == b)


def compare(pairs: list[tuple[str, list[Record], list[Record]]]) -> dict[str, Any]:
    """Agreement statistics for two sources over the articles both have."""
    flag, count = [], []
    fields: dict[str, list[float]] = {f: [] for f in FIELDS}
    diffs: list[float] = []
    date_gap = {"left_missing": 0, "right_missing": 0, "both_differ": 0}
    for _article, left, right in pairs:
        lf, lc, lr = _source_view(left)
        rf, rc, rr = _source_view(right)
        flag.append(float(lf == rf))
        if lf and rf:
            count.append(float(lc == rc))
        if lr and rr:
            for f in FIELDS:
                verdict = _match(f, lr, rr)
                if verdict is not None:
                    fields[f].append(float(verdict))
            ld, rd = norm("date", lr.get("date")), norm("date", rr.get("date"))
            if ld != rd:
                date_gap["left_missing" if ld is None else "right_missing" if rd is None else "both_differ"] += 1
            if lr.get("fatalities") is not None and rr.get("fatalities") is not None:
                diffs.append(float(lr["fatalities"]) - float(rr["fatalities"]))

    def rate(values: list[float]) -> dict[str, Any]:
        return {"n": len(values), "value": sum(values) / len(values) if values else None, "ci95": _ci(values)}

    return {
        "date_gap": date_gap, "articles": len(pairs), "accident_flag": rate(flag), "accident_count": rate(count),
        "fields": {f: rate(v) for f, v in fields.items()},
        "fatalities": {
            "n": len(diffs), "mean_diff_left_minus_right": sum(diffs) / len(diffs) if diffs else None,
            "mae": sum(abs(d) for d in diffs) / len(diffs) if diffs else None,
            "exact": sum(d == 0 for d in diffs), "within_1": sum(abs(d) <= 1 for d in diffs),
        },
    }


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, list):
        return ", ".join(map(str, value)) or "—"
    return str(value)


def _pct(entry: dict[str, Any]) -> str:
    if entry["value"] is None:
        return "—"
    ci = f" [{entry['ci95'][0] * 100:.0f}–{entry['ci95'][1] * 100:.0f}]" if entry["ci95"] else ""
    return f"{entry['value'] * 100:.1f}%{ci} <small>n={entry['n']}</small>"


def build_report(root: Path, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    store = ArticleStore(root)
    labels = store.all_latest()
    models = _load_models(root)
    humans = {u: {a: [x.wire() for x in rec.accidents] if not rec.unusable else []
                  for a, rec in recs.items()} for u, recs in labels.items()}
    sources: dict[str, dict[str, list[Record]]] = {
        **{u: d for u, d in humans.items()},
        **{f"model:{c}": {a: r.get("accidents", []) for a, r in res.items() if r.get("status") == "ok"}
           for c, res in models.items()},
    }
    names = list(sources)
    esc = html.escape
    out: list[str] = []

    def table(head: list[str], rows: list[list[str]]) -> str:
        return ("<table><thead><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr></thead><tbody>"
                + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
                + "</tbody></table>")

    # coverage
    total = len(store.article_ids())
    cov = [[esc(n), str(len(sources[n])),
            f"{100 * len(sources[n]) / total:.0f}%" if total else "—"] for n in names]
    # pairwise
    pair_blocks, summary_rows = [], []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = sorted(set(sources[a]) & set(sources[b]))
            if not shared:
                continue
            result = compare([(x, sources[a][x], sources[b][x]) for x in shared])
            fat = result["fatalities"]
            summary_rows.append([esc(a), esc(b), str(result["articles"]), _pct(result["accident_flag"]),
                                 _pct(result["accident_count"]), _pct(result["fields"]["fatalities"]),
                                 _pct(result["fields"]["date"]), _pct(result["fields"]["country"]),
                                 _pct(result["fields"]["location"]), _pct(result["fields"]["vehicles"])])
            gap = result["date_gap"]
            gap_note = (f"<p>Dates that differ at day level: {esc(a)} has none in {gap['left_missing']}, "
                        f"{esc(b)} has none in {gap['right_missing']}, both give different days in {gap['both_differ']}.</p>")
            pair_blocks.append(
                f"<h3>{esc(a)} vs {esc(b)} <small>({result['articles']} shared articles)</small></h3>" + gap_note
                + table(["Field", "Exact agreement [95% CI]"],
                        [[esc(f), _pct(r)] for f, r in result["fields"].items()])
                + f"<p>Fatalities (left − right): n={fat['n']}, exact {fat['exact']}, within ±1 {fat['within_1']}, "
                  f"mean difference {fat['mean_diff_left_minus_right']:+.2f}, MAE {fat['mae']:.2f}.</p>"
                if fat["n"] else
                f"<h3>{esc(a)} vs {esc(b)}</h3>" + table(["Field", "Exact agreement [95% CI]"],
                                                         [[esc(f), _pct(r)] for f, r in result["fields"].items()]))
    # per-article rows
    article_rows = []
    for aid in sorted({a for d in sources.values() for a in d}):
        meta = store.meta(aid)
        cells = []
        base: Record | None = None
        for n in names:
            acc = sources[n].get(aid)
            if acc is None:
                cells.append("<td class='na'>not labelled</td>")
                continue
            flag, cnt, single = _source_view(acc)
            if single is None:
                body = f"accident: {'yes' if flag else 'no'} ({cnt} record{'s' if cnt != 1 else ''})"
            else:
                body = "<br>".join(f"<b>{lbl}</b> {esc(_fmt(single.get(f)))}" for lbl, f in [
                    ("killed", "fatalities"), ("k+inj", "casualities"), ("veh", "vehicles"),
                    ("date", "date"), ("country", "country"), ("place", "location")])
            cells.append(f"<td>{body}</td>")
            base = base or single
        agree = len({json.dumps({f: norm(f, (_source_view(sources[n].get(aid))[2] or {}).get(f)) for f in FIELDS}, default=str)
                     for n in names if aid in sources[n]}) == 1
        article_rows.append(
            f"<tr class='{'agree' if agree else 'differ'}'><td><a href='{esc(str(meta.get('url')))}' target='_blank' rel='noreferrer noopener'>"
            f"{esc(str(meta.get('title')))}</a><br><small>{esc(str(meta.get('publisher')))} · {aid}</small></td>{''.join(cells)}</tr>")
    head = "".join(f"<th>{esc(n)}</th>" for n in names)
    run_info = []
    for c in models:
        state = json.loads((root / "runs" / c / "run.json").read_text("utf-8"))
        ok = sum(1 for r in models[c].values() if r.get("status") == "ok")
        failed = sum(1 for r in models[c].values() if r.get("status") == "failed")
        tokens_in = sum(r.get("input_tokens") or 0 for r in models[c].values())
        tokens_out = sum(r.get("output_tokens") or 0 for r in models[c].values())
        quotes = sum(r.get("quality", {}).get("quotes", 0) for r in models[c].values())
        verb = sum(r.get("quality", {}).get("verbatim", 0) for r in models[c].values())
        run_info.append([esc(c), str(ok), str(failed), f"{tokens_in:,} / {tokens_out:,}",
                         f"{verb}/{quotes}", esc(json.dumps(state.get("spec", {})))])
    out.append(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Model vs annotators report</title><style>
body{{font:13px/1.45 ui-monospace,Menlo,Consolas,monospace;margin:24px;max-width:1500px;color:#16202e;background:#f7f9fb}}
h1,h2,h3{{margin:1.2em 0 .4em}} table{{border-collapse:collapse;width:100%;margin:.5em 0 1.2em;background:#fff}}
th,td{{border:1px solid #cfd8e3;padding:4px 7px;text-align:left;vertical-align:top}} th{{background:#e9eff6}}
tr.differ{{background:#fff4f4}} tr.agree{{background:#f3fbf5}} .na{{color:#8795a6}} small{{color:#66758a}}
.note{{border-left:4px solid #d58a12;background:#fff9ec;padding:8px 12px;margin:10px 0}} a{{color:#0369a1}}
</style></head><body>
<h1>Model output vs annotators</h1>
<p>Generated {now:%Y-%m-%d %H:%M} UTC from {total} articles. Private research data: it names annotators and
quotes news text.</p>
<div class="note"><b>Read this first.</b> These numbers are <b>agreement between two sources</b>, not accuracy. Gold needs
a strict majority of at least 3 annotators per field; no article has that yet, so nobody is “right” here.
Field metrics only use articles where both sides report exactly one accident. Brackets are 95% bootstrap
intervals over articles (shown when n ≥ 5). Every human label so far says “accident”, so the accident-flag
row says little until someone marks an article as not an accident.</div>
<div class="note"><b>Two things that depress the numbers for reasons other than model skill.</b>
(1) <b>Dates:</b> almost every model-vs-human date mismatch is the model returning <i>no date</i> where the human wrote one.
The model sees the article markdown only; the page's publication date lives in the page metadata and was not part of
that input, while annotators see it in the article header. (2) <b>Vehicles and place names</b> are free-form: annotators
and the model pick different vocabulary entries or write <code>other:…</code> names, and spell places differently, so exact
set / word-overlap agreement is low even when both are reasonable.</div>
<h2>Who labelled what</h2>{table(["Source", "Articles", "Share of corpus"], cov)}
<h2>Model runs</h2>{table(["Run", "ok", "failed", "tokens in / out", "quotes verbatim", "spec"], run_info)}
<h2>Pairwise agreement summary</h2>
{table(["Left", "Right", "Shared articles", "Accident flag", "Accident count", "Fatalities", "Date (day)", "Country", "Location (token overlap ≥ 0.5)", "Vehicles"], summary_rows)}
<h2>Details per pair</h2>{''.join(pair_blocks)}
<h2>Every article ({len(article_rows)})</h2>
<p><label><input type="checkbox" id="only"> show only articles where the sources disagree</label>
 &nbsp; green = every labelling source agrees on all fields, red = at least one differs.</p>
<table id="rows"><thead><tr><th>Article</th>{head}</tr></thead><tbody>{''.join(article_rows)}</tbody></table>
<script>document.getElementById('only').addEventListener('change',function(e){{document.querySelectorAll('#rows tr.agree').forEach(function(r){{r.style.display=e.target.checked?'none':''}})}})</script>
</body></html>""")
    return "".join(out)
