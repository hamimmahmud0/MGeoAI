"""Rebuild every report from the public dataset alone (no article text is needed).

`reproduce(source, output)` takes a Hugging Face dataset slug or a local export folder, rebuilds a working
data root from its files, and runs the same scoring code the website uses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from traffic_fusion.extraction.annotation_store import ArticleStore
from traffic_fusion.extraction.grouping_eval import evaluate, render
from traffic_fusion.extraction.public import vehicle_group
from traffic_fusion.extraction.report import build_report
from traffic_fusion.extraction.scoring import annotation_stats, build_reference, model_metrics

REDACTED = "redacted"


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", "utf-8")


def fetch(source: str, cache: Path) -> Path:
    """A local folder is used as is; anything else is treated as a Hugging Face dataset slug."""
    local = Path(source)
    if (local / "data").is_dir():
        return local
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(repo_id=source, repo_type="dataset", local_dir=str(cache)))


def _wire(accident: dict[str, Any]) -> dict[str, Any]:
    return {"accident": accident["accident"], "casualities": accident.get("casualities"), "fatalities": accident.get("fatalities"),
            "vehicles": accident.get("vehicles"), "date": accident.get("date"), "country": accident.get("country"),
            "location": accident.get("location"), "longitude and latitude": accident.get("coordinates"), "evidences": []}


def materialise(dataset: Path, root: Path) -> dict[str, Any]:
    """Write the folder layout the scoring code expects. Article text is absent, so only scores that do not need it are possible."""
    data = dataset / "data"
    meta: dict[str, Any] = json.loads((data / "grouping_meta.json").read_text("utf-8"))
    for a in _rows(data / "articles.jsonl"):
        _dump(root / "articles" / a["article_id"] / "meta.json", {
            "url": a["url"], "publisher": a["publisher"], "title": a["title"], "published_at": a["published_at"],
            "language": a["language"], "images": [],
            "admin": {"group_id": a["reference_group_id"], "country": a["collection_country"], "region": a["region"]}})
    by_user: dict[str, list[str]] = {}
    for r in _rows(data / "annotations.jsonl"):
        by_user.setdefault(r["annotator"], []).append(json.dumps({
            "article_id": r["article_id"], "annotator": r["annotator"], "accidents": [_wire(x) for x in r["accidents"]],
            "images": r["images"], "unusable": r["unusable"], "notes": "", "submitted_at": REDACTED, "revision": r["revision"]}))
    (root / "labels").mkdir(parents=True, exist_ok=True)
    for user, lines in by_user.items():
        (root / "labels" / f"{user}.jsonl").write_text("\n".join(lines) + "\n", "utf-8")
    _dump(root / "human_order.json", meta["human_order"])

    runs: dict[str, list[dict[str, Any]]] = {}
    for e in _rows(data / "model_extractions.jsonl"):
        runs.setdefault(e["run_id"], []).append(e)
    for run_id, rows in runs.items():
        first = rows[0]
        _dump(root / "runs" / run_id / "run.json", {
            "config_id": run_id, "status": "finished", "done": len(rows), "failed": 0, "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "cost_known": False,
            "spec": {"provider": first["provider"], "model": first["model"], "input_set": first["input_set"],
                     "with_images": first["with_images"], "with_meta": first["with_meta"]}})
        for e in rows:
            _dump(root / "runs" / run_id / f"{e['article_id']}.json", {
                "article_id": e["article_id"], "status": e["status"], "accidents": [_wire(x) for x in e["accidents"]],
                "quality": e.get("quote_check") or {}, "latency_ms": e.get("latency_ms"),
                "input_tokens": e.get("input_tokens"), "output_tokens": e.get("output_tokens")})

    matching = root / "matching"
    pairs = _rows(data / "grouping_pairs.jsonl")
    _dump(matching / "pairs.json", {"seed": meta["seed"], "decision_rule": meta["decision_rule"], "population": meta["population"],
                                    "total_articles": meta["total_articles"], "pairs": pairs})
    _dump(matching / "meta.json", {k: meta[k] for k in ("pairs_sha256", "positive_pairs", "negative_pairs", "decision_rule", "population",
                                                          "extraction_run_used_for_model_fields", "human_record_from")})
    for r in _rows(data / "grouping_pair_predictions.jsonl"):
        _dump(matching / r["method"] / f"{r['pair_id']}__{r['order']}.json", r)
    counters: dict[str, int] = {}
    for c in _rows(data / "grouping_clusters.jsonl"):
        k = counters[c["method"]] = counters.get(c["method"], 0) + 1
        _dump(matching / c["method"] / f"run{k}.json", {**c, "status": "ok"})
    return meta


def incidents_geojson(dataset: Path) -> dict[str, Any]:
    data = dataset / "data"
    articles = {a["article_id"]: a for a in _rows(data / "articles.jsonl")}
    features = []
    incidents = _rows(data / "incidents.jsonl")
    for inc in incidents:
        geo = inc.get("geo")
        if not geo:
            continue
        members = [{"id": a, "title": articles[a]["title"], "publisher": articles[a]["publisher"], "url": articles[a]["url"],
                    "published_at": articles[a]["published_at"], "language": articles[a]["language"]} for a in inc["article_ids"]]
        when = inc.get("when")
        features.append({
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [geo["longitude"], geo["latitude"]]},
            "properties": {
                "incident_id": inc["incident_id"], "headline": inc["headline"], "summary": inc["summary"], "when": when,
                "place": inc.get("place_query"), "killed": inc.get("killed"), "injured": inc.get("injured"),
                "vehicles": inc.get("vehicles"), "casualty_note": inc.get("casualty_note"),
                "disagreements": inc.get("source_disagreements"), "vehicle_main": vehicle_group(inc.get("vehicles")),
                "year": int(str(when)[:4]) if when and str(when)[:4].isdigit() else None, "n_articles": len(members),
                "articles": members, "granularity": geo["granularity"], "uncertainty_radius_km": geo["uncertainty_radius_km"],
                "verified": False,
                "location_method": "OpenStreetMap place centroid; not a crash coordinate (ODbL, (c) OpenStreetMap contributors)"}})
    return {"type": "FeatureCollection", "features": features,
            "meta": {"records": len(incidents), "mapped": len(features), "verified": False}}


def reproduce(source: str, output: Path, work: Path | None = None) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    work = work or output / ".work"
    dataset = fetch(source, work / "download")
    root = work / "root"
    materialise(dataset, root)
    store = ArticleStore(root)
    labels = store.all_latest()

    _dump(output / "annotation_scores.json", annotation_stats(store))
    reference = build_reference(labels)
    models = {p.name: model_metrics(p, reference, store, labels)
              for p in sorted((root / "runs").iterdir()) if (p / "run.json").exists()}
    _dump(output / "model_performance.json", models)
    result = evaluate(root)
    _dump(output / "grouping_results.json", result)
    (output / "grouping_report.html").write_text(render(root, result), "utf-8")
    (output / "model_vs_annotators.html").write_text(build_report(root), "utf-8")
    geo = incidents_geojson(dataset)
    _dump(output / "incidents.geojson", geo)

    expected = json.loads((dataset / "data" / "expected_results.json").read_text("utf-8"))["grouping"]
    drift: dict[str, Any] = {}
    for name, want in expected.items():
        got = result["methods"].get(name, {}).get("estimated")
        if got is None:
            drift[name] = "missing"
            continue
        diffs = {k: round(got[k] - v, 4) for k, v in want.items() if v is not None and got.get(k) is not None and abs(got[k] - v) > 1e-3}
        if diffs:
            drift[name] = diffs
    summary = {"dataset": source, "files": sorted(p.name for p in output.iterdir() if p.is_file()),
               "grouping_methods": len(result["methods"]), "incidents_mapped": geo["meta"]["mapped"],
               "matches_published_numbers": not drift, "differences": drift}
    _dump(output / "reproduction_summary.json", summary)
    return summary
