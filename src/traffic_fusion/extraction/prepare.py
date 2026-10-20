"""Turn a saved news page into the two LLM input sets and annotator-visible text.

Everything is deterministic parsing. Scripts are never executed and the page is
treated as untrusted data.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString, PageElement

_DROP = ["script", "style", "svg", "noscript", "template", "iframe", "form", "button"]
_CHROME = ["nav", "header", "footer", "aside"]
_BLOCK = {"p", "div", "section", "article", "main", "li", "blockquote", "figure", "figcaption"}
_MAX_IMAGES = 12


def _soup(raw: bytes) -> BeautifulSoup:
    return BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")


def _clean(soup: BeautifulSoup, *, drop_chrome: bool) -> None:
    for node in soup(_DROP):
        node.decompose()
    if drop_chrome:
        for node in soup(_CHROME):
            node.decompose()


def _inline(node: PageElement) -> str:
    if not isinstance(node, (Tag, NavigableString)):
        return ""
    if isinstance(node, NavigableString):
        return re.sub(r"\s+", " ", str(node))
    inner = "".join(_inline(child) for child in node.children)
    if node.name in {"strong", "b"} and inner.strip():
        return f"**{inner.strip()}**"
    if node.name in {"em", "i"} and inner.strip():
        return f"*{inner.strip()}*"
    if node.name == "br":
        return "\n"
    if node.name == "img":
        alt = str(node.get("alt") or "").strip()
        return f"[image: {alt}]" if alt else "[image]"
    return inner


def _walk(node: Tag, out: list[str]) -> None:
    for child in node.children:
        if not isinstance(child, Tag):
            continue
        name = child.name
        if re.fullmatch(r"h[1-6]", name):
            text = _inline(child).strip()
            if text:
                out.append("#" * int(name[1]) + " " + text)
        elif name == "li":
            text = _inline(child).strip()
            if text:
                out.append(f"- {text}")
        elif name == "p" or name == "figcaption" or name == "blockquote":
            text = _inline(child).strip()
            if text:
                out.append(text)
        elif name in _BLOCK or name in {"ul", "ol", "table", "tbody", "tr", "td", "span", "a"}:
            if child.find(re.compile(r"^(p|h[1-6]|li|div|figcaption)$")) is not None:
                _walk(child, out)
            else:
                text = _inline(child).strip()
                if text:
                    out.append(text)
        else:
            _walk(child, out)


def html_to_markdown(raw: bytes) -> str:
    """Cleaned markdown: no scripts, navigation, headers, footers or sidebars."""
    soup = _soup(raw)
    _clean(soup, drop_chrome=True)
    title = soup.find("title")
    root = soup.find("article") or soup.find("main") or soup.body or soup
    lines: list[str] = []
    if title and title.get_text(strip=True):
        lines.append("Page title: " + re.sub(r"\s+", " ", title.get_text(strip=True)))
    _walk(root, lines)
    seen: set[str] = set()
    deduped = []
    for line in lines:
        if line in seen and len(line) < 200:
            continue
        seen.add(line)
        deduped.append(line)
    return "\n\n".join(deduped).strip() + "\n"


def raw_for_model(raw: bytes) -> str:
    """Raw-HTML input set: scripts/styles/svg removed so context is not wasted on code.

    Navigation, sidebars and related-news lists are kept on purpose; the prompt
    must ignore them. Never executes anything.
    """
    soup = _soup(raw)
    for node in soup(["script", "style", "svg", "noscript", "template"]):
        node.decompose()
    return str(soup)


def page_metadata(raw: bytes) -> dict[str, Any]:
    soup = _soup(raw)

    def meta(*names: str) -> str | None:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find(
                "meta", attrs={"name": name}
            )
            if isinstance(tag, Tag) and tag.get("content"):
                return str(tag["content"]).strip()
        return None

    h1 = soup.find("h1")
    title_tag = soup.find("title")
    return {
        "title": (
            meta("og:title")
            or (h1.get_text(" ", strip=True) if h1 else None)
            or (title_tag.get_text(" ", strip=True) if title_tag else None)
        ),
        "description": meta("og:description", "description"),
        "published_time": meta("article:published_time", "og:article:published_time"),
        "canonical_url": meta("og:url"),
        "language": (soup.html.get("lang") if soup.html else None),
    }


def image_candidates(raw: bytes, base_url: str | None) -> list[dict[str, str]]:
    """og:image plus <img> inside the article container, absolute URLs, de-duplicated."""
    soup = _soup(raw)
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(src: str | None, source: str, alt: str = "") -> None:
        if not src or src.startswith("data:"):
            return
        url = urljoin(base_url or "", src.strip())
        if urlparse(url).scheme not in {"http", "https"} or url in seen:
            return
        seen.add(url)
        found.append({"url": url, "source": source, "alt": alt.strip()[:300]})

    og = soup.find("meta", attrs={"property": "og:image"})
    if isinstance(og, Tag):
        add(str(og.get("content") or ""), "og:image")
    _clean(soup, drop_chrome=True)
    root = soup.find("article") or soup.find("main") or soup.body or soup
    for img in root.find_all("img"):
        width = str(img.get("width") or "")
        if width.isdigit() and int(width) < 80:
            continue
        add(str(img.get("src") or img.get("data-src") or ""), "article", str(img.get("alt") or ""))
    return found[:_MAX_IMAGES]
