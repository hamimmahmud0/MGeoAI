"""Build annotation pairs from candidate batches and fetched pages.

Output is the input of `mgeoai annotate import-items`: annotator-visible fields
(item_id, left, right) plus admin-only metadata (category, agent claim, ...).
"""
from __future__ import annotations

import glob
import hashlib
import html as htmllib
import itertools
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

MIN_TEXT = 300
MAX_TEXT = 6000
CRASH = re.compile(
    r"\b(?:crash|collision|collided|accident|killed|died|dead|injured|plunge[ds]?|overturn\w*|flipped|vehicle|bus|truck)\b"
    r"|দুর্ঘটনা|নিহত|সংঘর্ষ|আহত|ধাক্কা|মৃত|প্রাণ",
    re.I,
)
CONTACT = re.compile(r"\[email\s*protected\]|ফোন\s*:|ফ্যাক্স|\+\d{2,3}[-\s]?\d")
NOISE = re.compile(
    r"^(advertisement|share|follow us|read more|related|copyright|subscribe|sign up|"
    r"tap here|keep updated|also read|click here)",
    re.I,
)


def _plain(text: str) -> str:
    """Unescape embedded HTML (some sites ship escaped markup) and keep paragraph breaks."""
    if "&lt;" in text or "<p>" in text:
        text = htmllib.unescape(text)
        text = BeautifulSoup(text.replace("</p>", "</p>\n\n"), "html.parser").get_text()
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:MAX_TEXT]


def extract_text(html: bytes) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "aside", "form", "header"]):
        if tag.name == "script" and tag.get("type") == "application/ld+json":
            continue
        tag.decompose()
    for script in BeautifulSoup(html, "html.parser").find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        for node in data if isinstance(data, list) else [data]:
            body = node.get("articleBody") if isinstance(node, dict) else None
            if isinstance(body, str) and len(body) >= MIN_TEXT:
                return _plain(body)
    container = (
        soup.find(attrs={"itemprop": "articleBody"}) or soup.find("article") or soup.find("main")
        or soup.body or soup
    )
    seen: set[str] = set()
    parts = []
    for p in container.find_all("p"):
        text = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        if len(text) < 40 or NOISE.match(text) or CONTACT.search(text) or text in seen:
            continue
        seen.add(text)
        parts.append(text)
    return _plain("\n\n".join(parts))


def short_id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("|".join(parts).encode()).hexdigest()[:10]


def main(scraps: str, pages: str, out: str, seed: int = 20260101) -> None:
    rng = random.Random(seed)
    manifest = {r["url"]: r for r in map(json.loads, open(f"{pages}/manifest.jsonl"))}
    groups: dict[str, dict[str, Any]] = {}
    dropped: list[dict[str, str]] = []
    for path in sorted(glob.glob(f"{scraps}/candidates_b*.json")):
        for group in json.load(open(path))["groups"]:
            kept = []
            for art in group["articles"]:
                rec = manifest.get(art["url"])
                if not rec or not rec.get("file"):
                    dropped.append({"url": art["url"], "reason": f"fetch:{rec['status'] if rec else 'not_allowed'}"})
                    continue
                text = extract_text(Path(pages, rec["file"]).read_bytes())
                if len(text) < MIN_TEXT:
                    dropped.append({"url": art["url"], "reason": f"short_text:{len(text)}"})
                    continue
                if not CRASH.search(text):
                    dropped.append({"url": art["url"], "reason": "off_topic_text"})
                    continue
                kept.append({
                    "id": short_id("a_", art["url"]),
                    "title": art["title"],
                    "publisher": art["publisher"],
                    "url": art["url"],
                    "published_at": art.get("published_date"),
                    "text": text,
                    "_lang": art["language"],
                })
            groups[group["group_id"]] = {**group, "kept": kept}
    items: list[dict[str, Any]] = []

    def add(left: dict[str, Any], right: dict[str, Any], **meta: Any) -> None:
        pair = sorted([left, right], key=lambda a: a["id"])
        if rng.random() < 0.5:
            pair.reverse()
        strip = lambda a: {k: v for k, v in a.items() if not k.startswith("_")}  # noqa: E731
        items.append({
            "item_id": short_id("p_", pair[0]["id"], pair[1]["id"]),
            "left": strip(pair[0]), "right": strip(pair[1]), **meta,
        })

    usable_same = {g: v for g, v in groups.items() if v["kind"] == "same_incident" and len(v["kept"]) >= 2}
    for gid, g in sorted(usable_same.items()):
        pairs = list(itertools.combinations(g["kept"], 2))
        rng.shuffle(pairs)
        # Keep a random spanning tree so every article is covered by a human-labelled pair.
        parent = {a["id"]: a["id"] for a in g["kept"]}

        def find(x: str, parent: dict[str, str] = parent) -> str:
            while parent[x] != x:
                x = parent[x]
            return x

        chosen = []
        for a, b in pairs:
            if find(a["id"]) != find(b["id"]):
                parent[find(a["id"])] = find(b["id"])
                chosen.append((a, b))
        if len(g["kept"]) <= 3:
            chosen = pairs  # complete graph already has at most 3 pairs
        for a, b in chosen:
            add(a, b, category="positive", group=gid, region=g["region"], country=g["country"],
                agent_claim="same_incident", agent_difficulty=g["difficulty"],
                confusable_by=g.get("confusable_by", []),
                cross_language=a["_lang"] != b["_lang"])
    for gid, g in sorted(groups.items()):
        if g["kind"] != "decoy_cluster" or g.get("decoy_for") not in usable_same:
            continue
        target = usable_same[g["decoy_for"]]
        for art in g["kept"]:
            for other in rng.sample(target["kept"], min(2, len(target["kept"]))):
                add(art, other, category="hard_negative", group=gid, decoy_for=g["decoy_for"],
                    region=g["region"], country=g["country"], agent_claim="different_incident",
                    agent_difficulty=g["difficulty"], confusable_by=g.get("confusable_by", []),
                    cross_language=art["_lang"] != other["_lang"])
    # Easy negatives: unrelated incidents from the same region, for calibration.
    ids = sorted(usable_same)
    made = 0
    while made < 30:
        a, b = rng.sample(ids, 2)
        if usable_same[a]["region"] != usable_same[b]["region"]:
            continue
        made += 1
        add(rng.choice(usable_same[a]["kept"]), rng.choice(usable_same[b]["kept"]),
            category="easy_negative", group=f"{a}|{b}", region=usable_same[a]["region"],
            agent_claim="different_incident", agent_difficulty="easy", confusable_by=[])
    unique = {it["item_id"]: it for it in items}
    rng.shuffle(list(unique.values()))
    json.dump(list(unique.values()), open(out, "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("items", len(unique), Counter(i["category"] for i in unique.values()))
    print("usable same_incident groups", len(usable_same), "of",
          sum(v["kind"] == "same_incident" for v in groups.values()))
    print("dropped articles", len(dropped), Counter(d["reason"].split(":")[0] for d in dropped))
    json.dump(dropped, open(Path(out).with_name("dropped_articles.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
