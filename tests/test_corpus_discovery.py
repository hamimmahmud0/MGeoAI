from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from traffic_fusion.corpus.discovery import (
    CapturePolicy,
    CountryProfile,
    DiscoveredArticle,
    canonicalize_url,
    capture_article,
    discover_gdelt,
    load_country_profiles,
)


def article(url: str = "https://news.example/story") -> DiscoveredArticle:
    return DiscoveredArticle(
        discovery_id="disc_test",
        country_iso2="BD",
        url=url,
        title="Discovered title",
        domain="news.example",
        seen_at="20260812T120000Z",
        language="English",
        source_country="Bangladesh",
    )


def test_global_country_config_has_51_unique_profiles() -> None:
    profiles = load_country_profiles(Path("configs/global_countries.toml"))

    assert len(profiles) == 51
    assert len({profile.iso3 for profile in profiles.values()}) == 51
    assert profiles["BD"].languages == ("bn", "en")
    assert "সড়ক দুর্ঘটনা" in profiles["BD"].query_terms
    assert profiles["BD"].primary_timezone == "Asia/Dhaka"
    assert profiles["BD"].coverage_latitude == 23.685
    assert profiles["BD"].coverage_longitude == 90.3563
    coverage = profiles["BD"].to_coverage_feature()
    assert coverage["geometry"]["coordinates"] == [90.3563, 23.685]
    assert coverage["properties"]["is_incident_location"] is False
    assert coverage["properties"]["geometry_role"] == "collection_country_coverage_centroid"


def test_gdelt_discovery_is_bounded_deduplicated_and_metadata_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/doc/doc"
        assert request.url.params["maxrecords"] == "2"
        assert request.url.params["timespan"] == "7d"
        assert "sourcecountry:bangladesh" in request.url.params["query"]
        return httpx.Response(
            200,
            json={
                "articles": [
                    {
                        "url": "https://news.example/a?utm_source=test",
                        "title": "Road crash reported",
                        "domain": "news.example",
                        "seendate": "20260812T120000Z",
                        "language": "English",
                        "sourcecountry": "Bangladesh",
                        "socialimage": "https://news.example/image.jpg",
                    },
                    {
                        "url": "https://news.example/a",
                        "title": "duplicate",
                    },
                ]
            },
        )

    profile = CountryProfile(
        iso2="BD",
        iso3="BGD",
        name="Bangladesh",
        primary_timezone="Asia/Dhaka",
        coverage_latitude=23.685,
        coverage_longitude=90.3563,
        languages=("bn", "en"),
        query_terms=("সড়ক দুর্ঘটনা", "road accident"),
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        found = discover_gdelt(profile, client=client, max_records=2, window_days=7)

    assert len(found) == 1
    assert found[0].url == "https://news.example/a"
    assert found[0].title == "Road crash reported"
    assert "socialimage" not in found[0].to_mapping()
    with pytest.raises(ValueError, match="max_records"):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            discover_gdelt(profile, client=client, max_records=251)


def test_capture_obeys_robots_and_writes_sanitized_snapshot(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /story\n")
        assert request.url.path == "/story"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="""
                <html><head>
                <title>Fallback title</title>
                <meta property="og:title" content="Bus collision in Chandpur">
                <meta property="article:published_time" content="2026-08-12T10:00:00+06:00">
                <link rel="canonical" href="https://news.example/story?utm_source=feed">
                <script>stealSecrets()</script><style>.hidden{}</style>
                </head><body><nav>Unrelated navigation</nav><article>
                <h1>Bus collision in Chandpur</h1>
                <p>A bus and truck collided on the regional highway. Two people were injured.</p>
                <img src="https://tracker.example/pixel.jpg" onerror="bad()">
                </article></body></html>
            """,
        )

    ledger = tmp_path / "access.jsonl"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = capture_article(
            article(),
            tmp_path / "quarantine",
            client=client,
            ledger_path=ledger,
            policy=CapturePolicy(max_excerpt_chars=180),
        )

    assert result.status == "captured"
    assert calls == ["/robots.txt", "/story"]
    assert result.snapshot is not None
    assert result.snapshot.canonical_url == "https://news.example/story"
    assert result.snapshot.title == "Bus collision in Chandpur"
    assert result.snapshot.published_at == "2026-08-12T10:00:00+06:00"
    assert "Two people were injured" in result.snapshot.visible_text_excerpt
    sanitized = Path(result.quarantine_html_path or "").read_text()
    assert "<script" not in sanitized
    assert "<style" not in sanitized
    assert "<img" not in sanitized
    assert "tracker.example" not in sanitized
    snapshot = json.loads(Path(result.snapshot_path or "").read_text())
    assert snapshot["domain"] == "news.example"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert [row["action"] for row in rows] == ["robots_check", "article_capture"]
    assert rows[-1]["outcome"] == "captured"


def test_robots_denial_prevents_article_fetch(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        return httpx.Response(200, text="User-agent: *\nDisallow: /blocked\n")

    target = article("https://news.example/blocked/report")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = capture_article(
            target,
            tmp_path / "quarantine",
            client=client,
            ledger_path=tmp_path / "access.jsonl",
        )

    assert result.status == "robots_denied"
    assert result.snapshot is None
    assert not (tmp_path / "quarantine").exists()


def test_capture_rejects_oversized_or_non_html_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": "501"},
            content=b"ignored",
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = capture_article(
            article(),
            tmp_path / "quarantine",
            client=client,
            ledger_path=tmp_path / "access.jsonl",
            policy=CapturePolicy(max_html_bytes=500),
        )

    assert result.status == "rejected"
    assert result.error and "byte limit" in result.error


def test_url_canonicalization_removes_tracking_and_rejects_private_hosts() -> None:
    assert (
        canonicalize_url("HTTPS://News.Example/a?b=2&utm_source=x&a=1#fragment")
        == "https://news.example/a?a=1&b=2"
    )
    with pytest.raises(ValueError, match="non-public"):
        canonicalize_url("http://127.0.0.1/private")
