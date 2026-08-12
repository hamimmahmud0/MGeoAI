#!/usr/bin/env python3
"""Fast resumable Bing RSS fallback for sparse Group B countries."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.robotparser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlsplit
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
FINAL = ROOT / "candidates.jsonl"
LEDGER = ROOT / "access_attempts.jsonl"
UA = "MGeoAI-CorpusResearch/0.2 (+https://github.com/hamimmahmud0/MGeoAI)"
TARGET = 15
COUNTRIES = {
    "UG": ("Uganda", ["en", "sw", "lg"], '"Uganda" school bus crash killed'),
    "TZ": ("Tanzania", ["sw", "en"], '"Tanzania" bus crash killed'),
    "ET": ("Ethiopia", ["am", "en", "om"], '"Ethiopia" wedding bus river crash killed'),
    "MA": ("Morocco", ["ar", "fr", "ber"], '"Morocco" bus crash killed'),
    "EG": ("Egypt", ["ar", "en"], '"Egypt" tourist bus crash killed'),
    "TN": ("Tunisia", ["ar", "fr"], '"Tunisia" bus crash killed'),
    "TR": ("Türkiye", ["tr"], '"Turkey" bus crash killed'),
    "JO": ("Jordan", ["ar", "en"], '"Jordan" bus crash killed'),
}
SUFFIXES = ("road accident", "traffic crash", "bus crash", "car collision", "motorcycle accident")
EXTRA_QUERIES = {
    "JO": (
        '"Jordan" deadly highway crash',
        '"Jordan" truck crash killed',
        '"Amman" road accident',
        '"Jordan" pedestrian killed vehicle',
        'حادث سير الأردن',
        'حادث مروري الأردن',
    ),
}
STOPWORDS = {
    "the", "and", "for", "with", "from", "after", "into", "near", "that", "this",
    "road", "traffic", "crash", "accident", "collision", "killed", "injured", "dead",
    "uganda", "tanzania", "ethiopia", "morocco", "egypt", "tunisia", "turkey", "türkiye", "jordan",
}


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def append_ledger(row: dict[str, object]) -> None:
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def direct_url(value: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.hostname and parsed.hostname.endswith("bing.com"):
        value = parse_qs(parsed.query).get("url", [""])[0]
        parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return value


def domain(value: str) -> str:
    return (urlsplit(value).hostname or "").casefold().removeprefix("www.")


def clean(value: str | None, limit: int) -> str:
    text = re.sub(r"\s+", " ", BeautifulSoup(value or "", "html.parser").get_text(" ")).strip()
    words = text.split()
    return " ".join(words[:limit]) + (" …" if len(words) > limit else "")


def iso_date(value: str | None) -> str | None:
    try:
        return parsedate_to_datetime(value).astimezone(UTC).isoformat() if value else None
    except (TypeError, ValueError, OverflowError):
        return None


def discover(client: httpx.Client, code: str, name: str, pair_query: str) -> list[dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    queries = (
        [f'"{name}" {suffix}' for suffix in SUFFIXES]
        + list(EXTRA_QUERIES.get(code, ()))
        + [pair_query]
    )
    for query in queries:
        endpoint = f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss&setlang=en"
        try:
            response = client.get(
                "https://www.bing.com/news/search",
                params={"q": query, "format": "rss", "setlang": "en"},
                timeout=20,
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
        except (httpx.HTTPError, ElementTree.ParseError) as exc:
            append_ledger({"recorded_at": timestamp(), "country_iso2": code, "stage": "bing_rss", "discovery_endpoint": endpoint, "outcome": "failed", "error_class": type(exc).__name__})
            continue
        append_ledger({"recorded_at": timestamp(), "country_iso2": code, "stage": "bing_rss", "discovery_endpoint": endpoint, "outcome": "accessible", "http_status": response.status_code})
        for item in root.findall(".//item"):
            url = direct_url(item.findtext("link") or "")
            if not url:
                continue
            host = domain(url)
            if not host or host in {"bing.com", "msn.com"} or host.endswith(".msn.com"):
                continue
            source = next((node for node in item if node.tag.endswith("}Source")), None)
            found.setdefault(
                url,
                {
                    "url": url,
                    "domain": host,
                    "publisher": clean(source.text if source is not None else host, 20) or host,
                    "title": clean(item.findtext("title"), 80),
                    "excerpt": clean(item.findtext("description") or item.findtext("title"), 36),
                    "published_at": iso_date(item.findtext("pubDate")),
                    "discovery_url": endpoint,
                    "pair_query": query == pair_query,
                },
            )
        time.sleep(0.25)
    return list(found.values())


def check_domain(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
        first = str(rows[0]["url"])
        parsed = urlsplit(first)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        allowed = False
        robots_result = "robots_unavailable"
        try:
            response = client.get(robots_url, timeout=8)
            if response.status_code in {404, 410}:
                allowed, robots_result = True, "robots_not_found"
            elif response.status_code == 200:
                parser = urllib.robotparser.RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(response.text[:512_000].splitlines())
                allowed = parser.can_fetch(UA, first)
                robots_result = "robots_allowed" if allowed else "robots_denied"
            else:
                robots_result = f"robots_http_{response.status_code}"
        except httpx.HTTPError as exc:
            robots_result = f"robots_error_{type(exc).__name__}"
        for row in rows:
            result = robots_result
            status = None
            resolved = None
            if allowed:
                try:
                    with client.stream("GET", str(row["url"]), timeout=10) as response:
                        status = response.status_code
                        resolved = str(response.url)
                        content_type = response.headers.get("content-type", "").casefold()
                        total = 0
                        for chunk in response.iter_bytes():
                            total += len(chunk)
                            if total >= 64_000:
                                break
                        if response.status_code < 400 and ("html" in content_type or not content_type):
                            result = "accessible_html"
                        elif response.status_code in {401, 403, 451}:
                            result = f"blocked_http_{response.status_code}"
                        elif response.status_code == 429:
                            result = "rate_limited"
                        else:
                            result = f"http_{response.status_code}"
                except httpx.HTTPError as exc:
                    result = f"fetch_error_{type(exc).__name__}"
            row["direct_access"] = result
            row["http_status"] = status
            row["resolved_url"] = resolved
            append_ledger({"recorded_at": timestamp(), "country_iso2": row["country_iso2"], "stage": "publisher_access", "url": row["url"], "outcome": result, "http_status": status, "resolved_url": resolved})
    return rows


def tokens(title: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", title.casefold()) if len(word) >= 4 and word not in STOPWORDS}


def best_pair(rows: list[dict[str, object]]) -> tuple[dict[str, object], dict[str, object], float, list[str]] | None:
    options = []
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            if left["domain"] == right["domain"]:
                continue
            shared = sorted(tokens(str(left["title"])) & tokens(str(right["title"])))
            union = tokens(str(left["title"])) | tokens(str(right["title"]))
            score = len(shared) / len(union) if union else 0
            pair_bonus = 0.15 if left.get("pair_query") and right.get("pair_query") else 0
            if len(shared) >= 2 and score + pair_bonus >= 0.24:
                options.append((score + pair_bonus, shared, left, right))
    if not options:
        return None
    score, shared, left, right = max(options, key=lambda item: item[0])
    return left, right, round(min(0.95, 0.58 + score / 2), 3), shared


def compile_country(code: str, name: str, languages: list[str], raw: list[dict[str, object]]) -> list[dict[str, object]]:
    # Direct HTML is preferred. RSS metadata is the fallback when robots prevent a page check;
    # explicit HTTP blocks and rate limits are never promoted.
    strict = [row for row in raw if row.get("direct_access") == "accessible_html"]
    fallback = [
        row for row in raw
        if str(row.get("direct_access", "")).startswith(("robots_", "fetch_error_"))
        and row not in strict
    ]
    ranked = strict + fallback
    selected: list[dict[str, object]] = []
    per_domain: dict[str, int] = defaultdict(int)
    pair_rows = [row for row in ranked if row.get("pair_query")]
    pair = best_pair(pair_rows) or best_pair(ranked)
    required_pair_ids = {id(pair[0]), id(pair[1])} if pair else set()
    for row in ranked:
        if per_domain[str(row["domain"])] >= 2 and id(row) not in required_pair_ids:
            continue
        selected.append(row)
        per_domain[str(row["domain"])] += 1
        if len(selected) >= 20:
            break
    if pair:
        for member in pair[:2]:
            if member not in selected:
                selected.append(member)
    incident_key = None
    confidence = None
    reason = None
    paired_urls: set[str] = set()
    if pair:
        left, right, confidence, shared = pair
        paired_urls = {str(left["url"]), str(right["url"])}
        incident_key = f"gb-pair-{code.lower()}-{hashlib.sha256('|'.join(sorted(paired_urls)).encode()).hexdigest()[:12]}"
        reason = "Distinct publisher domains, close discovery context, and shared event terms (" + ", ".join(shared) + "). Human confirmation of event identity and upstream independence required."
    discovered_at = timestamp()
    compiled = []
    for row in selected:
        paired = str(row["url"]) in paired_urls
        direct_status = str(row.get("direct_access"))
        access_status = "accessible_html" if direct_status == "accessible_html" else "rss_metadata_accessible"
        compiled.append(
            {
                "country_iso2": code,
                "canonical_url": row["url"],
                "title": row["title"],
                "publisher": row["publisher"],
                "domain": row["domain"],
                "excerpt": row["excerpt"],
                "languages": languages,
                "published_at": row["published_at"],
                "discovered_at": discovered_at,
                "discovered_via": "bing_news_rss",
                "discovery_url": row["discovery_url"],
                "access_status": access_status,
                "incident_key": incident_key if paired else None,
                "pair_confidence": confidence if paired else None,
                "pair_reason": reason if paired else None,
            }
        )
    return compiled


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", action="append")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    requested = set(args.country or COUNTRIES)
    existing = read_jsonl(FINAL)
    by_country: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in existing:
        by_country[str(row["country_iso2"])].append(row)
    with httpx.Client(headers={"User-Agent": UA}) as client:
        for code, (name, languages, pair_query) in COUNTRIES.items():
            if code not in requested or (len(by_country[code]) >= TARGET and not args.force):
                continue
            raw = discover(client, code, name, pair_query)
            for row in raw:
                row["country_iso2"] = code
            grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
            for row in raw[:60]:
                grouped[str(row["domain"])].append(row)
            checked: list[dict[str, object]] = []
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(check_domain, rows) for rows in grouped.values()]
                for future in as_completed(futures):
                    checked.extend(future.result())
            compiled = compile_country(code, name, languages, checked)
            by_country[code] = compiled
            checkpoint = ROOT / "countries" / f"{code}.fast.candidates.jsonl"
            write_jsonl(checkpoint, compiled)
            merged = [row for country_rows in by_country.values() for row in country_rows]
            write_jsonl(FINAL, merged)
            print(f"{code}: {len(compiled)} candidates, {len({x['domain'] for x in compiled})} domains, pair={bool(best_pair(checked))}", flush=True)


if __name__ == "__main__":
    main()
