from __future__ import annotations

import json
from pathlib import Path

from traffic_fusion.adapters import adapt_image, adapt_video
from traffic_fusion.ingest.discovery import discover
from traffic_fusion.ingest.html import parse_html, render_markdown


def test_manifest_is_hash_idempotent(tmp_path: Path) -> None:
    (tmp_path / "youtube").mkdir()
    (tmp_path / "youtube" / "video_01.json").write_text("{}")
    first = discover(tmp_path)
    second = discover(tmp_path)
    assert first == second
    assert first[0]["sha256"] == "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"


def test_html_conversion_removes_script_and_retains_provenance(tmp_path: Path) -> None:
    html = tmp_path / "content.html"
    html.write_text("""<html><head><title>Crash report</title><script>alert('x')</script></head><body>
    <nav>Privacy</nav><article><h1>Tongi crash</h1><p>One student was killed in a road accident.</p>
    <div aria-label="Comment by Sam">We need safer roads now.</div></article></body></html>""")
    parsed = parse_html(html, "content.html")
    markdown = render_markdown(parsed)
    assert "alert('x')" not in markdown
    assert "One student was killed" in markdown
    assert all(block.locator.locator for block in parsed.blocks)
    assert "<!-- block:blk_" in markdown


def test_facebook_leaf_text_is_not_lost(tmp_path: Path) -> None:
    html = tmp_path / "content.html"
    html.write_text(
        "<title>Facebook</title><div><span>Students blocked the highway after a road accident caused severe traffic congestion for travellers.</span></div>"
    )
    parsed = parse_html(html, "content.html")
    assert any("severe traffic congestion" in block.text for block in parsed.blocks)


def test_video_adapter_preserves_claim_path(tmp_path: Path) -> None:
    path = tmp_path / "video.json"
    path.write_text(
        json.dumps(
            {
                "source": {"platform_or_publisher": "Fixture TV", "source_languages": ["Bengali"]},
                "claims": [
                    {
                        "claim": "Police reported one fatality.",
                        "evidence_type": "reported",
                        "confidence_in_extraction": "high",
                        "novel": 7,
                    }
                ],
            }
        )
    )
    source, items = adapt_video(path, "youtube/video.json")
    assert source.publisher == "Fixture TV"
    assert items[0].provenance.locator == "$.claims[0]"
    assert items[0].extensions["raw_fields"]["novel"] == 7


def test_image_adapter_keeps_observation_distinct_from_inference(tmp_path: Path) -> None:
    path = tmp_path / "image.json"
    path.write_text(
        json.dumps(
            {
                "source_type": "image",
                "observations": [
                    {
                        "observation": "A damaged bus is visible.",
                        "observation_type": "direct_visual_observation",
                        "confidence": "high",
                    }
                ],
                "inferences": [{"inference": "The bus may have crashed.", "confidence": "low"}],
            }
        )
    )
    _, items = adapt_image(path, "html/01/image.json", "src_parent")
    assert items[0].assertion_type == "observed"
    assert items[1].assertion_type == "inferred"
    assert items[0].provenance.locator != items[1].provenance.locator
