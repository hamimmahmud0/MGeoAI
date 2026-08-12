from __future__ import annotations

import hashlib
import json
import re
import time
import tomllib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import httpx


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "social_candidates.jsonl"
SUMMARY = ROOT / "summary.json"
ACCESS_LEDGER = ROOT / "access_ledger.jsonl"
APPVIEW = "https://api.bsky.app"
SEARCH_PATH = "/xrpc/app.bsky.feed.searchPosts"
USER_AGENT = "MGeoAI-SocialResearch/0.1 (+public-metadata-only)"
MAX_EXCERPT = 280
MAX_PER_COUNTRY = 3

ALIASES = {
    "US": ("United States", "U.S.", "USA"),
    "GB": ("United Kingdom", "UK", "Britain"),
    "AE": ("United Arab Emirates", "UAE", "Dubai", "Abu Dhabi"),
    "SA": ("Saudi Arabia", "Saudi"),
    "KR": ("South Korea", "Korea"),
    "NZ": ("New Zealand",),
    "ZA": ("South Africa",),
    "LK": ("Sri Lanka",),
    "PH": ("Philippines",),
}
VEHICLE = re.compile(
    r"\b(bus|car|cars|truck|trucks|lorry|van|vehicle|vehicles|motorcycle|motorbike|coach|taxi|suv|pedestrian)\b",
    re.IGNORECASE,
)
INCIDENT = re.compile(
    r"\b(crash|crashes|crashed|collision|collides|collided|accident|overturns|overturned|plunges|plunged|rammed|struck|hit-and-run)\b",
    re.IGNORECASE,
)
CONSEQUENCE = re.compile(
    r"\b(killed|dead|dies|died|death|fatal|injured|injuries|hospital|hurt|missing|closed|blocked|delays?)\b",
    re.IGNORECASE,
)
EXCLUDE = re.compile(
    r"\b(video game|film review|movie review|road safety report|annual statistics|insurance advice|crash course|plane crash|air crash|helicopter crash)\b",
    re.IGNORECASE,
)


def append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_profiles() -> list[dict[str, object]]:
    with Path("configs/global_countries.toml").open("rb") as handle:
        rows = tomllib.load(handle)["countries"]
    return rows


def compact(value: str, limit: int = MAX_EXCERPT) -> str:
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[: limit + 1].rsplit(" ", 1)[0].rstrip() + "…"


def has_country(text: str, aliases: tuple[str, ...]) -> bool:
    folded = text.casefold()
    return any(re.search(rf"(?<!\w){re.escape(alias.casefold())}(?!\w)", folded) for alias in aliases)


def incident_candidate(text: str, aliases: tuple[str, ...]) -> bool:
    return bool(
        has_country(text, aliases)
        and VEHICLE.search(text)
        and INCIDENT.search(text)
        and CONSEQUENCE.search(text)
        and not EXCLUDE.search(text)
    )


def external_link(post: dict[str, object]) -> str | None:
    embed = post.get("embed")
    if not isinstance(embed, dict):
        return None
    external = embed.get("external")
    if not isinstance(external, dict):
        return None
    uri = external.get("uri")
    return str(uri) if isinstance(uri, str) and uri.startswith(("http://", "https://")) else None


def post_url(post: dict[str, object]) -> tuple[str, str] | None:
    uri = post.get("uri")
    author = post.get("author")
    if not isinstance(uri, str) or not isinstance(author, dict):
        return None
    parts = uri.split("/")
    if len(parts) < 5:
        return None
    did = str(author.get("did", ""))
    handle = str(author.get("handle", ""))
    rkey = parts[-1]
    if not did.startswith("did:") or not rkey:
        return None
    return f"https://bsky.app/profile/{did}/post/{rkey}", handle


def query_country(
    client: httpx.Client,
    *,
    iso2: str,
    country_name: str,
    aliases: tuple[str, ...],
) -> list[dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    queries = (f'"{country_name}" "bus crash"', f'"{country_name}" "road accident"')
    for query in queries:
        params = {"q": query, "limit": "75", "sort": "latest"}
        discovery_url = f"{APPVIEW}{SEARCH_PATH}?{urlencode(params)}"
        checked_at = datetime.now(UTC).isoformat()
        try:
            response = client.get(f"{APPVIEW}{SEARCH_PATH}", params=params, timeout=20)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            append_jsonl(
                ACCESS_LEDGER,
                {
                    "checked_at": checked_at,
                    "platform": "bluesky",
                    "country_iso2": iso2,
                    "discovery_url": discovery_url,
                    "access_result": "failed",
                    "detail": type(exc).__name__,
                },
            )
            continue
        posts = payload.get("posts", []) if isinstance(payload, dict) else []
        append_jsonl(
            ACCESS_LEDGER,
            {
                "checked_at": checked_at,
                "platform": "bluesky",
                "country_iso2": iso2,
                "discovery_url": discovery_url,
                "access_result": "accessible_public_api",
                "http_status": response.status_code,
                "result_count": len(posts),
            },
        )
        for post in posts:
            if not isinstance(post, dict):
                continue
            record = post.get("record")
            text = str(record.get("text", "")) if isinstance(record, dict) else ""
            direct = post_url(post)
            if not direct or not incident_candidate(text, aliases):
                continue
            url, handle = direct
            excerpt = compact(text)
            if not excerpt:
                continue
            found.setdefault(
                url,
                {
                    "candidate_id": "social_" + hashlib.sha256(url.encode()).hexdigest()[:16],
                    "platform": "bluesky",
                    "country_iso2": iso2,
                    "country_name": country_name,
                    "direct_verification_url": url,
                    "author_handle": handle,
                    "published_at": (
                        record.get("createdAt") if isinstance(record, dict) else post.get("indexedAt")
                    ),
                    "short_metadata_excerpt": excerpt,
                    "external_link_in_post": external_link(post),
                    "discovered_at": checked_at,
                    "discovered_via": "bluesky_public_appview_search",
                    "discovery_url": discovery_url,
                    "access_result": "accessible_public_api",
                    "country_assignment": "text_explicit_country_mention",
                    "assignment_confidence": 0.8,
                    "review_status": "requires_human_incident_and_location_review",
                    "uncertainty_note": (
                        "Country name appears in public post text, but social metadata alone does "
                        "not verify the event, exact location, authorship, or independence."
                    ),
                    "media_downloaded": False,
                    "full_post_body_stored": False,
                },
            )
        time.sleep(0.3)
    return list(found.values())[:MAX_PER_COUNTRY]


def main() -> None:
    existing = []
    if OUTPUT.exists():
        existing = [json.loads(line) for line in OUTPUT.read_text(encoding="utf-8").splitlines() if line]
    existing_urls = {row["direct_verification_url"] for row in existing}
    completed = {row["country_iso2"] for row in existing}
    rows = list(existing)
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for profile in load_profiles():
            iso2 = str(profile["iso2"])
            name = str(profile["name"])
            if iso2 in completed:
                continue
            aliases = ALIASES.get(iso2, (name,))
            candidates = query_country(
                client,
                iso2=iso2,
                country_name=name,
                aliases=aliases,
            )
            for candidate in candidates:
                if candidate["direct_verification_url"] in existing_urls:
                    continue
                append_jsonl(OUTPUT, candidate)
                rows.append(candidate)
                existing_urls.add(candidate["direct_verification_url"])
    country_counts = Counter(str(row["country_iso2"]) for row in rows)
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "candidate_count": len(rows),
        "country_count": len(country_counts),
        "country_counts": dict(sorted(country_counts.items())),
        "target_country_count": 10,
        "target_met": len(country_counts) >= 10,
        "platforms": ["bluesky"],
        "collection_surface": f"{APPVIEW}{SEARCH_PATH}",
        "collection_policy": [
            "Unauthenticated public AppView metadata only.",
            "No media downloads, login bypass, profile crawling, replies, or full thread capture.",
            "Post text is reduced to a short metadata excerpt and URLs are removed from excerpts.",
            "Every candidate requires human event, location, credibility, and independence review.",
        ],
        "blockers": (
            []
            if len(country_counts) >= 10
            else [f"Only {len(country_counts)} countries produced responsibly assignable results."]
        ),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
