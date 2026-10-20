"""Polite download of article images so annotators and models see the same bytes.

Policy mirrors `benchmark/fetch_pages.py`: robots.txt per host (RFC 9309; a 5xx robots
file means disallow), identifying User-Agent, at least 3 s between requests to a host,
size cap, image content types only. No circumvention; a refusal is recorded, not retried.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

UA = "MGeoAI-extraction/0.1 (academic research; polite, low-rate)"
MAX_BYTES = 5_000_000
MIN_DELAY = 3.0
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}
MAX_PER_ARTICLE = 6


class RobotsCache:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self._parsers: dict[str, RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._parsers:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                response = self.client.get(f"{origin}/robots.txt")
                if response.status_code >= 500:
                    parser = None  # unreachable robots.txt: disallow
                elif response.status_code == 200 and "<html" not in response.text[:200].lower():
                    assert parser is not None
                    parser.parse(response.text.splitlines())
                else:
                    assert parser is not None
                    parser.parse([])
            except httpx.HTTPError:
                parser = None
            self._parsers[origin] = parser
        parser = self._parsers[origin]
        return bool(parser and parser.can_fetch(UA, url))


def fetch_article_images(root: Path, article_ids: list[str] | None = None) -> dict[str, int]:
    """Download candidate images listed in each article's meta.json. Safe to re-run."""
    counts = {"saved": 0, "skipped": 0, "robots": 0, "failed": 0}
    last_hit: dict[str, float] = {}
    with httpx.Client(timeout=25, follow_redirects=True, headers={"User-Agent": UA}) as client:
        robots = RobotsCache(client)
        base = root / "articles"
        for folder in sorted(base.iterdir() if base.is_dir() else []):
            if article_ids is not None and folder.name not in article_ids:
                continue
            meta_path = folder / "meta.json"
            if not meta_path.exists():
                continue
            meta: dict[str, Any] = json.loads(meta_path.read_text("utf-8"))
            images: list[dict[str, Any]] = meta.get("images", [])
            kept = 0
            for index, image in enumerate(images, start=1):
                if image.get("file") or image.get("status") in {"robots", "failed", "not_image"}:
                    kept += 1 if image.get("file") else 0
                    counts["skipped"] += 1
                    continue
                if kept >= MAX_PER_ARTICLE:
                    image["status"] = "over_limit"
                    continue
                url = image["url"]
                if not robots.allowed(url):
                    image["status"] = "robots"
                    counts["robots"] += 1
                    continue
                host = urlsplit(url).netloc
                wait = MIN_DELAY - (time.monotonic() - last_hit.get(host, 0))
                if wait > 0:
                    time.sleep(wait)
                try:
                    response = client.get(url)
                    last_hit[host] = time.monotonic()
                    kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    body = response.content[:MAX_BYTES + 1]
                    if response.status_code != 200 or kind not in EXT or len(body) > MAX_BYTES:
                        image["status"] = "not_image" if response.status_code == 200 else "failed"
                        image["http_status"] = response.status_code
                        counts["failed"] += 1
                        continue
                except httpx.HTTPError as exc:
                    image["status"] = "failed"
                    image["error"] = type(exc).__name__
                    counts["failed"] += 1
                    continue
                target = folder / "images"
                target.mkdir(exist_ok=True)
                name = f"{index}.{EXT[kind]}"
                (target / name).write_bytes(body)
                image.update(file=name, sha256=hashlib.sha256(body).hexdigest(), status="saved",
                             content_type=kind, bytes=len(body))
                counts["saved"] += 1
                kept += 1
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return counts
