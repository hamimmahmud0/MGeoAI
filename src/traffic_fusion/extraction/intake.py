"""Build `extraction/articles/<id>/` from the hand-collected benchmark pages.

Selection rule (verified against the drop log): `<id> copy.html` (a browser re-save of a
page whose HTTP fetch had no usable text) beats `<id>.html`. `id = sha256(url)[:16]`.
Group ids are admin-only and never sent to a model or served to annotators.
"""

from __future__ import annotations

import glob
import hashlib
import json
from pathlib import Path
from typing import Any

from traffic_fusion.extraction.prepare import (
    html_to_markdown,
    image_candidates,
    page_metadata,
    raw_for_model,
)
from traffic_fusion.utils import write_json


def article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _candidates(scraps_dir: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for path in sorted(glob.glob(str(scraps_dir / "candidates_b*.json"))):
        batch = json.loads(Path(path).read_text(encoding="utf-8"))
        for group in batch["groups"]:
            for art in group["articles"]:
                rows[art["url"]] = {
                    "candidate": art,
                    "group_id": group["group_id"],
                    "batch": batch.get("batch_id"),
                    "region": group.get("region"),
                    "country": group.get("country"),
                }
    return rows


def build_articles(pages_dir: Path, scraps_dir: Path, out_root: Path) -> dict[str, Any]:
    manifest = {
        row["url"]: row
        for row in (
            json.loads(line)
            for line in (pages_dir / "manifest.jsonl").read_text().splitlines()
            if line.strip()
        )
    }
    dropped = {
        row["url"]: row["reason"]
        for row in json.loads((pages_dir.parent / "dropped_articles.json").read_text())
    }
    report: dict[str, Any] = {"built": 0, "missing": [], "variants": {}}
    for url, info in _candidates(scraps_dir).items():
        aid = article_id(url)
        copy, plain = pages_dir / f"{aid} copy.html", pages_dir / f"{aid}.html"
        path = copy if copy.exists() else plain if plain.exists() else None
        if path is None:
            report["missing"].append({"url": url, "id": aid, "dropped": dropped.get(url)})
            continue
        raw = path.read_bytes()
        reason = dropped.get(url, "")
        if copy.exists():
            variant = "browser_resave"
        elif reason.startswith("fetch:not_allowed"):
            variant = "browser_recovery_robots_disallowed"
        elif reason.startswith("fetch:"):
            variant = "browser_recovery_after_http_error"
        else:
            variant = "http_fetch"
        report["variants"][variant] = report["variants"].get(variant, 0) + 1
        meta = page_metadata(raw)
        cand = info["candidate"]
        target = out_root / "articles" / aid
        target.mkdir(parents=True, exist_ok=True)
        (target / "raw.html").write_bytes(raw)
        (target / "model_raw.html").write_text(raw_for_model(raw), encoding="utf-8")
        markdown = html_to_markdown(raw)
        (target / "article.md").write_text(markdown, encoding="utf-8")
        write_json(
            target / "meta.json",
            {
                "id": aid,
                "url": url,
                "publisher": cand.get("publisher"),
                "title": meta["title"] or cand.get("title"),
                "published_at": meta["published_time"] or cand.get("published_date"),
                "language": cand.get("language") or meta["language"],
                "sha256": hashlib.sha256(raw).hexdigest(),
                "source_variant": variant,
                "source_file": path.name,
                "markdown_chars": len(markdown),
                "images": image_candidates(raw, url),
                # Admin-only: never served to annotators, never sent to a model.
                "admin": {
                    "group_id": info["group_id"],
                    "batch": info["batch"],
                    "region": info["region"],
                    "country": info["country"],
                    "agent_claim": cand.get("event_date_stated"),
                    "http_status": manifest.get(url, {}).get("status"),
                    "drop_reason": reason or None,
                },
            },
        )
        report["built"] += 1
    return report
