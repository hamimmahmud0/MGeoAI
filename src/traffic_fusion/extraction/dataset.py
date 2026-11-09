"""Export the annotated road-accident news workspace as a public dataset.

What is shared: our own work (annotations, model extractions, grouping labels and predictions, fused
incident summaries, place lookups) plus article metadata (URL, publisher, title, date). What is NOT shared:
article text, HTML and images (they belong to the publishers), annotator account names (replaced by
annotator_1, annotator_2, ...), annotator free-text notes, timestamps, raw model replies, and the verbatim
quotes models copied from articles. Scores are recomputed from these files by `mgeoai x reproduce`.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from traffic_fusion.extraction.annotation_store import ArticleStore
from traffic_fusion.extraction.grouping import Corpus

DATA = "data"


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), "utf-8")


def _read(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _accident(record: dict[str, Any], keep_evidence_notes: bool = False) -> dict[str, Any]:
    out = {
        "accident": record["accident"], "fatalities": record.get("fatalities"), "casualities": record.get("casualities"),
        "vehicles": record.get("vehicles"), "date": record.get("date"), "country": record.get("country"),
        "location": record.get("location"), "coordinates": record.get("longitude and latitude"),
    }
    if keep_evidence_notes:  # the quotes themselves are article text and are dropped; only the field names stay
        out["evidence_fields"] = sorted({e.get("field") for e in record.get("evidences", []) if e.get("field")})
    return out


def _error_kind(message: str | None) -> str | None:
    if not message:
        return None
    low = message.lower()
    for key, kind in (("truncated", "truncated"), ("validation", "invalid_output"), ("json", "invalid_output"),
                      ("http", "http_error"), ("timeout", "timeout"), ("no accident", "empty_answer")):
        if key in low:
            return kind
    return "other"


def export_dataset(root: Path, out: Path, repo_id: str, candidates_glob: str = "benchmark/scraps/candidates_b0[1-5].json") -> dict[str, Any]:
    store = ArticleStore(root)
    labels = store.all_latest()
    order = sorted(labels, key=lambda u: (-len(labels[u]), u))
    alias = {user: f"annotator_{i + 1}" for i, user in enumerate(order)}
    corpus = Corpus(root, candidates_glob=candidates_glob)
    data = out / DATA
    data.mkdir(parents=True, exist_ok=True)

    articles = []
    for a in corpus.ids:
        m, kind = corpus.meta[a], corpus.groups_kind.get(corpus.group[a], {})
        articles.append({
            "article_id": a, "url": m.get("url"), "publisher": m.get("publisher"), "title": m.get("title"),
            "published_at": m.get("published_at"), "language": m.get("language"), "source_variant": m.get("source_variant"),
            "markdown_chars": m.get("markdown_chars"), "images_saved": sum(1 for i in m.get("images", []) if i.get("file")),
            "collection_country": m["admin"].get("country"), "region": m["admin"].get("region"),
            "reference_group_id": corpus.group[a], "reference_group_kind": kind.get("kind"),
            "decoy_for_group": kind.get("decoy_for")})
    _write_jsonl(data / "articles.jsonl", articles)

    annotations = []
    for user in order:
        for a, rec in sorted(labels[user].items()):
            annotations.append({
                "article_id": a, "annotator": alias[user], "revision": rec.revision, "unusable": rec.unusable,
                "accidents": [_accident(x.wire()) for x in rec.accidents],
                "images": [{"image_id": i.image_id, "description": i.description, "shows_accident": i.shows_accident,
                            "vehicles_visible": i.vehicles_visible} for i in rec.images]})
    _write_jsonl(data / "annotations.jsonl", annotations)

    extractions = []
    runs_dir = root / "runs"
    for folder in sorted(runs_dir.iterdir()) if runs_dir.is_dir() else []:
        if folder.name.startswith("_") or not (folder / "run.json").exists():
            continue
        spec = _read(folder / "run.json")["spec"]
        for path in sorted(folder.glob("*.json")):
            if path.name == "run.json":
                continue
            r = _read(path)
            settings = r.get("call_settings") or {}
            extractions.append({
                "run_id": folder.name, "provider": spec["provider"], "model": spec["model"], "input_set": spec["input_set"],
                "with_images": spec.get("with_images", False), "with_meta": spec.get("with_meta", False),
                "thinking": settings.get("thinking"), "max_output_tokens": settings.get("max_output_tokens"),
                "article_id": r["article_id"], "status": r["status"], "error_kind": _error_kind(r.get("error")),
                "accidents": [_accident(x, keep_evidence_notes=True) for x in r.get("accidents", [])],
                "images": r.get("images", []), "images_sent": len(r.get("images_sent") or []),
                "quote_check": r.get("quality"), "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
                "latency_ms": r.get("latency_ms"), "finish_reason": r.get("finish_reason")})
    _write_jsonl(data / "model_extractions.jsonl", extractions)

    matching = root / "matching"
    pairs_doc = _read(matching / "pairs.json")
    _write_jsonl(data / "grouping_pairs.jsonl", pairs_doc["pairs"])
    predictions, clusters = [], []
    for folder in sorted(p for p in matching.iterdir() if p.is_dir()) if matching.is_dir() else []:
        if folder.name.startswith("pair-"):
            for path in sorted(folder.glob("*__*.json")):
                r = _read(path)
                predictions.append({
                    "method": folder.name, "pair_id": r["pair_id"], "order": r["order"], "status": r["status"],
                    "decision": r.get("decision"), "confidence": r.get("confidence"), "rationale": r.get("rationale"),
                    "quote_check": r.get("quote_check"), "input_tokens": r.get("input_tokens"),
                    "output_tokens": r.get("output_tokens"), "finish_reason": r.get("finish_reason")})
        elif folder.name.startswith("cluster-"):
            for path in sorted(folder.glob("run*.json")):
                r = _read(path)
                if r["status"] == "ok":
                    clusters.append({"method": folder.name, "run": r["run"], "clusters": r["clusters"], "validity": r.get("validity"),
                                     "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens")})
    _write_jsonl(data / "grouping_pair_predictions.jsonl", predictions)
    embedding_file = matching / "embedding_baseline.json"
    if embedding_file.exists():
        emb = _read(embedding_file)
        _write_jsonl(data / "grouping_embedding_baseline.jsonl", [
            {"pair_id": pid, "model": name, "repo": entry["repo"], "cosine": value}
            for name, entry in emb["models"].items() for pid, value in sorted(entry["cosine"].items())])
    _write_jsonl(data / "grouping_clusters.jsonl", clusters)
    meta, manifest = _read(matching / "meta.json"), _read(matching / "run_manifest.json")
    human_from = {alias.get(u, u): n for u, n in (meta.get("human_record_from") or {}).items()}
    grouping_meta = {
        "seed": pairs_doc["seed"], "decision_rule": pairs_doc["decision_rule"], "population": pairs_doc["population"],
        "total_articles": pairs_doc["total_articles"], "pairs_sha256": meta["pairs_sha256"],
        "positive_pairs": meta["positive_pairs"], "negative_pairs": meta["negative_pairs"],
        "extraction_run_used_for_model_fields": meta["extraction_run_used_for_model_fields"],
        "human_record_from": human_from, "human_order": [alias[u] for u in corpus.human_order if u in alias], "model": manifest["model"], "seeds": manifest["seeds"],
        "prompt_sha256": manifest["prompt_sha256"], "tokens": manifest["tokens"], "extra_models": _extra_models(matching)}
    (data / "grouping_meta.json").write_text(json.dumps(grouping_meta, indent=1) + "\n", "utf-8")

    incidents = []
    incidents_file = matching / "incidents.json"
    if incidents_file.exists():
        doc = _read(incidents_file)
        for inc in doc["incidents"]:
            f = inc["fusion"]
            incidents.append({
                "incident_id": inc["incident_id"], "article_ids": inc["articles"], "headline": f["headline"], "summary": f["summary"],
                "when": f.get("when"), "place_query": f.get("place_query"), "country": f.get("country"), "killed": f.get("killed"),
                "injured": f.get("injured"), "casualty_note": f.get("casualty_note"), "vehicles": f.get("vehicles"),
                "source_disagreements": f.get("source_disagreements"), "geo": inc.get("geo"),
                "fused_by": doc.get("model"), "grouping": doc.get("source"), "prompt_hash": doc.get("prompt_hash")})
    _write_jsonl(data / "incidents.jsonl", incidents)

    results = _read(matching / "results.json")
    expected = {"grouping": {n: {"precision": m["estimated"]["precision"], "recall": m["estimated"]["recall"], "f1": m["estimated"]["f1"]}
                             for n, m in results["methods"].items()},
                "note": "Headline numbers at export time; `mgeoai x reproduce` recomputes them from the files in data/ and compares."}
    (data / "expected_results.json").write_text(json.dumps(expected, indent=1) + "\n", "utf-8")

    summary = {"repo_id": repo_id, "exported_utc": datetime.now(UTC).isoformat(timespec="seconds"), "articles": len(articles),
               "annotations": len(annotations), "annotators": len(alias), "model_extractions": len(extractions),
               "runs": sorted({e["run_id"] for e in extractions}), "pairs": len(pairs_doc["pairs"]), "pair_predictions": len(predictions),
               "cluster_runs": len(clusters), "incidents": len(incidents), "languages": sorted({a["language"] for a in articles if a["language"]}),
               "publishers": len({a["publisher"] for a in articles})}
    card = Path(__file__).resolve().parents[3] / "docs" / "DATASET_CARD.md"
    if card.exists():
        (out / "README.md").write_text(card.read_text("utf-8"), "utf-8")
    leak = _scan_for_leaks(out, list(alias))
    if leak:
        raise RuntimeError(f"export refused: {leak}")
    return summary


def _extra_models(matching: Path) -> dict[str, Any]:
    """Models other than the default that also answered same-accident questions (folders `<method>@<model>`)."""
    found: dict[str, Any] = {}
    for folder in sorted(p for p in matching.iterdir() if p.is_dir() and "@" in p.name):
        tag = folder.name[folder.name.index("@") + 1:]
        files = [_read(f) for f in folder.glob("*.json")]
        settings: dict[str, Any] = next((f["call_settings"] for f in files if f.get("call_settings")), {})
        entry = found.setdefault(tag, {"provider": settings.get("provider"), "model": settings.get("model"), "methods": {}})
        entry["methods"][folder.name.split("@")[0]] = {
            "calls": len(files), "ok": sum(1 for f in files if f.get("status") == "ok"),
            "tokens_in": sum(f.get("input_tokens") or 0 for f in files), "tokens_out": sum(f.get("output_tokens") or 0 for f in files)}
    return found


def _scan_for_leaks(out: Path, usernames: list[str]) -> str | None:
    """Fail the export if a real account name, a raw reply or an article body slipped into the files."""
    patterns = [re.compile(rf"\b{re.escape(u)}\b", re.I) for u in usernames]
    for path in sorted((out / DATA).glob("*")):
        text = path.read_text("utf-8")
        if any(p.search(text) for p in patterns):
            return f"a real account name appears in {path.name}"
        if '"raw_text":' in text or '"markdown":' in text or '"quote":' in text:
            return f"raw model text or article text appears in {path.name}"
    return None
