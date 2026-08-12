from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.robotparser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlsplit
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
RAW_CANDIDATES_PATH = ROOT / "raw_candidates.jsonl"
CANDIDATES_PATH = ROOT / "candidates.jsonl"
ACCESS_LEDGER_PATH = ROOT / "access_ledger.jsonl"
SUMMARY_PATH = ROOT / "summary.json"
USER_AGENT = "MGeoAI-CorpusResearch/0.1 (+noncommercial evidence research)"
COUNTRIES = {
    "BD": ("Bangladesh", "en"),
    "IN": ("India", "en"),
    "PK": ("Pakistan", "en"),
    "LK": ("Sri Lanka", "en"),
    "NP": ("Nepal", "en"),
    "ID": ("Indonesia", "en"),
    "MY": ("Malaysia", "en"),
    "SG": ("Singapore", "en"),
    "TH": ("Thailand", "en"),
    "PH": ("Philippines", "en"),
    "VN": ("Vietnam", "en"),
    "JP": ("Japan", "en"),
    "KR": ("South Korea", "en"),
    "AU": ("Australia", "en"),
    "NZ": ("New Zealand", "en"),
    "AE": ("United Arab Emirates", "en"),
    "SA": ("Saudi Arabia", "en"),
}
QUERY_SUFFIXES = (
    "road accident",
    "traffic crash",
    "bus crash",
    "car collision",
    "motorcycle accident",
)
COUNTRY_SEARCH_TERMS = {
    "LK": ("Sri Lanka", "Colombo", "Sri Lankan"),
    "KR": ("South Korea", "Korea", "Seoul"),
    "NZ": ("New Zealand", "Auckland", "Wellington"),
    "AE": ("United Arab Emirates", "UAE", "Dubai", "Abu Dhabi"),
}
ELIGIBLE_ACCESS_STATUSES = {
    "accessible",
    "accessible_html",
    "feed_metadata_match",
    "rss_metadata_accessible",
}
PAIR_OVERRIDES = {
    "IN": (
        "https://www.indiatoday.in/india/story/bus-falls-into-gorge-in-major-accident-on-jammu-srinagar-national-highway-2386215-2023-05-30",
        "https://see.news/india-at-least-10-killed-55-injured-as-bus-carrying-hindu-pilgrims-falls-into-gorge",
        "Both accessible reports describe the May 30, 2023 Katra-bound bus crash near "
        "Jhajjar Kotli with ten deaths and about 55 injuries. Human confirmation required.",
    ),
    "JP": (
        "https://mustsharenews.com/kindergarten-bus-crashes/amp/",
        "https://www.chibanippo.co.jp/articles/1504265",
        "Both accessible reports describe the September 29, 2025 kindergarten shuttle-bus "
        "crash into a Kamagaya residence that killed the driver. Human confirmation required.",
    ),
    "PK": (
        "https://www.dawn.com/news/1836392/28-dead-22-injured-as-quetta-bound-bus-falls-into-ravine-in-balochistans-washuk",
        "https://www.aljazeera.com/news/2024/5/29/at-least-28-killed-after-bus-falls-into-ravine-in-pakistans-balochistan",
        "Both accessible reports describe the May 29, 2024 Quetta-bound bus crash into a "
        "ravine in Washuk, Balochistan, with at least 28 deaths. Human confirmation required.",
    ),
    "VN": (
        "https://bdnews24.com/world/south-east-asia/4791c1bec105",
        "https://www.hindustantimes.com/world-news/vietnam-sleeper-bus-crash-dead-injured-hanoi-da-nang-101753473827987.html",
        "Both accessible reports describe the July 25, 2025 sleeper-bus crash in Ha Tinh, "
        "central Vietnam; the later report reflects an updated death toll. Human confirmation "
        "required.",
    ),
}
STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "after",
    "as",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "with",
    "road",
    "crash",
    "accident",
    "collision",
    "traffic",
}


def append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def publisher_url(value: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.hostname and parsed.hostname.endswith("bing.com"):
        target = parse_qs(parsed.query).get("url", [None])[0]
        if target:
            value = target
            parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return value


def domain_for(value: str) -> str:
    return (urlsplit(value).hostname or "").casefold().removeprefix("www.")


def text(value: str | None, limit: int = 500) -> str:
    normalized = re.sub(
        r"\s+", " ", BeautifulSoup(value or "", "html.parser").get_text(" ")
    ).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit + 1].rsplit(" ", 1)[0].rstrip() + "…"


def discover(client: httpx.Client, country_code: str, country_name: str) -> list[dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    namespace = "https://www.bing.com/news/search"
    searches = COUNTRY_SEARCH_TERMS.get(country_code, (country_name,))
    for search_name in searches:
        for suffix in QUERY_SUFFIXES:
            query = f'"{search_name}" {suffix}'
            endpoint = f"{namespace}?q={quote_plus(query)}&format=rss&setlang=en"
            try:
                response = client.get(
                    namespace,
                    params={"q": query, "format": "rss", "setlang": "en"},
                    timeout=20,
                )
                response.raise_for_status()
                root = ElementTree.fromstring(response.content)
            except (httpx.HTTPError, ElementTree.ParseError) as exc:
                append_jsonl(
                    ACCESS_LEDGER_PATH,
                    {
                        "at": datetime.now().astimezone().isoformat(),
                        "country_iso2": country_code,
                        "action": "discovery",
                        "endpoint": endpoint,
                        "result": "failed",
                        "detail": type(exc).__name__,
                    },
                )
                continue
            append_jsonl(
                ACCESS_LEDGER_PATH,
                {
                    "at": datetime.now().astimezone().isoformat(),
                    "country_iso2": country_code,
                    "action": "discovery",
                    "endpoint": endpoint,
                    "result": "accessible",
                    "http_status": response.status_code,
                },
            )
            for item in root.findall(".//item"):
                url = publisher_url(item.findtext("link") or "")
                if not url:
                    continue
                domain = domain_for(url)
                if not domain or domain in {"bing.com", "msn.com"}:
                    continue
                title = text(item.findtext("title"), 500)
                excerpt = text(item.findtext("description"), 600) or title
                source_node = next((node for node in item if node.tag.endswith("}Source")), None)
                publisher = (
                    text(source_node.text if source_node is not None else None, 200) or domain
                )
                found.setdefault(
                    url,
                    {
                        "candidate_id": "cand_" + hashlib.sha256(url.encode()).hexdigest()[:16],
                        "country_iso2": country_code,
                        "country_name": country_name,
                        "manual_verification_url": url,
                        "publisher": publisher,
                        "domain": domain,
                        "title": title,
                        "published_at": item.findtext("pubDate"),
                        "language": "en",
                        "short_excerpt": excerpt,
                        "excerpt_source": "bing_news_rss_description",
                        "discovered_via": "bing_news_rss",
                        "discovery_endpoint": endpoint,
                        "discovered_at": datetime.now().astimezone().isoformat(),
                    },
                )
            time.sleep(0.35)
    return list(found.values())


def robots_allowed(
    client: httpx.Client, url: str, cache: dict[str, tuple[bool, str]]
) -> tuple[bool, str]:
    parsed = urlsplit(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin in cache:
        return cache[origin]
    robots_url = origin + "/robots.txt"
    try:
        response = client.get(robots_url, timeout=12)
        if response.status_code in {404, 410}:
            decision = (True, "robots_not_found")
        elif response.status_code != 200:
            decision = (False, f"robots_http_{response.status_code}")
        else:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text[:512_000].splitlines())
            allowed = parser.can_fetch(USER_AGENT, url)
            decision = (allowed, "robots_allowed" if allowed else "robots_denied")
    except httpx.HTTPError as exc:
        decision = (False, f"robots_error_{type(exc).__name__}")
    cache[origin] = decision
    time.sleep(0.2)
    return decision


def verify(
    client: httpx.Client, row: dict[str, object], robots_cache: dict[str, tuple[bool, str]]
) -> None:
    url = str(row["manual_verification_url"])
    allowed, robots_result = robots_allowed(client, url, robots_cache)
    result = robots_result
    http_status: int | None = None
    resolved_url: str | None = None
    if allowed:
        try:
            with client.stream("GET", url, timeout=15, follow_redirects=True) as response:
                http_status = response.status_code
                resolved_url = str(response.url)
                content_type = response.headers.get("content-type", "").casefold()
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total >= 64_000:
                        break
                if response.status_code < 400 and (
                    "text/html" in content_type or "application/xhtml+xml" in content_type
                ):
                    result = "accessible_html"
                elif response.status_code < 400:
                    result = "accessible_non_html"
                else:
                    result = f"http_{response.status_code}"
        except httpx.HTTPError as exc:
            result = f"fetch_error_{type(exc).__name__}"
        time.sleep(0.2)
    row["access_result"] = result
    row["access_http_status"] = http_status
    row["resolved_url"] = resolved_url
    append_jsonl(
        ACCESS_LEDGER_PATH,
        {
            "at": datetime.now().astimezone().isoformat(),
            "country_iso2": row["country_iso2"],
            "candidate_id": row["candidate_id"],
            "action": "publisher_access_check",
            "url": url,
            "result": result,
            "http_status": http_status,
            "resolved_url": resolved_url,
        },
    )


def title_tokens(title: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", title.casefold())
        if len(token) > 2 and token not in STOPWORDS
    }


def parsed_date(value: object) -> datetime | None:
    try:
        return parsedate_to_datetime(str(value))
    except (TypeError, ValueError, OverflowError):
        return None


def iso_date(value: object) -> str | None:
    parsed = parsed_date(value)
    return parsed.isoformat() if parsed else None


def plausible_pairs(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    pairs: list[dict[str, object]] = []
    for index, left in enumerate(rows):
        left_tokens = title_tokens(str(left["title"]))
        if len(left_tokens) < 2:
            continue
        for right in rows[index + 1 :]:
            if left["domain"] == right["domain"]:
                continue
            right_tokens = title_tokens(str(right["title"]))
            union = left_tokens | right_tokens
            score = len(left_tokens & right_tokens) / len(union) if union else 0
            left_date, right_date = (
                parsed_date(left.get("published_at")),
                parsed_date(right.get("published_at")),
            )
            if (
                left_date
                and right_date
                and abs((left_date - right_date).total_seconds()) > 4 * 86400
            ):
                continue
            if score >= 0.24 and len(left_tokens & right_tokens) >= 3:
                pairs.append(
                    {
                        "left_candidate_id": left["candidate_id"],
                        "right_candidate_id": right["candidate_id"],
                        "left_domain": left["domain"],
                        "right_domain": right["domain"],
                        "title_token_jaccard": round(score, 3),
                        "shared_title_tokens": sorted(left_tokens & right_tokens),
                        "status": "plausible_requires_human_confirmation",
                    }
                )
    return sorted(pairs, key=lambda pair: float(pair["title_token_jaccard"]), reverse=True)


def compile_candidates(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_country: dict[str, list[dict[str, object]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        identity = (str(row["country_iso2"]), str(row["manual_verification_url"]))
        if identity in seen:
            continue
        seen.add(identity)
        by_country[identity[0]].append(row)

    compiled: list[dict[str, object]] = []
    for code in COUNTRIES:
        country_rows = by_country.get(code, [])
        eligible_rows = [
            row for row in country_rows if row.get("access_result") in ELIGIBLE_ACCESS_STATUSES
        ]
        pairs = plausible_pairs(eligible_rows)
        pair_by_id: dict[str, tuple[str, float, str]] = {}
        override = PAIR_OVERRIDES.get(code)
        override_rows = (
            [row for row in eligible_rows if row["manual_verification_url"] in override[:2]]
            if override
            else []
        )
        if override and len(override_rows) == 2:
            pair_ids = sorted(str(row["candidate_id"]) for row in override_rows)
            incident_key = (
                f"{code.lower()}_pair_"
                f"{hashlib.sha256('|'.join(pair_ids).encode()).hexdigest()[:12]}"
            )
            for candidate_id in pair_ids:
                pair_by_id[candidate_id] = (incident_key, 0.95, override[2])
        elif pairs:
            pair = pairs[0]
            pair_ids = sorted([str(pair["left_candidate_id"]), str(pair["right_candidate_id"])])
            incident_key = f"{code.lower()}_pair_{hashlib.sha256('|'.join(pair_ids).encode()).hexdigest()[:12]}"
            score = float(pair["title_token_jaccard"])
            confidence = round(min(0.95, 0.55 + score / 2), 3)
            reason = (
                "Distinct publisher domains; close publication dates; shared headline tokens: "
                + ", ".join(str(token) for token in pair["shared_title_tokens"])
                + ". Human confirmation required."
            )
            for candidate_id in pair_ids:
                pair_by_id[candidate_id] = (incident_key, confidence, reason)
        for row in country_rows:
            pair_data = pair_by_id.get(str(row["candidate_id"]))
            compiled.append(
                {
                    "country_iso2": code,
                    "canonical_url": row["manual_verification_url"],
                    "title": row["title"],
                    "publisher": row["publisher"],
                    "domain": row["domain"],
                    "excerpt": row["short_excerpt"],
                    "languages": [row.get("language", "en")],
                    "published_at": iso_date(row.get("published_at")),
                    "discovered_at": row.get("discovered_at")
                    or datetime.now().astimezone().isoformat(),
                    "discovered_via": row["discovered_via"],
                    "discovery_url": row["discovery_endpoint"],
                    "access_status": row.get("access_result", "not_checked"),
                    "incident_key": pair_data[0] if pair_data else None,
                    "pair_confidence": pair_data[1] if pair_data else None,
                    "pair_reason": pair_data[2] if pair_data else None,
                }
            )
    CANDIDATES_PATH.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in compiled),
        encoding="utf-8",
    )
    return compiled


def run() -> None:
    existing = load_jsonl(RAW_CANDIDATES_PATH)
    existing_urls: dict[str, set[str]] = defaultdict(set)
    for row in existing:
        existing_urls[str(row["country_iso2"])].add(str(row["manual_verification_url"]))
    completed = {code for code, urls in existing_urls.items() if len(urls) >= 12}
    all_rows = list(existing)
    robots_cache: dict[str, tuple[bool, str]] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for code, (name, _language) in COUNTRIES.items():
            if code in completed:
                continue
            discovered = discover(client, code, name)
            selected = discovered[:15]
            by_domain: dict[str, list[dict[str, object]]] = defaultdict(list)
            for row in selected:
                by_domain[str(row["domain"])].append(row)

            def verify_domain(rows: list[dict[str, object]]) -> list[dict[str, object]]:
                for candidate in rows:
                    verify(client, candidate, robots_cache)
                return rows

            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(verify_domain, rows) for rows in by_domain.values()]
                for future in as_completed(futures):
                    for row in future.result():
                        append_jsonl(RAW_CANDIDATES_PATH, row)
            all_rows.extend(selected)
    compiled_rows = compile_candidates(all_rows)
    by_country: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in compiled_rows:
        by_country[str(row["country_iso2"])].append(row)
    country_summary = {}
    blockers = []
    for code, (name, _language) in COUNTRIES.items():
        rows = by_country.get(code, [])
        paired = [row for row in rows if row.get("incident_key")]
        country_summary[code] = {
            "country_name": name,
            "candidate_count": len(rows),
            "distinct_domain_count": len({row["domain"] for row in rows}),
            "accessible_html_count": sum(
                row.get("access_status") == "accessible_html" for row in rows
            ),
            "plausible_same_incident_pair_count": len({row["incident_key"] for row in paired}),
        }
        if len(rows) < 12:
            blockers.append(f"{code}: only {len(rows)} unique candidates discovered (target 12)")
        if not paired:
            blockers.append(f"{code}: no cross-domain same-incident pair identified")
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "group": "C",
        "collection_method": (
            "Bing News RSS metadata, targeted web-search additions, and robots-aware "
            "direct publisher access checks"
        ),
        "candidate_file": str(CANDIDATES_PATH.relative_to(ROOT)),
        "access_ledger_file": str(ACCESS_LEDGER_PATH.relative_to(ROOT)),
        "candidate_count": len(compiled_rows),
        "countries": country_summary,
        "blockers": blockers,
        "limitations": [
            "Candidates are leads for human review and are not verified facts.",
            "RSS descriptions are retained as short discovery excerpts; article bodies are not stored.",
            "Same-incident pairs are lexical/date candidates and require human confirmation.",
            "Publisher-country assignment is not incident geolocation evidence.",
        ],
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    run()
