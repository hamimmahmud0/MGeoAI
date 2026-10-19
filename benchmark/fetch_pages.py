"""Fetch robots-allowed candidate pages politely and store raw HTML (never executed)."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx

UA = "MGeoAI-benchmark/0.1 (academic research; polite, low-rate)"
MAX_BYTES = 5_000_000
MIN_DELAY = 3.0


def fetch_origin(origin: str, row: dict[str, object], out_dir: Path) -> list[dict[str, object]]:
    delay = max(float(row.get("crawl_delay") or 0), MIN_DELAY)
    records = []
    with httpx.Client(timeout=25, follow_redirects=True, headers={"User-Agent": UA}) as client:
        for url in row["allowed"]:  # type: ignore[attr-defined]
            record: dict[str, object] = {"url": url, "origin": origin}
            try:
                response = client.get(url)
                record["status"] = response.status_code
                record["final_url"] = str(response.url)
                body = response.content[:MAX_BYTES]
                record["bytes"] = len(body)
                if response.status_code == 200 and "html" in response.headers.get("content-type", ""):
                    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
                    (out_dir / f"{digest}.html").write_bytes(body)
                    record["file"] = f"{digest}.html"
                    record["sha256"] = hashlib.sha256(body).hexdigest()
            except httpx.HTTPError as exc:
                record["status"] = f"error:{type(exc).__name__}"
            record["fetched_at"] = datetime.now(UTC).isoformat(timespec="seconds")
            records.append(record)
            time.sleep(delay)
    return records


def main(robots_report: str, out_dir_name: str) -> None:
    report = json.load(open(robots_report))
    out_dir = Path(out_dir_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_origin, o, r, out_dir) for o, r in report.items()]
        rows = [rec for f in futures for rec in f.result()]
    with (out_dir / "manifest.jsonl").open("w") as handle:
        for rec in rows:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    ok = sum(1 for r in rows if r.get("file"))
    print(f"fetched={ok} failed={len(rows) - ok} of {len(rows)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
