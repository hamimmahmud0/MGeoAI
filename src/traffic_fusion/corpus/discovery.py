from __future__ import annotations

import ipaddress
import json
import re
import tomllib
import urllib.robotparser
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, Tag

from traffic_fusion.utils import normalize_text, stable_hash, stable_id, write_json

GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_GDELT_RECORDS = 250
MAX_GDELT_WINDOW_DAYS = 90
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}
REMOVED_ELEMENTS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "canvas",
    "img",
    "picture",
    "source",
    "video",
    "audio",
    "iframe",
    "object",
    "embed",
    "form",
    "button",
}
REMOVED_CONTEXT = {"nav", "footer", "aside"}


class DiscoveryError(RuntimeError):
    """A bounded discovery or capture operation could not be completed safely."""


@dataclass(frozen=True, slots=True)
class CountryProfile:
    iso2: str
    iso3: str
    name: str
    primary_timezone: str
    coverage_latitude: float
    coverage_longitude: float
    languages: tuple[str, ...]
    query_terms: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "iso2": self.iso2,
            "iso3": self.iso3,
            "name": self.name,
            "primary_timezone": self.primary_timezone,
            "coverage_centroid": {
                "latitude": self.coverage_latitude,
                "longitude": self.coverage_longitude,
                "role": "collection_country_coverage_centroid",
                "is_incident_location": False,
            },
            "languages": list(self.languages),
            "query_terms": list(self.query_terms),
        }

    def to_coverage_feature(self) -> dict[str, Any]:
        """Return a publisher-coverage marker, never an incident coordinate."""
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [self.coverage_longitude, self.coverage_latitude],
            },
            "properties": {
                "iso2": self.iso2,
                "iso3": self.iso3,
                "country_name": self.name,
                "primary_timezone": self.primary_timezone,
                "geometry_role": "collection_country_coverage_centroid",
                "is_incident_location": False,
            },
        }


@dataclass(frozen=True, slots=True)
class DiscoveredArticle:
    discovery_id: str
    country_iso2: str
    url: str
    title: str | None
    domain: str
    seen_at: str | None
    language: str | None
    source_country: str | None
    discovered_via: Literal["gdelt_doc"] = "gdelt_doc"

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CapturePolicy:
    user_agent: str = "MGeoAI-Discovery/0.2"
    timeout_seconds: float = 15.0
    max_html_bytes: int = 2_000_000
    max_robots_bytes: int = 512_000
    max_excerpt_chars: int = 1_200

    def __post_init__(self) -> None:
        if not self.user_agent.strip():
            raise ValueError("a descriptive crawler user agent is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_html_bytes < 1 or self.max_robots_bytes < 1:
            raise ValueError("capture byte limits must be positive")
        if not 100 <= self.max_excerpt_chars <= 10_000:
            raise ValueError("max_excerpt_chars must be between 100 and 10000")


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    url: str
    robots_url: str
    allowed: bool
    status_code: int | None
    checked_at: str
    reason: str
    rules_sha256: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EvidenceSnapshot:
    snapshot_id: str
    country_iso2: str
    canonical_url: str
    title: str | None
    published_at: str | None
    domain: str
    visible_text_excerpt: str
    content_sha256: str
    captured_at: str
    discovery_id: str

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CaptureResult:
    status: Literal["captured", "robots_denied", "rejected", "failed"]
    article: DiscoveredArticle
    robots: RobotsDecision
    snapshot: EvidenceSnapshot | None = None
    quarantine_html_path: str | None = None
    snapshot_path: str | None = None
    error: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        result = asdict(self)
        result["article"] = self.article.to_mapping()
        result["robots"] = self.robots.to_mapping()
        result["snapshot"] = self.snapshot.to_mapping() if self.snapshot else None
        return result


@dataclass(frozen=True, slots=True)
class _HttpPayload:
    status_code: int
    headers: dict[str, str]
    body: bytes
    final_url: str


def load_country_profiles(path: Path = Path("configs/global_countries.toml")) -> dict[str, CountryProfile]:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    rows = raw.get("countries")
    if not isinstance(rows, list):
        raise DiscoveryError("global country configuration must contain [[countries]] rows")
    profiles: dict[str, CountryProfile] = {}
    iso3_codes: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise DiscoveryError("country configuration row must be a table")
        iso2 = str(row.get("iso2", "")).upper()
        iso3 = str(row.get("iso3", "")).upper()
        name = str(row.get("name", "")).strip()
        primary_timezone = str(row.get("primary_timezone", "")).strip()
        centroid = row.get("coverage_centroid")
        languages = tuple(str(item).strip() for item in row.get("languages", []) if str(item))
        query_terms = tuple(
            normalize_text(str(item)) for item in row.get("query_terms", []) if str(item).strip()
        )
        if not re.fullmatch(r"[A-Z]{2}", iso2) or not re.fullmatch(r"[A-Z]{3}", iso3):
            raise DiscoveryError(f"invalid ISO codes for country row {name or iso2 or iso3}")
        if not isinstance(centroid, dict):
            raise DiscoveryError(f"country {iso2} requires a coverage centroid")
        try:
            latitude = float(centroid["latitude"])
            longitude = float(centroid["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DiscoveryError(f"country {iso2} has an invalid coverage centroid") from exc
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise DiscoveryError(f"country {iso2} coverage centroid is outside WGS84 bounds")
        if not name or not primary_timezone or not languages or not query_terms:
            raise DiscoveryError(
                f"country {iso2} requires name, primary timezone, languages, and query terms"
            )
        if iso2 in profiles or iso3 in iso3_codes:
            raise DiscoveryError(f"duplicate country code in global configuration: {iso2}/{iso3}")
        profiles[iso2] = CountryProfile(
            iso2,
            iso3,
            name,
            primary_timezone,
            latitude,
            longitude,
            languages,
            query_terms,
        )
        iso3_codes.add(iso3)
    return profiles


def build_gdelt_query(profile: CountryProfile) -> str:
    terms = []
    for term in profile.query_terms[:20]:
        escaped = term.replace('"', "")
        terms.append(f'"{escaped}"' if " " in escaped else escaped)
    country = re.sub(r"[^A-Za-z]", "", profile.name).casefold()
    return f"({' OR '.join(terms)}) sourcecountry:{country}"


def discover_gdelt(
    profile: CountryProfile,
    *,
    client: httpx.Client,
    max_records: int = 100,
    window_days: int = 30,
    endpoint: str = GDELT_DOC_ENDPOINT,
) -> list[DiscoveredArticle]:
    """Return bounded GDELT metadata; no linked article content is fetched."""
    if not 1 <= max_records <= MAX_GDELT_RECORDS:
        raise ValueError(f"max_records must be between 1 and {MAX_GDELT_RECORDS}")
    if not 1 <= window_days <= MAX_GDELT_WINDOW_DAYS:
        raise ValueError(f"window_days must be between 1 and {MAX_GDELT_WINDOW_DAYS}")
    payload = _bounded_request(
        client,
        endpoint,
        params={
            "query": build_gdelt_query(profile),
            "mode": "artlist",
            "maxrecords": str(max_records),
            "format": "json",
            "timespan": f"{window_days}d",
        },
        user_agent="MGeoAI-Discovery/0.2",
        timeout_seconds=20.0,
        max_bytes=4_000_000,
    )
    if payload.status_code != 200:
        raise DiscoveryError(f"GDELT DOC returned HTTP {payload.status_code}")
    try:
        decoded = json.loads(payload.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryError("GDELT DOC returned invalid JSON") from exc
    raw_articles = decoded.get("articles", []) if isinstance(decoded, dict) else []
    if not isinstance(raw_articles, list):
        raise DiscoveryError("GDELT DOC response has no article list")
    results: list[DiscoveredArticle] = []
    seen_urls: set[str] = set()
    for row in raw_articles[:max_records]:
        if not isinstance(row, dict):
            continue
        try:
            url = canonicalize_url(str(row.get("url", "")))
        except ValueError:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        domain = hostname_for_url(url)
        title = normalize_text(str(row["title"])) if row.get("title") else None
        results.append(
            DiscoveredArticle(
                discovery_id=stable_id("disc", profile.iso2, url),
                country_iso2=profile.iso2,
                url=url,
                title=title,
                domain=domain,
                seen_at=str(row["seendate"]) if row.get("seendate") else None,
                language=str(row["language"]) if row.get("language") else None,
                source_country=str(row["sourcecountry"])
                if row.get("sourcecountry")
                else None,
            )
        )
    return results


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ValueError("only public HTTP(S) URLs without user information are supported")
    _reject_nonpublic_literal_host(parsed.hostname)
    host = parsed.hostname.casefold()
    port = parsed.port
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        if lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS:
            continue
        query.append((key, item))
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.casefold(), host, path, urlencode(sorted(query)), ""))


def hostname_for_url(value: str) -> str:
    host = urlsplit(value).hostname
    if not host:
        raise ValueError("URL has no hostname")
    return host.casefold().removeprefix("www.")


def check_robots(
    url: str,
    *,
    client: httpx.Client,
    policy: CapturePolicy = CapturePolicy(),
    ledger_path: Path | None = None,
) -> RobotsDecision:
    checked_at = _timestamp()
    canonical_url = canonicalize_url(url)
    parsed = urlsplit(canonical_url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    try:
        response = _bounded_request(
            client,
            robots_url,
            user_agent=policy.user_agent,
            timeout_seconds=policy.timeout_seconds,
            max_bytes=policy.max_robots_bytes,
        )
    except (httpx.HTTPError, DiscoveryError) as exc:
        decision = RobotsDecision(
            url=canonical_url,
            robots_url=robots_url,
            allowed=False,
            status_code=None,
            checked_at=checked_at,
            reason=f"robots unavailable: {type(exc).__name__}",
        )
    else:
        if response.status_code in {404, 410}:
            decision = RobotsDecision(
                url=canonical_url,
                robots_url=robots_url,
                allowed=True,
                status_code=response.status_code,
                checked_at=checked_at,
                reason="robots file not found",
            )
        elif response.status_code != 200:
            decision = RobotsDecision(
                url=canonical_url,
                robots_url=robots_url,
                allowed=False,
                status_code=response.status_code,
                checked_at=checked_at,
                reason="robots response was not safely usable",
            )
        else:
            text = response.body.decode("utf-8", errors="replace")
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(text.splitlines())
            allowed = parser.can_fetch(policy.user_agent, canonical_url)
            decision = RobotsDecision(
                url=canonical_url,
                robots_url=robots_url,
                allowed=allowed,
                status_code=200,
                checked_at=checked_at,
                reason="allowed by robots rules" if allowed else "disallowed by robots rules",
                rules_sha256=stable_hash(response.body, 64),
            )
    if ledger_path:
        append_access_ledger(
            ledger_path,
            {
                "at": checked_at,
                "action": "robots_check",
                "url": robots_url,
                "target_url": canonical_url,
                "outcome": "allowed" if decision.allowed else "denied",
                "status_code": decision.status_code,
                "reason": decision.reason,
                "rules_sha256": decision.rules_sha256,
            },
        )
    return decision


def capture_article(
    article: DiscoveredArticle,
    quarantine_dir: Path,
    *,
    client: httpx.Client,
    ledger_path: Path,
    policy: CapturePolicy = CapturePolicy(),
) -> CaptureResult:
    """Capture sanitized HTML and a short mapping-ready evidence snapshot."""
    robots = check_robots(
        article.url, client=client, policy=policy, ledger_path=ledger_path
    )
    if not robots.allowed:
        result = CaptureResult(
            status="robots_denied",
            article=article,
            robots=robots,
            error=robots.reason,
        )
        _record_capture_result(ledger_path, result)
        return result
    try:
        response = _bounded_request(
            client,
            article.url,
            user_agent=policy.user_agent,
            timeout_seconds=policy.timeout_seconds,
            max_bytes=policy.max_html_bytes,
        )
        if response.status_code != 200:
            raise DiscoveryError(f"article returned HTTP {response.status_code}")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise DiscoveryError(f"unsupported article content type: {content_type or 'missing'}")
        final_url = canonicalize_url(response.final_url)
        if hostname_for_url(final_url) != hostname_for_url(article.url):
            raise DiscoveryError("cross-host article redirect was rejected")
        snapshot, sanitized_html = make_evidence_snapshot(
            article,
            response.body,
            final_url=final_url,
            max_excerpt_chars=policy.max_excerpt_chars,
        )
        capture_root = quarantine_dir / article.country_iso2 / snapshot.snapshot_id
        html_path = capture_root / "page.sanitized.html"
        snapshot_path = capture_root / "snapshot.json"
        capture_root.mkdir(parents=True, exist_ok=True)
        html_path.write_text(sanitized_html, encoding="utf-8")
        write_json(snapshot_path, snapshot.to_mapping())
        result = CaptureResult(
            status="captured",
            article=article,
            robots=robots,
            snapshot=snapshot,
            quarantine_html_path=str(html_path),
            snapshot_path=str(snapshot_path),
        )
    except (httpx.HTTPError, DiscoveryError, OSError, ValueError) as exc:
        result = CaptureResult(
            status="rejected" if isinstance(exc, (DiscoveryError, ValueError)) else "failed",
            article=article,
            robots=robots,
            error=str(exc),
        )
    _record_capture_result(ledger_path, result)
    return result


def make_evidence_snapshot(
    article: DiscoveredArticle,
    html: bytes,
    *,
    final_url: str | None = None,
    max_excerpt_chars: int = 1_200,
) -> tuple[EvidenceSnapshot, str]:
    if not 100 <= max_excerpt_chars <= 10_000:
        raise ValueError("max_excerpt_chars must be between 100 and 10000")
    soup = BeautifulSoup(html.decode("utf-8", errors="replace"), "html.parser")
    canonical = _canonical_from_soup(soup, final_url or article.url)
    title = _title_from_soup(soup) or article.title
    published_at = _publication_date_from_soup(soup) or article.seen_at
    for node in list(soup.find_all(REMOVED_ELEMENTS | REMOVED_CONTEXT)):
        node.decompose()
    for tag in soup.find_all(True):
        assert isinstance(tag, Tag)
        allowed: dict[str, Any] = {}
        for attribute in ("datetime", "lang", "dir"):
            if tag.has_attr(attribute):
                allowed[attribute] = tag.attrs[attribute]
        tag.attrs = allowed
    root = soup.find("article") or soup.find("main") or soup.body or soup
    visible_text = normalize_text(root.get_text(" ", strip=True))
    excerpt = _short_excerpt(visible_text, max_excerpt_chars)
    if not excerpt:
        raise DiscoveryError("article contained no visible text after sanitization")
    captured_at = _timestamp()
    content_sha256 = stable_hash(html, 64)
    snapshot = EvidenceSnapshot(
        snapshot_id=stable_id("snap", article.country_iso2, canonical, content_sha256),
        country_iso2=article.country_iso2,
        canonical_url=canonical,
        title=title,
        published_at=published_at,
        domain=hostname_for_url(canonical),
        visible_text_excerpt=excerpt,
        content_sha256=content_sha256,
        captured_at=captured_at,
        discovery_id=article.discovery_id,
    )
    return snapshot, str(soup)


def append_access_ledger(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _bounded_request(
    client: httpx.Client,
    url: str,
    *,
    user_agent: str,
    timeout_seconds: float,
    max_bytes: int,
    params: dict[str, str] | None = None,
) -> _HttpPayload:
    with client.stream(
        "GET",
        url,
        params=params,
        headers={"User-Agent": user_agent, "Accept": "text/html,application/json;q=0.9,*/*;q=0.1"},
        timeout=timeout_seconds,
    ) as response:
        length_header = response.headers.get("content-length")
        if length_header and length_header.isdigit() and int(length_header) > max_bytes:
            raise DiscoveryError(f"response exceeds {max_bytes} byte limit")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise DiscoveryError(f"response exceeds {max_bytes} byte limit")
            chunks.append(chunk)
        return _HttpPayload(
            status_code=response.status_code,
            headers={key.casefold(): value for key, value in response.headers.items()},
            body=b"".join(chunks),
            final_url=str(response.url),
        )


def _canonical_from_soup(soup: BeautifulSoup, fallback: str) -> str:
    node = soup.find("link", rel=lambda value: value and "canonical" in value)
    candidate = None
    if isinstance(node, Tag) and node.get("href"):
        candidate = urljoin(fallback, str(node["href"]))
    if candidate:
        try:
            canonical = canonicalize_url(candidate)
            if hostname_for_url(canonical) == hostname_for_url(fallback):
                return canonical
        except ValueError:
            pass
    return canonicalize_url(fallback)


def _title_from_soup(soup: BeautifulSoup) -> str | None:
    meta = soup.find("meta", attrs={"property": "og:title"})
    if isinstance(meta, Tag) and meta.get("content"):
        return normalize_text(str(meta["content"]))[:500]
    title = soup.find("h1") or soup.find("title")
    return normalize_text(title.get_text(" ", strip=True))[:500] if isinstance(title, Tag) else None


def _publication_date_from_soup(soup: BeautifulSoup) -> str | None:
    selectors: tuple[tuple[str, str | None, str | None, str], ...] = (
        ("meta", "property", "article:published_time", "content"),
        ("meta", "name", "date", "content"),
        ("time", None, None, "datetime"),
    )
    for name, attribute_name, attribute_value, field in selectors:
        attrs: Any = (
            {attribute_name: attribute_value} if attribute_name and attribute_value else None
        )
        node = soup.find(name, attrs=attrs)
        if isinstance(node, Tag) and node.get(field):
            return normalize_text(str(node[field]))[:100]
    return None


def _short_excerpt(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    shortened = value[: limit + 1].rsplit(" ", 1)[0].rstrip()
    return (shortened or value[:limit]).rstrip() + "…"


def _record_capture_result(path: Path, result: CaptureResult) -> None:
    append_access_ledger(
        path,
        {
            "at": _timestamp(),
            "action": "article_capture",
            "url": result.article.url,
            "country_iso2": result.article.country_iso2,
            "domain": result.article.domain,
            "outcome": result.status,
            "snapshot_id": result.snapshot.snapshot_id if result.snapshot else None,
            "content_sha256": result.snapshot.content_sha256 if result.snapshot else None,
            "error": result.error,
        },
    )


def _reject_nonpublic_literal_host(host: str) -> None:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        if host.casefold() in {"localhost", "localhost.localdomain"}:
            raise ValueError("local hosts are not supported") from exc
        return
    if not address.is_global:
        raise ValueError("non-public IP addresses are not supported")


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
