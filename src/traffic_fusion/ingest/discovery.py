from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from traffic_fusion.config import Settings
from traffic_fusion.utils import stable_id, write_jsonl

SUPPORTED_NAMES = {"content.html", "news_01.html", "image_01.json"}


def _kind(path: Path) -> str | None:
    if path.suffix.lower() == ".html":
        return "html"
    if path.suffix.lower() == ".json" and path.parent.name == "youtube":
        return "video_analysis"
    if path.name == "image_01.json":
        return "image_analysis"
    return None


def discover(input_dir: Path, settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or Settings.load()
    root = input_dir.resolve()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        kind = _kind(path)
        if not kind:
            continue
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        warnings: list[str] = []
        if size > settings.max_file_bytes:
            warnings.append(f"file exceeds configured size limit ({size} bytes)")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        info = path.parent / "SOURCE_INFO.md"
        parent_rel = None
        if kind == "image_analysis":
            html = next(iter(sorted(path.parent.glob("*.html"))), None)
            parent_rel = html.relative_to(root).as_posix() if html else None
        rows.append(
            {
                "manifest_id": stable_id("file", rel, digest),
                "relative_path": rel,
                "absolute_path": str(path),
                "kind": kind,
                "size_bytes": size,
                "sha256": digest,
                "source_info_path": str(info) if info.exists() else None,
                "parent_relative_path": parent_rel,
                "warnings": warnings,
            }
        )
    return rows


def write_manifest(
    input_dir: Path, output: Path, settings: Settings | None = None
) -> list[dict[str, Any]]:
    rows = discover(input_dir, settings)
    write_jsonl(output, rows)
    return rows
