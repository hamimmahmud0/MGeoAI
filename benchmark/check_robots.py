"""Check robots.txt permission for every candidate URL (no article pages are fetched)."""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

UA = "MGeoAI-benchmark/0.1 (academic research; polite, low-rate)"


def main(pattern: str, out: str) -> None:
    urls: dict[str, list[str]] = defaultdict(list)
    for path in sorted(glob.glob(pattern)):
        for group in json.load(open(path))["groups"]:
            for article in group["articles"]:
                parts = urlsplit(article["url"])
                urls[f"{parts.scheme}://{parts.netloc}"].append(article["url"])
    result: dict[str, dict[str, object]] = {}
    with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": UA}) as client:
        for origin, items in sorted(urls.items()):
            row: dict[str, object] = {"urls": len(items)}
            try:
                response = client.get(f"{origin}/robots.txt")
                row["robots_status"] = response.status_code
                if response.status_code == 200 and "<html" not in response.text[:200].lower():
                    parser = RobotFileParser()
                    parser.parse(response.text.splitlines())
                    allowed = [u for u in items if parser.can_fetch(UA, u)]
                    row["allowed"] = allowed
                    row["blocked"] = [u for u in items if u not in allowed]
                    row["crawl_delay"] = parser.crawl_delay(UA)
                elif response.status_code >= 500:
                    # RFC 9309: an unreachable robots.txt (server error) means disallow.
                    row["allowed"], row["blocked"] = [], items
                else:
                    # 4xx / non-robots body: no restrictions published; still rate-limited.
                    row["allowed"] = items
                    row["blocked"] = []
            except httpx.HTTPError as exc:
                row["robots_status"] = f"error:{type(exc).__name__}"
                row["allowed"], row["blocked"] = [], items
            result[origin] = row
    json.dump(result, open(out, "w"), indent=2)
    total = sum(len(r["allowed"]) for r in result.values())  # type: ignore[arg-type]
    blocked = sum(len(r["blocked"]) for r in result.values())  # type: ignore[arg-type]
    print(f"origins={len(result)} allowed={total} blocked_or_unreachable={blocked}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
