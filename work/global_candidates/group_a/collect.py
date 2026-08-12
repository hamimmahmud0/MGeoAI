#!/usr/bin/env python3
"""Resumable, metadata-only traffic article discovery for group A countries.

This script stores public feed metadata and verifies publisher URLs without
scraping article bodies. Google News links are resolved to publisher URLs, and
blocked/unavailable URLs are retained only in the access-failure ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx


ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw"
STATE_PATH = ROOT / "state.json"
CANDIDATES_PATH = ROOT / "candidates.jsonl"
PAIRS_PATH = ROOT / "same_incident_pairs.jsonl"
FAILURES_PATH = ROOT / "access_failures.jsonl"
SUMMARY_PATH = ROOT / "summary.json"
METHODOLOGY_PATH = ROOT / "README.md"

GOOGLE_RSS = "https://news.google.com/rss/search"
GOOGLE_BATCH = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36 MGeoAI-research/0.1"
)
TARGET = 15
COUNTRY_QUERY_NAMES = {
    "US": "United States",
    "CA": "Canada",
    "MX": "México",
    "BR": "Brasil",
    "AR": "Argentina",
    "CL": "Chile",
    "CO": "Colombia",
    "PE": "Perú",
    "EC": "Ecuador",
    "CR": "Costa Rica",
    "GB": "United Kingdom",
    "IE": "Ireland",
    "FR": "France",
    "DE": "Deutschland",
    "ES": "España",
    "PT": "Portugal",
    "IT": "Italia",
}
CEID_LANGUAGE = {
    "MX": "es-419",
    "BR": "pt-419",
    "AR": "es-419",
    "CL": "es-419",
    "CO": "es-419",
    "PE": "es-419",
    "EC": "es-419",
    "CR": "es-419",
    "PT": "pt-150",
}


@dataclass(frozen=True)
class Profile:
    iso2: str
    name: str
    language: str
    hl: str
    terms: tuple[str, ...]
    casualty_terms: tuple[str, ...]

    @property
    def query(self) -> str:
        traffic = " OR ".join(f'\"{term}\"' for term in self.terms)
        casualties = " OR ".join(self.casualty_terms)
        country = COUNTRY_QUERY_NAMES.get(self.iso2)
        qualifier = f' \"{country}\"' if country else ""
        return f"({traffic}) ({casualties}){qualifier} when:90d"

    @property
    def discovery_url(self) -> str:
        request = httpx.Request("GET", GOOGLE_RSS, params=self.params)
        return str(request.url)

    @property
    def params(self) -> dict[str, str]:
        return {
            "q": self.query,
            "hl": self.hl,
            "gl": self.iso2,
            "ceid": f"{self.iso2}:{CEID_LANGUAGE.get(self.iso2, self.language)}",
        }


PROFILES = (
    Profile("US", "United States", "en", "en-US", ("traffic crash", "highway crash", "car crash", "vehicle collision"), ("killed", "dead", "injured")),
    Profile("CA", "Canada", "en", "en-CA", ("traffic collision", "highway crash", "car crash", "road accident"), ("killed", "dead", "injured")),
    Profile("MX", "Mexico", "es", "es-419", ("accidente de tránsito", "accidente carretero", "choque vehicular", "colisión vial"), ("muerto", "muertos", "herido", "heridos")),
    Profile("BR", "Brazil", "pt", "pt-BR", ("acidente de trânsito", "acidente rodoviário", "colisão de veículos", "acidente de ônibus"), ("morto", "mortos", "ferido", "feridos")),
    Profile("AR", "Argentina", "es", "es-419", ("accidente vial", "choque vehicular", "siniestro vial", "accidente de tránsito"), ("muerto", "muertos", "herido", "heridos")),
    Profile("CL", "Chile", "es", "es-419", ("accidente de tránsito", "choque vehicular", "colisión vial", "accidente carretero"), ("muerto", "muertos", "herido", "heridos")),
    Profile("CO", "Colombia", "es", "es-419", ("accidente vial", "accidente de tránsito", "choque vehicular", "siniestro vial"), ("muerto", "muertos", "herido", "heridos")),
    Profile("PE", "Peru", "es", "es-419", ("accidente de tránsito", "choque vehicular", "accidente carretero", "siniestro vial"), ("muerto", "muertos", "herido", "heridos")),
    Profile("EC", "Ecuador", "es", "es-419", ("accidente de tránsito", "siniestro vial", "choque vehicular", "accidente de bus"), ("muerto", "muertos", "herido", "heridos")),
    Profile("CR", "Costa Rica", "es", "es-419", ("accidente de tránsito", "choque vehicular", "accidente vial", "colisión en carretera"), ("muerto", "muertos", "herido", "heridos")),
    Profile("GB", "United Kingdom", "en", "en-GB", ("road accident", "traffic collision", "motorway crash", "vehicle collision"), ("killed", "dead", "injured")),
    Profile("IE", "Ireland", "en", "en-IE", ("road accident", "traffic collision", "road crash", "vehicle collision"), ("killed", "dead", "injured")),
    Profile("FR", "France", "fr", "fr", ("accident de la route", "collision routière", "accident de voiture", "accident de bus"), ("mort", "morts", "blessé", "blessés")),
    Profile("DE", "Germany", "de", "de", ("Verkehrsunfall", "Autounfall", "Busunfall", "Zusammenstoß"), ("tot", "Tote", "verletzt", "Verletzte")),
    Profile("ES", "Spain", "es", "es", ("accidente de tráfico", "accidente de carretera", "choque de vehículos", "colisión vial"), ("muerto", "muertos", "herido", "heridos")),
    Profile("PT", "Portugal", "pt", "pt-PT", ("acidente rodoviário", "acidente de viação", "colisão de veículos", "acidente de autocarro"), ("morto", "mortos", "ferido", "feridos")),
    Profile("IT", "Italy", "it", "it", ("incidente stradale", "scontro tra veicoli", "incidente automobilistico", "incidente autobus"), ("morto", "morti", "ferito", "feriti")),
)


GENERIC = {
    "accident", "accidente", "acidente", "incidente", "crash", "collision",
    "colision", "colisão", "road", "route", "traffic", "tránsito", "transito",
    "stradale", "highway", "vehicle", "vehicles", "vehicular", "veicoli",
    "killed", "dead", "injured", "muerto", "muertos", "morto", "mortos",
    "morti", "mort", "morts", "herido", "heridos", "ferido", "feridos",
    "feriti", "blessé", "blessés", "verletzt", "verletzte", "tot", "tote",
    "verkehrsunfall", "autounfall", "busunfall", "zusammenstoß", "deja", "varios",
    "the", "and", "of", "in", "on", "at", "to", "a", "an", "de", "del",
    "la", "el", "en", "un", "una", "y", "e", "di", "da", "do", "dos",
    "das", "der", "die", "mit", "bei", "sur", "le", "les", "des", "et",
}


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode()
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:20]}"


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda row: (row.get("country_iso2", ""), row.get("canonical_url", row.get("pair_id", ""))))
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in ordered), encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_publisher(title: str, publisher: str) -> str:
    suffix = f" - {publisher}"
    return title[: -len(suffix)].strip() if title.casefold().endswith(suffix.casefold()) else title


def hostname(url: str) -> str:
    return (urlparse(url).hostname or "").casefold().removeprefix("www.")


def tokenize(title: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", title.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = set(re.findall(r"[a-z0-9]{3,}", normalized))
    return {token for token in tokens if token not in GENERIC}


def parse_seen(value: str) -> datetime | None:
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(value)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except (TypeError, ValueError, OverflowError):
            return None


def published_iso(value: str | None) -> str | None:
    parsed = parse_seen(value or "")
    if not parsed:
        return None
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_incident_title(title: str, profile: Profile) -> bool:
    folded = unicodedata.normalize("NFKD", title.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    terms = [*profile.terms, *profile.casualty_terms]
    normalized_terms = []
    for term in terms:
        normalized = unicodedata.normalize("NFKD", term.casefold())
        normalized_terms.append("".join(char for char in normalized if not unicodedata.combining(char)))
    excluded = (
        "statistics", "data:", "crash test", "attenuator", "insurance",
        "seguridad vial", "road safety week", "simulation", "video game",
    )
    return any(term in folded for term in normalized_terms) and not any(item in folded for item in excluded)


def fetch_feed(profile: Profile, client: httpx.Client, refresh: bool) -> list[dict[str, Any]]:
    cache = RAW_DIR / f"{profile.iso2}.json"
    if cache.exists() and not refresh:
        return load_json(cache, [])
    response = client.get(
        GOOGLE_RSS,
        params=profile.params,
        timeout=30,
        follow_redirects=True,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    rows: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        source = item.find("source")
        publisher = clean_text(source.text if source is not None else None)
        publisher_homepage = clean_text(source.attrib.get("url") if source is not None else None)
        rss_title = clean_text(item.findtext("title"))
        title = strip_publisher(rss_title, publisher)
        if not title or not is_incident_title(title, profile):
            continue
        rows.append(
            {
                "country_iso2": profile.iso2,
                "country_name": profile.name,
                "title": title,
                "publisher": publisher,
                "publisher_homepage": publisher_homepage,
                "publisher_domain_hint": hostname(publisher_homepage),
                "published_at": clean_text(item.findtext("pubDate")) or None,
                "rss_url": clean_text(item.findtext("link")),
                "rss_guid": clean_text(item.findtext("guid")),
                "rss_excerpt": title[:400],
                "source_discovery_endpoint": profile.discovery_url,
                "language": profile.language,
                "discovered_at": now(),
            }
        )
    dump_json(cache, rows)
    return rows


def pair_score(left: dict[str, Any], right: dict[str, Any]) -> tuple[float, list[str]]:
    if left["publisher_domain_hint"] == right["publisher_domain_hint"]:
        return 0.0, []
    if clean_text(left.get("publisher", "")).casefold() == clean_text(right.get("publisher", "")).casefold():
        return 0.0, []
    left_tokens, right_tokens = tokenize(left["title"]), tokenize(right["title"])
    shared = left_tokens & right_tokens
    if len(shared) < 2:
        return 0.0, []
    union = left_tokens | right_tokens
    jaccard = len(shared) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, left["title"].casefold(), right["title"].casefold()).ratio()
    left_date, right_date = parse_seen(left.get("published_at")), parse_seen(right.get("published_at"))
    days = abs((left_date - right_date).total_seconds()) / 86400 if left_date and right_date else 99
    strong_match = sequence >= 0.82 or (len(shared) >= 3 and jaccard >= 0.30 and sequence >= 0.48)
    if days > 3 or not strong_match:
        return 0.0, []
    score = min(0.98, 0.52 * jaccard + 0.38 * sequence + (0.10 if days <= 1 else 0.04))
    reasons = [f"independent domains", f"shared distinctive title tokens: {', '.join(sorted(shared)[:8])}", f"publication timestamps {days:.1f} days apart"]
    return score, reasons


def best_pair(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], float, list[str]] | None:
    best: tuple[dict[str, Any], dict[str, Any], float, list[str]] | None = None
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            score, reasons = pair_score(left, right)
            if score >= 0.50 and (best is None or score > best[2]):
                best = left, right, score, reasons
    return best


def priority_rows(rows: list[dict[str, Any]], pair: tuple[dict[str, Any], dict[str, Any], float, list[str]] | None) -> list[dict[str, Any]]:
    prioritized: list[dict[str, Any]] = []
    if pair:
        prioritized.extend(pair[:2])
    seen_ids = {id(row) for row in prioritized}
    seen_domains = {row["publisher_domain_hint"] for row in prioritized}
    for row in rows:
        if id(row) in seen_ids or row["publisher_domain_hint"] in seen_domains:
            continue
        prioritized.append(row)
        seen_ids.add(id(row))
        seen_domains.add(row["publisher_domain_hint"])
    prioritized.extend(row for row in rows if id(row) not in seen_ids)
    return prioritized


def decode_google_url(row: dict[str, Any], client: httpx.Client) -> tuple[str | None, str | None]:
    token = row.get("rss_guid") or urlparse(row["rss_url"]).path.rstrip("/").split("/")[-1]
    if not token:
        return None, "missing Google News article token"
    try:
        response = client.get(
            f"https://news.google.com/rss/articles/{token}?oc=5",
            timeout=20,
            follow_redirects=True,
        )
        response.raise_for_status()
        signature = re.search(r'data-n-a-sg="([^"]+)"', response.text)
        timestamp = re.search(r'data-n-a-ts="([^"]+)"', response.text)
        if not signature or not timestamp:
            return None, "Google News decoding parameters absent"
        # The undocumented resolver RPC expects the service locale, not the
        # publisher-country locale used by RSS discovery.
        locale = "US:en"
        inner = (
            '[["X","X",["X","X"],null,null,1,1,"' + locale +
            '",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"' +
            token + '",' + timestamp.group(1) + ',"' + signature.group(1) + '"]'
        )
        payload = [["Fbv4je", "[\"garturlreq\"," + inner + "]"]]
        decoded = client.post(
            GOOGLE_BATCH,
            content=f"f.req={quote(json.dumps([payload]))}",
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            timeout=20,
        )
        decoded.raise_for_status()
        chunks = decoded.text.split("\n\n")
        outer = json.loads(chunks[1])[:-2]
        direct = json.loads(outer[0][2])[1]
        if urlparse(direct).scheme not in {"http", "https"} or not hostname(direct):
            return None, "decoded URL was not public HTTP(S)"
        return direct, None
    except (httpx.HTTPError, TypeError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:180]}"


def verify_publisher(url: str, client: httpx.Client) -> dict[str, Any]:
    checked_at = now()
    try:
        with client.stream("GET", url, headers={"Range": "bytes=0-1023"}, timeout=12, follow_redirects=True) as response:
            status = response.status_code
            final_url = str(response.url)
            content_type = response.headers.get("content-type")
        if 200 <= status < 400:
            result = "accessible"
        elif status in {401, 403, 407, 418, 429, 451}:
            result = "blocked"
        elif status in {404, 410}:
            result = "unavailable"
        else:
            result = "http_error"
        return {"result": result, "http_status": status, "checked_at": checked_at, "final_url": final_url, "content_type": content_type}
    except httpx.HTTPError as exc:
        return {"result": "request_error", "http_status": None, "checked_at": checked_at, "final_url": url, "content_type": None, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def collect_country(profile: Profile, client: httpx.Client, state: dict[str, Any], refresh: bool) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]]]:
    feed_rows = fetch_feed(profile, client, refresh)
    proposed_pair = best_pair(feed_rows)
    rows = priority_rows(feed_rows, proposed_pair)
    accepted: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    decoded_by_guid = state.setdefault("decoded_urls", {})
    access_by_url = state.setdefault("access_results", {})
    for row in rows[:60]:
        if len(accepted) >= TARGET:
            break
        guid = row["rss_guid"]
        direct = decoded_by_guid.get(guid)
        decode_error = None
        if not direct:
            direct, decode_error = decode_google_url(row, client)
            if direct:
                decoded_by_guid[guid] = direct
                dump_json(STATE_PATH, state)
            time.sleep(0.35)
        if not direct:
            failures.append({**row, "access_result": "resolution_failed", "error": decode_error})
            continue
        domain = hostname(direct)
        if not domain:
            failures.append({**row, "direct_url": direct, "access_result": "invalid_direct_url"})
            continue
        access = access_by_url.get(direct)
        if not access:
            access = verify_publisher(direct, client)
            access_by_url[direct] = access
            dump_json(STATE_PATH, state)
            time.sleep(0.25)
        if access["result"] != "accessible":
            failures.append({**row, "direct_url": direct, "publisher_domain": domain, "access_result": access["result"], "access_check": access})
            continue
        final_url = access.get("final_url") or direct
        accepted.append(
            {
                "country_iso2": profile.iso2,
                "canonical_url": final_url,
                "title": row["title"],
                "publisher": row["publisher"],
                "domain": hostname(final_url),
                "excerpt": row["rss_excerpt"],
                "languages": [row["language"]],
                "published_at": published_iso(row["published_at"]),
                "discovered_at": row["discovered_at"],
                "discovered_via": "google_news_rss",
                "discovery_url": row["source_discovery_endpoint"],
                "access_status": access["result"],
                "incident_key": None,
                "pair_confidence": None,
                "pair_reason": None,
            }
        )
    deduped = list({item["canonical_url"]: item for item in accepted}.values())
    accepted = deduped[:TARGET]
    pair_record = make_pair_record(profile, accepted)
    if pair_record:
        pair_urls = set(pair_record["candidate_urls"])
        for item in accepted:
            if item["canonical_url"] in pair_urls:
                item["incident_key"] = pair_record["incident_key"]
                item["pair_confidence"] = pair_record["confidence"]
                item["pair_reason"] = pair_record["reason"]
    return accepted, pair_record, failures


def make_pair_record(profile: Profile, accepted: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = [
        {
            **row,
            "publisher_domain_hint": row["domain"],
        }
        for row in accepted
    ]
    pair = best_pair(rows)
    if not pair:
        return None
    left, right, score, reasons = pair
    confidence = round(score, 4)
    incident_key = stable_id("incident", profile.iso2, *sorted((left["canonical_url"], right["canonical_url"])))
    return {
        "schema_version": "1.0.0",
        "pair_id": stable_id("pair", profile.iso2, left["canonical_url"], right["canonical_url"]),
        "incident_key": incident_key,
        "country_iso2": profile.iso2,
        "relationship": "plausible_same_incident",
        "candidate_urls": [left["canonical_url"], right["canonical_url"]],
        "independent_domains": [left["domain"], right["domain"]],
        "confidence": confidence,
        "confidence_label": "high" if score >= 0.68 else "medium",
        "score": round(score, 4),
        "reason": "; ".join(reasons),
        "manual_verification_required": True,
        "verification_urls": [left["canonical_url"], right["canonical_url"]],
        "asserts_same_incident": False,
    }


def write_methodology() -> None:
    METHODOLOGY_PATH.write_text(
        """# Group A live candidate discovery\n\n"
        "This directory is a resumable metadata-only candidate ledger for 17 countries. "
        "`collect.py` queries country-localized Google News RSS over a bounded 90-day window, "
        "resolves aggregator links to publisher URLs, and makes a range-limited GET only to "
        "classify publisher access. It does not save article bodies.\n\n"
        "- `raw/<ISO2>.json`: parsed RSS metadata cache (not article content).\n"
        "- `state.json`: resolved-link and access-check cache for resumption.\n"
        "- `candidates.jsonl`: accessible direct publisher candidates.\n"
        "- `same_incident_pairs.jsonl`: cross-domain suggestions requiring manual verification.\n"
        "- `access_failures.jsonl`: blocked, unavailable, or unresolved discoveries.\n"
        "- `summary.json`: counts, deficits, methods, and blockers.\n\n"
        "Pair suggestions are not truth assertions. They require two domains, at least two "
        "distinctive shared title tokens, close publication timestamps, and a similarity threshold.\n\n"
        "Run `python work/global_candidates/group_a/collect.py`; add `--refresh-feeds` only to "
        "replace cached feed metadata.\n"
        """,
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-feeds", action="store_true")
    parser.add_argument("--countries", nargs="*", default=[])
    args = parser.parse_args()
    selected = [profile for profile in PROFILES if not args.countries or profile.iso2 in {item.upper() for item in args.countries}]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    state = load_json(STATE_PATH, {"schema_version": "1.0.0", "decoded_urls": {}, "access_results": {}})
    selected_codes = {profile.iso2 for profile in selected}
    all_candidates = [row for row in load_jsonl(CANDIDATES_PATH) if row.get("country_iso2") not in selected_codes]
    all_pairs = [row for row in load_jsonl(PAIRS_PATH) if row.get("country_iso2") not in selected_codes]
    all_failures = [row for row in load_jsonl(FAILURES_PATH) if row.get("country_iso2") not in selected_codes]
    previous_summary = load_json(SUMMARY_PATH, {})
    per_country: dict[str, Any] = {
        iso2: value
        for iso2, value in previous_summary.get("per_country", {}).items()
        if iso2 not in selected_codes
    }
    with httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Language": "en,*;q=0.5"}) as client:
        for profile in selected:
            print(f"[{profile.iso2}] collecting", flush=True)
            try:
                candidates, pair, failures = collect_country(profile, client, state, args.refresh_feeds)
            except (httpx.HTTPError, ET.ParseError, OSError, ValueError) as exc:
                candidates, pair, failures = [], None, [{"country_iso2": profile.iso2, "access_result": "discovery_failed", "error": f"{type(exc).__name__}: {exc}"}]
            all_candidates.extend(candidates)
            if pair:
                all_pairs.append(pair)
            all_failures.extend(failures)
            per_country[profile.iso2] = {
                "country_name": profile.name,
                "candidate_count": len(candidates),
                "distinct_publisher_domains": len({row["domain"] for row in candidates}),
                "pair_count": 1 if pair else 0,
                "target_met": len(candidates) >= TARGET,
                "pair_target_met": pair is not None,
                "failure_count": len(failures),
                "blockers": ([f"candidate deficit: {TARGET - len(candidates)}"] if len(candidates) < TARGET else []) + (["no defensible cross-domain same-incident pair met the threshold"] if not pair else []),
            }
            dump_jsonl(CANDIDATES_PATH, all_candidates)
            dump_jsonl(PAIRS_PATH, all_pairs)
            dump_jsonl(FAILURES_PATH, all_failures)
            dump_json(STATE_PATH, state)
            print(f"[{profile.iso2}] {len(candidates)} candidates; pair={'yes' if pair else 'no'}; failures={len(failures)}", flush=True)
    summary = {
        "schema_version": "1.0.0",
        "generated_at": now(),
        "scope": "group_a",
        "requested_countries": sorted(per_country),
        "country_count": len(per_country),
        "candidate_target_per_country": TARGET,
        "total_candidates": len(all_candidates),
        "total_distinct_direct_urls": len({row["canonical_url"] for row in all_candidates}),
        "total_pair_suggestions": len(all_pairs),
        "countries_meeting_candidate_target": sum(item["target_met"] for item in per_country.values()),
        "countries_meeting_pair_target": sum(item["pair_target_met"] for item in per_country.values()),
        "discovery_methods": ["Google News RSS localized search", "Google News publisher-link resolution", "range-limited publisher GET access classification"],
        "unavailable_method": {"name": "GDELT DOC 2.0", "result": "HTTP 429 global rate limit during this collection window"},
        "limitations": ["RSS title is the only excerpt retained.", "Publisher bodies are not captured.", "Pair records are suggestions requiring manual verification, not same-incident assertions."],
        "per_country": per_country,
    }
    dump_json(SUMMARY_PATH, summary)
    write_methodology()
    return 0 if all(item["target_met"] and item["pair_target_met"] for item in per_country.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
