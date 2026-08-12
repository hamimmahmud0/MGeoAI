#!/usr/bin/env python3
"""Resumable, metadata-only discovery for MGeoAI global corpus group B.

The collector uses Google News RSS only as a discovery index, resolves result links
to direct publisher URLs, observes publisher robots rules, and records short excerpts
from accessible publisher pages. It deliberately does not accept sources into the
corpus or claim that publisher-domain diversity proves editorial independence.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup
from googlenewsdecoder import new_decoderv1

ROOT = Path(__file__).resolve().parent
TARGET = 15
MAX_ACCEPTED = 20
USER_AGENT = "MGeoAIResearchCollector/0.2 (+https://github.com/hamimmahmud0/MGeoAI)"
DISCOVERY_BASE = "https://news.google.com/rss/search"


@dataclass(frozen=True)
class Country:
    alpha2: str
    alpha3: str
    name: str
    languages: tuple[str, ...]
    timezone: str
    locale: str
    query: str
    pair_query: str


COUNTRIES = (
    Country("NL", "NLD", "Netherlands", ("nl", "en"), "Europe/Amsterdam", "nl-NL", '(verkeersongeluk OR dodelijk ongeval OR botsing) Nederland', 'dodelijk verkeersongeluk Nederland'),
    Country("BE", "BEL", "Belgium", ("nl", "fr", "de", "en"), "Europe/Brussels", "nl-BE", '(verkeersongeluk OR dodelijk ongeval OR accident de la route) België OR Belgique', 'trein minibus ongeval België doden'),
    Country("SE", "SWE", "Sweden", ("sv", "en"), "Europe/Stockholm", "sv-SE", '(trafikolycka OR bilolycka OR krasch) Sverige död OR skadad', 'buss krasch Stockholm hållplats döda'),
    Country("NO", "NOR", "Norway", ("nb", "nn", "en"), "Europe/Oslo", "no-NO", '(trafikkulykke OR bilulykke OR kollisjon) Norge omkom OR skadet', 'trafikkulykke Norge to omkom'),
    Country("PL", "POL", "Poland", ("pl",), "Europe/Warsaw", "pl-PL", '(wypadek drogowy OR zderzenie OR wypadek samochodowy) Polska zginął OR ranni', 'wypadek drogowy Polska zginęli'),
    Country("ZA", "ZAF", "South Africa", ("en", "zu", "xh", "af"), "Africa/Johannesburg", "en-ZA", '(road crash OR traffic accident OR collision) South Africa killed OR injured', 'bus crash South Africa killed'),
    Country("NG", "NGA", "Nigeria", ("en", "ha", "ig", "yo"), "Africa/Lagos", "en-NG", '(road crash OR traffic accident OR collision) Nigeria killed OR injured', 'Kano athletes bus crash killed'),
    Country("KE", "KEN", "Kenya", ("en", "sw"), "Africa/Nairobi", "en-KE", '(road crash OR traffic accident OR collision) Kenya killed OR injured', 'Kenya bus crash killed injured'),
    Country("GH", "GHA", "Ghana", ("en", "ak"), "Africa/Accra", "en-GH", '(road crash OR traffic accident OR collision) Ghana killed OR injured', 'East Legon crash Ghana killed'),
    Country("UG", "UGA", "Uganda", ("en", "sw", "lg"), "Africa/Kampala", "en-UG", '(road crash OR traffic accident OR collision) Uganda killed OR injured', 'Uganda bus crash killed injured'),
    Country("TZ", "TZA", "Tanzania", ("sw", "en"), "Africa/Dar_es_Salaam", "sw-TZ", '(ajali ya barabarani OR road crash OR bus accident) Tanzania kufariki OR killed OR injured', 'Tanzania bus crash killed'),
    Country("ET", "ETH", "Ethiopia", ("am", "en", "om"), "Africa/Addis_Ababa", "en-ET", '(road accident OR bus crash OR traffic collision) Ethiopia killed OR injured', 'Ethiopia wedding bus river crash killed'),
    Country("MA", "MAR", "Morocco", ("ar", "fr", "ber"), "Africa/Casablanca", "fr-MA", '(حادثة سير OR accident de la route OR bus accident) المغرب OR Maroc morts OR blessés', 'accident autocar Maroc morts'),
    Country("EG", "EGY", "Egypt", ("ar", "en"), "Africa/Cairo", "ar-EG", '(حادث سير OR حادث تصادم OR road crash) مصر OR Egypt قتلى OR injured', 'Egypt bus crash tourists killed'),
    Country("TN", "TUN", "Tunisia", ("ar", "fr"), "Africa/Tunis", "fr-TN", '(حادث مرور OR accident de la route OR collision) تونس OR Tunisie morts OR blessés', 'accident bus Tunisie morts'),
    Country("TR", "TUR", "Türkiye", ("tr",), "Europe/Istanbul", "tr-TR", '(trafik kazası OR otobüs kazası OR çarpışma) Türkiye öldü OR yaralandı', 'otobüs kazası Türkiye öldü'),
    Country("JO", "JOR", "Jordan", ("ar", "en"), "Asia/Amman", "ar-JO", '(حادث سير OR حادث مروري OR تصادم) الأردن OR Jordan وفيات OR injured', 'Jordan bus crash killed injured'),
)

INCIDENT_TERMS = {
    "accident", "crash", "collision", "killed", "injured", "dead", "dies", "died",
    "verkeersongeluk", "ongeval", "botsing", "trafikolycka", "bilolycka", "krasch",
    "trafikkulykke", "bilulykke", "kollisjon", "omkom", "wypadek", "zderzenie",
    "zginął", "zginęli", "ranni", "ajali", "حادث", "تصادم", "قتلى", "trafik",
    "kazası", "çarpışma", "öldü", "yaralandı", "morts", "blessés", "collision",
}
GENERIC_PAIR_TERMS = INCIDENT_TERMS | {
    "road", "traffic", "car", "bus", "vehicle", "people", "after", "into", "near",
    "with", "from", "that", "this", "have", "were", "been", "more", "news", "video",
    "nederland", "belgië", "belgique", "sverige", "norge", "polska", "south", "africa",
    "nigeria", "kenya", "ghana", "uganda", "tanzania", "ethiopia", "maroc", "المغرب",
    "egypt", "مصر", "tunisie", "تونس", "türkiye", "jordan", "الأردن",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def stable_id(country: Country, url: str) -> str:
    return f"gb-{country.alpha3.lower()}-{hashlib.sha256(url.encode()).hexdigest()[:16]}"


def rss_url(country: Country, query: str) -> str:
    lang, region = (country.locale.split("-", 1) + [country.alpha2])[:2]
    return (
        f"{DISCOVERY_BASE}?q={quote_plus(query + ' when:3y')}&hl={lang}-{region}"
        f"&gl={region}&ceid={region}:{lang}"
    )


def strip_publisher(title: str, publisher: str) -> str:
    suffix = f" - {publisher}".casefold()
    return title[: -len(suffix)].strip() if title.casefold().endswith(suffix) else title.strip()


def clean_text(value: str) -> str:
    value = BeautifulSoup(html.unescape(value), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", value).strip()


def short_excerpt(text: str, title: str, limit: int = 36) -> str:
    normalized = clean_text(text)
    if not normalized:
        return clean_text(title)
    sentences = re.split(r"(?<=[.!?。！？])\s+", normalized)
    selected = next((x for x in sentences if len(x.split()) >= 8), normalized)
    words = selected.split()
    return " ".join(words[:limit]) + (" …" if len(words) > limit else "")


def publisher_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return host


class Collector:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en,*;q=0.5"})
        self.robots: dict[str, tuple[str, urllib.robotparser.RobotFileParser | None]] = {}
        self.last_domain_request: dict[str, float] = defaultdict(float)

    def get_rss(self, endpoint: str) -> list[dict[str, Any]]:
        response = self.session.get(endpoint, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        rows: list[dict[str, Any]] = []
        for item in root.findall("./channel/item"):
            source = item.find("source")
            published = item.findtext("pubDate")
            try:
                published_at = parsedate_to_datetime(published).astimezone(UTC).isoformat() if published else None
            except (TypeError, ValueError):
                published_at = None
            rows.append(
                {
                    "rss_title": clean_text(item.findtext("title") or ""),
                    "google_url": item.findtext("link") or "",
                    "published_at": published_at,
                    "publisher": clean_text(source.text if source is not None and source.text else ""),
                    "publisher_home": source.attrib.get("url") if source is not None else None,
                }
            )
        return rows

    def decode(self, google_url: str) -> tuple[str | None, str | None]:
        result = new_decoderv1(google_url, interval=0.15)
        if result.get("status"):
            return result.get("decoded_url"), None
        return None, str(result.get("message", "decode_failed"))

    def robots_allowed(self, url: str) -> tuple[bool, str]:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robots:
            robots_url = f"{origin}/robots.txt"
            try:
                response = self.session.get(robots_url, timeout=12)
                if response.status_code == 404:
                    self.robots[origin] = ("not_found_allow", None)
                elif response.status_code == 200:
                    parser = urllib.robotparser.RobotFileParser()
                    parser.set_url(robots_url)
                    parser.parse(response.text.splitlines())
                    self.robots[origin] = ("fetched", parser)
                else:
                    self.robots[origin] = (f"http_{response.status_code}_skip", None)
            except requests.RequestException as exc:
                self.robots[origin] = (f"unavailable_skip:{type(exc).__name__}", None)
        status, parser = self.robots[origin]
        if parser is None:
            return status == "not_found_allow", status
        return parser.can_fetch(USER_AGENT, url), status

    def fetch_publisher(self, url: str) -> dict[str, Any]:
        checked_at = now()
        allowed, robots_status = self.robots_allowed(url)
        if not allowed:
            return {
                "outcome": "robots_disallowed" if robots_status == "fetched" else "robots_unavailable",
                "checked_at": checked_at,
                "robots": robots_status,
                "http_status": None,
            }
        domain = publisher_domain(url)
        wait = 1.0 - (time.monotonic() - self.last_domain_request[domain])
        if wait > 0:
            time.sleep(wait)
        self.last_domain_request[domain] = time.monotonic()
        try:
            response = self.session.get(url, timeout=15, allow_redirects=True)
        except requests.Timeout:
            return {"outcome": "timeout", "checked_at": checked_at, "robots": robots_status, "http_status": None}
        except requests.RequestException as exc:
            return {
                "outcome": "request_error",
                "error_class": type(exc).__name__,
                "checked_at": checked_at,
                "robots": robots_status,
                "http_status": None,
            }
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        base = {
            "checked_at": checked_at,
            "robots": robots_status,
            "http_status": response.status_code,
            "content_type": content_type or None,
            "final_url": response.url,
        }
        if response.status_code in {401, 403, 451}:
            return {**base, "outcome": "blocked"}
        if response.status_code == 429:
            return {**base, "outcome": "rate_limited"}
        if response.status_code >= 400:
            return {**base, "outcome": "http_error"}
        if content_type and "html" not in content_type:
            return {**base, "outcome": "unsupported_content_type"}
        extracted = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            favor_precision=True,
        )
        if not extracted or len(clean_text(extracted)) < 80:
            return {**base, "outcome": "no_reviewable_text"}
        return {
            **base,
            "outcome": "accessible",
            "page_text": clean_text(extracted),
            "content_sha256": hashlib.sha256(response.content).hexdigest(),
        }


def likely_incident(title: str) -> bool:
    tokens = set(re.findall(r"[^\W_]+", title.casefold(), flags=re.UNICODE))
    return bool(tokens & INCIDENT_TERMS)


def pair_tokens(title: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[^\W_]+", title.casefold(), flags=re.UNICODE)
        if len(token) >= 4 and token not in GENERIC_PAIR_TERMS
    }
    return tokens


def pair_score(left: dict[str, Any], right: dict[str, Any]) -> tuple[float, list[str]]:
    lt, rt = pair_tokens(left["title"]), pair_tokens(right["title"])
    shared = sorted(lt & rt)
    jac = len(set(shared)) / len(lt | rt) if lt | rt else 0
    sequence = SequenceMatcher(None, left["title"].casefold(), right["title"].casefold()).ratio()
    date_score = 0.0
    try:
        delta = abs(
            (datetime.fromisoformat(left["published_at"]) - datetime.fromisoformat(right["published_at"])).total_seconds()
        ) / 86400
        date_score = max(0.0, 1 - delta / 7)
    except (TypeError, ValueError):
        pass
    return 0.55 * jac + 0.30 * sequence + 0.15 * date_score, shared


def choose_pair(country: Country, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    options: list[tuple[float, list[str], dict[str, Any], dict[str, Any]]] = []
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            if left["publisher_domain"] == right["publisher_domain"]:
                continue
            score, shared = pair_score(left, right)
            if len(shared) >= 2 and score >= 0.36:
                options.append((score, shared, left, right))
    if not options:
        return None
    score, shared, left, right = max(options, key=lambda item: item[0])
    pair_id = f"gb-pair-{country.alpha3.lower()}-{hashlib.sha256((left['candidate_id'] + right['candidate_id']).encode()).hexdigest()[:12]}"
    return {
        "pair_id": pair_id,
        "country_code": country.alpha3,
        "country_code_alpha2": country.alpha2,
        "country_name": country.name,
        "relation": "credible_same_incident_candidate",
        "left_candidate_id": left["candidate_id"],
        "right_candidate_id": right["candidate_id"],
        "left_publisher_domain": left["publisher_domain"],
        "right_publisher_domain": right["publisher_domain"],
        "left_title": left["title"],
        "right_title": right["title"],
        "left_url": left["manual_verification_url"],
        "right_url": right["manual_verification_url"],
        "shared_distinctive_terms": shared,
        "discovery_similarity_score": round(score, 4),
        "rationale": "Distinct publisher domains, closely aligned publication timing, and shared distinctive event terms indicate a credible same-incident candidate.",
        "independence_assessment": "distinct_publisher_domains; common upstream wire or syndication not ruled out",
        "human_verification_required": True,
        "created_at": now(),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def collect_country(collector: Collector, country: Country, force: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidate_path = ROOT / "countries" / f"{country.alpha2}.candidates.jsonl"
    attempt_path = ROOT / "countries" / f"{country.alpha2}.attempts.jsonl"
    if candidate_path.exists() and not force:
        cached = read_jsonl(candidate_path)
        if len(cached) >= TARGET:
            return cached, read_jsonl(attempt_path)

    discovered_at = now()
    endpoints = [rss_url(country, country.query), rss_url(country, country.pair_query)]
    discovery_rows: list[dict[str, Any]] = []
    seen_google: set[str] = set()
    for endpoint in endpoints:
        try:
            items = collector.get_rss(endpoint)
        except Exception as exc:  # persisted for resumable auditing
            discovery_rows.append({"discovery_error": type(exc).__name__, "message": str(exc), "endpoint": endpoint})
            continue
        for item in items:
            if item["google_url"] in seen_google or not likely_incident(item["rss_title"]):
                continue
            seen_google.add(item["google_url"])
            item["discovery_endpoint"] = endpoint
            discovery_rows.append(item)

    candidates: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    seen_direct: set[str] = set()
    domain_counts: dict[str, int] = defaultdict(int)
    # Prefer publisher diversity, recency is already supplied by the RSS ordering.
    for item in discovery_rows[:90]:
        if "google_url" not in item:
            attempts.append({"country_code": country.alpha3, "stage": "rss", **item, "recorded_at": now()})
            continue
        direct_url, decode_error = collector.decode(item["google_url"])
        if not direct_url:
            attempts.append(
                {
                    "country_code": country.alpha3,
                    "stage": "decode",
                    "outcome": "decode_failed",
                    "error": decode_error,
                    "google_url": item["google_url"],
                    "discovery_endpoint": item["discovery_endpoint"],
                    "recorded_at": now(),
                }
            )
            continue
        parsed = urlparse(direct_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        canonical = direct_url.split("#", 1)[0]
        if canonical in seen_direct:
            continue
        seen_direct.add(canonical)
        domain = publisher_domain(canonical)
        # Keep exploring sparse domains before taking a fourth item from one publisher.
        if domain_counts[domain] >= 3 and len(candidates) < TARGET:
            continue
        access = collector.fetch_publisher(canonical)
        public_access = {key: value for key, value in access.items() if key != "page_text"}
        attempts.append(
            {
                "country_code": country.alpha3,
                "country_code_alpha2": country.alpha2,
                "stage": "publisher_access",
                "url": canonical,
                "publisher_domain": domain,
                "discovery_endpoint": item["discovery_endpoint"],
                **public_access,
                "recorded_at": now(),
            }
        )
        if access["outcome"] != "accessible":
            continue
        final_url = str(access.get("final_url") or canonical)
        domain = publisher_domain(final_url)
        title = strip_publisher(item["rss_title"], item["publisher"])
        excerpt = short_excerpt(str(access["page_text"]), title)
        record = {
            "schema_version": "candidate-discovery-1.0.0",
            "candidate_id": stable_id(country, final_url),
            "country_code": country.alpha3,
            "country_code_alpha2": country.alpha2,
            "country_name": country.name,
            "country_assignment": "discovery_query; requires reviewer confirmation from publisher content",
            "languages": list(country.languages),
            "timezone": country.timezone,
            "traffic_incident": True,
            "review_status": "pending",
            "publisher": item["publisher"] or domain,
            "publisher_domain": domain,
            "publisher_home": item["publisher_home"],
            "title": title,
            "short_excerpt": excerpt,
            "excerpt_basis": "accessible direct publisher page; maximum 36 words",
            "published_at": item["published_at"],
            "discovered_at": discovered_at,
            "discovery_service": "Google News RSS",
            "discovery_endpoint": item["discovery_endpoint"],
            "discovery_result_url": item["google_url"],
            "direct_publisher_url": final_url,
            "manual_verification_url": final_url,
            "access_result": public_access,
            "capture_status": "metadata_only_not_captured",
            "redistribution_status": "metadata_only",
            "independence": "unknown",
            "dependency_group": f"pending:{domain}",
            "verification_note": "Candidate metadata only. A human must confirm country, incident eligibility, content match, and editorial independence before acceptance.",
        }
        if record["candidate_id"] in {x["candidate_id"] for x in candidates}:
            continue
        candidates.append(record)
        domain_counts[domain] += 1
        if len(candidates) >= MAX_ACCEPTED:
            break

    write_jsonl(candidate_path, candidates)
    write_jsonl(attempt_path, attempts)
    return candidates, attempts


def build_summary(all_candidates: list[dict[str, Any]], all_pairs: list[dict[str, Any]], all_attempts: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for country in COUNTRIES:
        candidates = [x for x in all_candidates if x["country_code"] == country.alpha3]
        attempts = [x for x in all_attempts if x.get("country_code") == country.alpha3]
        outcomes: dict[str, int] = defaultdict(int)
        for attempt in attempts:
            outcomes[str(attempt.get("outcome", attempt.get("stage", "unknown")))] += 1
        rows.append(
            {
                "country_code": country.alpha3,
                "country_code_alpha2": country.alpha2,
                "country_name": country.name,
                "candidate_count": len(candidates),
                "distinct_publisher_domains": len({x["publisher_domain"] for x in candidates}),
                "pair_count": sum(1 for x in all_pairs if x["country_code"] == country.alpha3),
                "target_met": len(candidates) >= TARGET,
                "access_outcomes": dict(sorted(outcomes.items())),
            }
        )
    return {
        "group": "B",
        "generated_at": now(),
        "target_candidates_per_country": TARGET,
        "countries_requested": len(COUNTRIES),
        "countries_meeting_candidate_target": sum(1 for row in rows if row["target_met"]),
        "countries_with_pair": sum(1 for row in rows if row["pair_count"] >= 1),
        "total_candidates": len(all_candidates),
        "total_distinct_urls": len({x["manual_verification_url"] for x in all_candidates}),
        "total_pairs": len(all_pairs),
        "limitations": [
            "Discovery candidates are not accepted corpus sources and have not received formal human review.",
            "Country assignment is query-based and requires confirmation from each publisher page.",
            "Distinct publisher domains do not rule out syndication or a shared upstream report.",
            "Short excerpts are limited to 36 words and retained only for manual triage; payloads were not captured.",
            "Blocked, robots-disallowed, rate-limited, inaccessible, or unextractable pages were excluded from candidate JSONL and retained in access-attempt logs.",
        ],
        "countries": rows,
    }


def write_summary_markdown(summary: dict[str, Any]) -> None:
    lines = [
        "# Group B live candidate discovery summary",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        f"- Candidate records: **{summary['total_candidates']}**",
        f"- Countries meeting the >= {TARGET} target: **{summary['countries_meeting_candidate_target']} / {summary['countries_requested']}**",
        f"- Countries with a credible distinct-domain pair: **{summary['countries_with_pair']} / {summary['countries_requested']}**",
        f"- Distinct direct publisher URLs: **{summary['total_distinct_urls']}**",
        "",
        "| Country | Candidates | Publisher domains | Pairs | Target | Access blockers / exclusions |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in summary["countries"]:
        blocked = ", ".join(f"{key}: {value}" for key, value in row["access_outcomes"].items() if key != "accessible") or "none recorded"
        lines.append(
            f"| {row['country_code']} — {row['country_name']} | {row['candidate_count']} | "
            f"{row['distinct_publisher_domains']} | {row['pair_count']} | "
            f"{'met' if row['target_met'] else 'NOT MET'} | {blocked} |"
        )
    lines.extend(["", "## Interpretation limits", ""])
    lines.extend(f"- {item}" for item in summary["limitations"])
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `candidates.jsonl`: accessible direct-publisher candidate metadata.",
            "- `pairs.jsonl`: one or more credible same-incident pair candidates where found.",
            "- `access_attempts.jsonl`: decode, robots, HTTP, extraction, and other exclusion outcomes.",
            "- `countries/*.jsonl`: resumable per-country checkpoints.",
            "- `summary.json`: machine-readable totals.",
        ]
    )
    (ROOT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", action="append", help="Two-letter country code; repeatable")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    selected = [x for x in COUNTRIES if not args.country or x.alpha2 in set(args.country)]
    collector = Collector()
    for country in selected:
        candidates, attempts = collect_country(collector, country, force=args.force)
        print(f"{country.alpha2}: {len(candidates)} candidates, {len(attempts)} attempts", flush=True)

    all_candidates: list[dict[str, Any]] = []
    all_attempts: list[dict[str, Any]] = []
    all_pairs: list[dict[str, Any]] = []
    for country in COUNTRIES:
        candidates = read_jsonl(ROOT / "countries" / f"{country.alpha2}.candidates.jsonl")
        attempts = read_jsonl(ROOT / "countries" / f"{country.alpha2}.attempts.jsonl")
        all_candidates.extend(candidates)
        all_attempts.extend(attempts)
        pair = choose_pair(country, candidates)
        if pair:
            all_pairs.append(pair)
    pair_by_candidate: dict[str, dict[str, Any]] = {}
    for pair in all_pairs:
        incident_key = pair["pair_id"]
        for candidate_id in (pair["left_candidate_id"], pair["right_candidate_id"]):
            pair_by_candidate[candidate_id] = {
                "incident_key": incident_key,
                "pair_confidence": pair["discovery_similarity_score"],
                "pair_reason": pair["rationale"] + " " + pair["independence_assessment"],
            }
    compiler_rows: list[dict[str, Any]] = []
    for candidate in all_candidates:
        pair_fields = pair_by_candidate.get(candidate["candidate_id"], {})
        compiler_rows.append(
            {
                "country_iso2": candidate["country_code_alpha2"],
                "canonical_url": candidate["manual_verification_url"],
                "title": candidate["title"],
                "publisher": candidate["publisher"],
                "domain": candidate["publisher_domain"],
                "excerpt": candidate["short_excerpt"],
                "languages": candidate["languages"],
                "published_at": candidate["published_at"],
                "discovered_at": candidate["discovered_at"],
                "discovered_via": "google_news_rss",
                "discovery_url": candidate["discovery_endpoint"],
                "access_status": candidate["access_result"]["outcome"],
                "incident_key": pair_fields.get("incident_key"),
                "pair_confidence": pair_fields.get("pair_confidence"),
                "pair_reason": pair_fields.get("pair_reason"),
            }
        )
    write_jsonl(ROOT / "candidates.jsonl", compiler_rows)
    write_jsonl(ROOT / "access_attempts.jsonl", all_attempts)
    write_jsonl(ROOT / "pairs.jsonl", all_pairs)
    summary = build_summary(all_candidates, all_pairs, all_attempts)
    (ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_summary_markdown(summary)
    print(json.dumps({key: summary[key] for key in ("total_candidates", "countries_meeting_candidate_target", "total_pairs", "countries_with_pair")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
