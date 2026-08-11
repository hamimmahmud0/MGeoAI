from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser

from traffic_fusion.models import ParsedBlock, ProvenanceLocator, SourceRecord, SourceType
from traffic_fusion.utils import normalize_text, stable_hash, stable_id, write_json

NOISE_EXACT = {
    "facebook",
    "share",
    "share now",
    "advertisement",
    "print",
    "copy",
    "highlights",
    "privacy",
    "terms",
    "see more",
    "log in",
    "sign up",
    "follow us",
    "all reactions:",
    "keep updated, follow the business standard's google news channel",
    "tap here to add the daily star as a trusted source",
}
NOISE_PREFIXES = (
    "copyright ",
    "related topic",
    "recommended for you",
    "more from",
    "read more",
    "privacy and legal",
    "connect with us",
    "download the app",
)
DATE_RE = re.compile(
    r"(?:publish(?:ed)?|updated|last modified)?\s*:?\s*(\d{1,2}\s+[A-Za-z]+,?\s+20\d{2}(?:,?\s+\d{1,2}:\d{2}\s*(?:am|pm)?)?)",
    re.I,
)
TRAFFIC_TEXT_RE = re.compile(
    r"\b(?:accident|crash|collision|killed|injured|road|highway|traffic|blockade|congestion|vehicle|motorcycle|bus|truck)\b|সড়ক|দুর্ঘটনা|নিহত|আহত|মহাসড়ক|যানজট|অবরোধ",
    re.I,
)


@dataclass(slots=True)
class ParsedHtml:
    source: SourceRecord
    blocks: list[ParsedBlock]


def _source_info(path: Path | None) -> tuple[str | None, str | None, dict[str, str]]:
    if not path or not path.exists():
        return None, None, {}
    text = path.read_text(encoding="utf-8", errors="replace")
    uri_match = re.search(r"(?:news link:\s*)?(https?://\S+)", text, re.I)
    uri = uri_match.group(1).rstrip(" )") if uri_match else None
    page_match = re.search(r"Page name:\s*`?([^`\n]+)", text, re.I)
    source_match = re.search(r"Source name:\s*([^\n]+)", text, re.I)
    publisher = page_match.group(1).strip() if page_match else None
    if not publisher and source_match:
        publisher = source_match.group(1).strip()
    if not publisher and uri:
        publisher = urlparse(uri).netloc.removeprefix("www.")
    return uri, publisher, {"source_info_path": str(path), "source_info_hash": stable_hash(text)}


def _clean_candidate(text: str) -> str | None:
    text = normalize_text(text)
    if not text or len(text) < 2:
        return None
    low = text.casefold()
    if low in NOISE_EXACT or any(low.startswith(prefix) for prefix in NOISE_PREFIXES):
        return None
    # Facebook's accessibility DOM contains obfuscated single-character runs.
    if (
        len(text) > 20
        and sum(len(token) == 1 for token in text.split()) / max(len(text.split()), 1) > 0.55
    ):
        return None
    return text


def _selector(tag: Tag) -> str:
    parts: list[str] = []
    node: Tag | None = tag
    while node is not None and node.name not in {"html", "[document]"} and len(parts) < 5:
        if node.get("id"):
            parts.append(f"{node.name}#{node.get('id')}")
            break
        sibling_index = 1
        sibling = node.previous_sibling
        while sibling:
            if isinstance(sibling, Tag) and sibling.name == node.name:
                sibling_index += 1
            sibling = sibling.previous_sibling
        parts.append(f"{node.name}:nth-of-type({sibling_index})")
        node = node.parent if isinstance(node.parent, Tag) else None
    return " > ".join(reversed(parts))


def _candidate_tags(soup: BeautifulSoup) -> Iterable[tuple[Tag, str]]:
    seen: set[str] = set()
    selectors = "h1,h2,h3,article p,main p,[role='article'] div[dir='auto'],p,figcaption,time"
    for tag in soup.select(selectors):
        # Only leaf-ish divs; otherwise Facebook creates huge repeated parent text.
        if tag.name == "div" and tag.find(["div", "p"], recursive=False):
            continue
        text = _clean_candidate(tag.get_text(" ", strip=True))
        if not text or text in seen:
            continue
        seen.add(text)
        yield tag, text
    # Saved Facebook accessibility DOMs often wrap a useful post in nested spans
    # rather than paragraphs. Add leaf text nodes without accepting their noisy
    # ancestor containers.
    for string in soup.find_all(string=True):
        parent = string.parent
        if not isinstance(parent, Tag) or parent.name in {"script", "style", "svg", "noscript"}:
            continue
        text = _clean_candidate(str(string))
        if not text or len(text) < 45 or not TRAFFIC_TEXT_RE.search(text) or text in seen:
            continue
        seen.add(text)
        yield parent, text


def _guess_kind(tag: Tag, text: str, index: int) -> str:
    if tag.name in {"h1", "h2"} and index < 4:
        return "headline"
    if tag.name == "figcaption":
        return "caption"
    if tag.name == "time" or DATE_RE.search(text):
        return "published_time"
    aria = str(tag.get("aria-label", "")).casefold()
    if "comment" in aria:
        return "comment"
    return "article"


def _parse_date(blocks: list[ParsedBlock]) -> datetime | None:
    for block in blocks[:15]:
        match = DATE_RE.search(block.text)
        if match:
            try:
                return date_parser.parse(match.group(1), fuzzy=True)
            except (ValueError, OverflowError):
                pass
    return None


def parse_html(path: Path, relative_path: str, source_info_path: Path | None = None) -> ParsedHtml:
    raw = path.read_bytes()
    content_hash = stable_hash(raw, 64)
    source_id = stable_id("src", relative_path, content_hash)
    text = raw.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    for node in soup(["script", "style", "svg", "noscript", "template"]):
        node.decompose()
    uri, publisher, metadata = _source_info(source_info_path)
    title_tag = soup.find("h1") or soup.find("title")
    title = _clean_candidate(title_tag.get_text(" ", strip=True)) if title_tag else None
    is_facebook = (
        "facebook" in (soup.title.string.casefold() if soup.title and soup.title.string else "")
        or "Facebook" in text[:5000]
    )
    blocks: list[ParsedBlock] = []
    warnings: list[str] = []
    for index, (tag, candidate) in enumerate(_candidate_tags(soup), start=1):
        kind = _guess_kind(tag, candidate, index)
        block_id = stable_id("blk", source_id, kind, candidate)
        blocks.append(
            ParsedBlock(
                block_id=block_id,
                source_id=source_id,
                kind="post" if is_facebook and kind == "article" and index < 12 else kind,
                text=candidate,
                locator=ProvenanceLocator(
                    source_path=relative_path,
                    locator_type="html_selector",
                    locator=_selector(tag),
                    block_id=block_id,
                    original_text=candidate,
                ),
            )
        )
    if not blocks:
        warnings.append("No model-readable content blocks extracted")
    if title is None and blocks:
        title = blocks[0].text[:240]
    source = SourceRecord(
        source_id=source_id,
        source_type=SourceType.FACEBOOK_HTML if is_facebook else SourceType.NEWS_HTML,
        platform="Facebook" if is_facebook else "web",
        publisher=publisher,
        source_uri=uri,
        local_path=relative_path,
        content_hash=content_hash,
        published_at=_parse_date(blocks),
        timezone="Asia/Dhaka" if _parse_date(blocks) else None,
        languages=["bn", "en"],
        title=title,
        source_metadata=metadata,
        ingest_warnings=warnings,
        independence="repost" if is_facebook else "unknown",
        dependency_group=publisher.casefold() if publisher else None,
    )
    return ParsedHtml(source=source, blocks=blocks)


def render_markdown(parsed: ParsedHtml) -> str:
    source = parsed.source
    front = [
        "---",
        f"source_id: {source.source_id}",
        f"schema_version: {source.schema_version}",
        f"source_type: {source.source_type.value}",
        f"publisher: {source.publisher or 'unknown'}",
        f"source_uri: {source.source_uri or 'unknown'}",
        f"published_at: {source.published_at.isoformat() if source.published_at else 'unknown'}",
        "---",
        "",
        f"# {source.title or 'Untitled source'}",
        "",
    ]
    sections = [
        ("Article or Post", {"article", "post"}),
        ("Captions", {"caption"}),
        ("Comments", {"comment"}),
    ]
    for heading, kinds in sections:
        selected = [block for block in parsed.blocks if block.kind in kinds]
        if not selected:
            continue
        front.extend([f"## {heading}", ""])
        for block in selected:
            front.extend([f"<!-- block:{block.block_id} -->", block.text, ""])
    return "\n".join(front).rstrip() + "\n"


def write_parsed_html(parsed: ParsedHtml, output_dir: Path) -> None:
    target = output_dir / "sources" / parsed.source.source_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "content.md").write_text(render_markdown(parsed), encoding="utf-8")
    write_json(target / "source.json", parsed.source)
    write_json(target / "blocks.json", [block.model_dump(mode="json") for block in parsed.blocks])
