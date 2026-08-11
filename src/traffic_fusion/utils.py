from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_core import to_jsonable_python


def stable_hash(value: str | bytes, length: int = 16) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()[:length]


def stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{stable_hash('|'.join(parts))}"


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u200b", "").replace("\u034f", "")
    return re.sub(r"\s+", " ", value).strip()


def canonical_json(value: Any) -> str:
    return json.dumps(
        to_jsonable_python(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, values: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for value in values:
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        lines.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def utc_now() -> datetime:
    return datetime.now(UTC)
