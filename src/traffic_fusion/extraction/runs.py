"""Run LLM extraction over the article set; job state and results live on disk.

One folder per (provider, model, input set, images) configuration:
`extraction/runs/<config_id>/{run.json, <article_id>.json}`. Re-running resumes: articles
with a stored successful result are skipped. Results are never served to annotators.
"""

from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from traffic_fusion.extraction.control import ControlStore
from traffic_fusion.extraction.providers import (
    IMPLEMENTED,
    CallResult,
    ProviderError,
    call_chat,
    image_part,
)
from traffic_fusion.extraction.schema import AccidentRecord, ImageAnalysis
from traffic_fusion.utils import stable_hash

PROMPT_PATH = Path("assets/mllm_prompts/accident_extraction_prompt.md")
MAX_RAW_CHARS = 400_000


class RunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str = Field(min_length=1, max_length=200)
    input_set: str = Field(pattern="^(raw|markdown)$")
    with_images: bool = False
    limit: int | None = Field(default=None, ge=1, le=100000)
    article_ids: list[str] | None = None

    def config_id(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", self.model.lower()).strip("-")[:60]
        return f"{self.provider}__{slug}__{self.input_set}__{'img' if self.with_images else 'txt'}"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def parse_output(text: str) -> tuple[list[AccidentRecord], list[ImageAnalysis]]:
    """Accept the envelope, a bare list, or a single accident object."""
    payload: Any = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()))
    images_raw: list[Any] = []
    if isinstance(payload, dict) and "accidents" in payload:
        images_raw = payload.get("images") or []
        payload = payload["accidents"]
    items = payload if isinstance(payload, list) else [payload]
    accidents = [AccidentRecord.model_validate(item) for item in items]
    images = [ImageAnalysis.model_validate(item) for item in images_raw]
    if not accidents:
        raise ValueError("no accident objects")
    return accidents, images


def check_quotes(accidents: list[AccidentRecord], source_text: str) -> dict[str, int]:
    haystack = _norm(source_text)
    total = valid = 0
    for record in accidents:
        for evidence in record.evidences:
            total += 1
            valid += _norm(evidence.quote) in haystack
    return {"quotes": total, "verbatim": valid}


class RunManager:
    def __init__(self, root: Path, control: ControlStore) -> None:
        self.root = root
        self.control = control
        self.runs_dir = root / "runs"
        self._threads: dict[str, threading.Thread] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    # helpers -----------------------------------------------------------------
    def _articles(self, spec: RunSpec) -> list[str]:
        base = self.root / "articles"
        ids = sorted(p.name for p in base.iterdir() if (p / "meta.json").exists()) if base.is_dir() else []
        if spec.article_ids is not None:
            ids = [i for i in ids if i in set(spec.article_ids)]
        return ids[: spec.limit] if spec.limit else ids

    def _source(self, article_id: str, input_set: str) -> str:
        folder = self.root / "articles" / article_id
        name = "model_raw.html" if input_set == "raw" else "article.md"
        text = (folder / name).read_text("utf-8")
        return text[:MAX_RAW_CHARS]

    def _image_files(self, article_id: str, limit: int) -> list[tuple[str, str, bytes]]:
        folder = self.root / "articles" / article_id
        meta = json.loads((folder / "meta.json").read_text("utf-8"))
        found: list[tuple[str, str, bytes]] = []
        for index, image in enumerate(meta.get("images", []), start=1):
            if image.get("file") and len(found) < limit:
                path = folder / "images" / image["file"]
                if path.exists():
                    found.append((f"{article_id}-{index}", image["content_type"], path.read_bytes()))
        return found

    def estimate(self, spec: RunSpec) -> dict[str, Any]:
        settings = self.control.settings()
        ids = self._articles(spec)
        done = {p.stem for p in (self.runs_dir / spec.config_id()).glob("*.json") if p.name != "run.json"}
        todo = [i for i in ids if i not in done]
        prompt_chars = len(PROMPT_PATH.read_text("utf-8"))
        chars = sum(len(self._source(i, spec.input_set)) + prompt_chars for i in todo)
        images = (
            sum(len(self._image_files(i, settings.max_images_per_article)) for i in todo)
            if spec.with_images else 0
        )
        in_tokens = int(chars / 3.2) + images * 1200  # rough: ~3.2 chars/token, ~1.2k/image
        out_tokens = len(todo) * 500
        price = self.control.price(spec.provider, spec.model)
        cost = (
            (in_tokens * price.input_per_million_usd + out_tokens * price.output_per_million_usd) / 1e6
            if price else None
        )
        return {
            "config_id": spec.config_id(), "articles_total": len(ids), "articles_todo": len(todo),
            "images_to_send": images, "est_input_tokens": in_tokens, "est_output_tokens": out_tokens,
            "est_cost_usd": cost, "cost_known": price is not None,
            "token_limit": settings.run_token_limit,
            "within_token_limit": in_tokens + out_tokens <= settings.run_token_limit,
            "note": "Estimate only: ~3.2 characters per token and ~1,200 tokens per image.",
        }

    def status(self, config_id: str) -> dict[str, Any] | None:
        path = self.runs_dir / config_id / "run.json"
        try:
            return json.loads(path.read_text("utf-8"))  # type: ignore[no-any-return]
        except (OSError, json.JSONDecodeError):
            return None

    def list(self) -> list[dict[str, Any]]:
        if not self.runs_dir.is_dir():
            return []
        rows = [self.status(p.name) for p in sorted(self.runs_dir.iterdir()) if p.is_dir()]
        return [row for row in rows if row]

    def _write_status(self, config_id: str, state: dict[str, Any]) -> None:
        path = self.runs_dir / config_id / "run.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2) + "\n", "utf-8")

    # control -----------------------------------------------------------------
    def start(self, spec: RunSpec) -> dict[str, Any]:
        if spec.provider not in IMPLEMENTED:
            raise ValueError(f"provider {spec.provider!r} is not implemented yet")
        if not self.control.get_key(spec.provider):
            raise ValueError(f"no API key set for {spec.provider}")
        config = self.control.settings().providers[spec.provider]
        if spec.with_images and not config.supports_images:
            raise ValueError("this provider is not marked as accepting images in the control panel")
        config_id = spec.config_id()
        with self._lock:
            thread = self._threads.get(config_id)
            if thread and thread.is_alive():
                raise ValueError("this configuration is already running")
            cancel = threading.Event()
            self._cancel[config_id] = cancel
            state = {
                "config_id": config_id, "spec": spec.model_dump(), "status": "running",
                "started_at": _now(), "finished_at": None, "done": 0, "failed": 0,
                "input_tokens": 0, "output_tokens": 0, "cost_usd": None,
                "cost_known": self.control.price(spec.provider, spec.model) is not None,
                "stop_reason": None,
            }
            self._write_status(config_id, state)
            thread = threading.Thread(target=self._run, args=(spec, state, cancel), daemon=True)
            self._threads[config_id] = thread
            thread.start()
        return state

    def cancel(self, config_id: str) -> bool:
        event = self._cancel.get(config_id)
        if event:
            event.set()
        return event is not None

    def _run(self, spec: RunSpec, state: dict[str, Any], cancel: threading.Event) -> None:
        settings = self.control.settings()
        config = settings.providers[spec.provider]
        price = self.control.price(spec.provider, spec.model)
        system = PROMPT_PATH.read_text("utf-8")
        prompt_hash = stable_hash(system, 16)
        config_dir = self.runs_dir / state["config_id"]
        lock = threading.Lock()
        ids = [i for i in self._articles(spec) if not (config_dir / f"{i}.json").exists()
               or json.loads((config_dir / f"{i}.json").read_text("utf-8")).get("status") != "ok"]

        def one(article_id: str) -> None:
            if cancel.is_set() or state["stop_reason"]:
                return
            with lock:
                if state["input_tokens"] + state["output_tokens"] >= settings.run_token_limit:
                    state["stop_reason"] = "token_limit"
                    return
                if (price and state["cost_usd"] is not None
                        and state["cost_usd"] >= settings.run_cost_limit_usd):
                    state["stop_reason"] = "cost_limit"
                    return
            record: dict[str, Any] = {"article_id": article_id, "spec": spec.model_dump(exclude={"article_ids", "limit"}),
                                      "prompt_hash": prompt_hash, "started_at": _now()}
            try:
                source = self._source(article_id, spec.input_set)
                parts: list[dict[str, Any]] = [{"type": "text", "text": (
                    "<ARTICLE_SOURCE>\n" + source + "\n</ARTICLE_SOURCE>\n"
                    "Extract the road accident(s) as specified.")}]
                sent = []
                if spec.with_images:
                    for image_id, media_type, data in self._image_files(article_id, settings.max_images_per_article):
                        parts += [{"type": "text", "text": f"IMAGE {image_id}"}, image_part(media_type, data)]
                        sent.append(image_id)
                record["images_sent"] = sent
                result: CallResult = call_chat(
                    spec.provider, api_key=self.control.get_key(spec.provider) or "", model=spec.model,
                    system=system, user_parts=parts, base_url=config.base_url,
                    timeout=config.timeout_seconds, max_output_tokens=config.max_output_tokens,
                )
                record.update(raw_text=result.text, input_tokens=result.input_tokens,
                              output_tokens=result.output_tokens, latency_ms=result.latency_ms,
                              finish_reason=result.finish_reason, model_returned=result.model_returned,
                              retries=result.retries, notes=result.notes)
                if result.finish_reason == "length":
                    raise ValueError("response truncated (finish_reason=length)")
                accidents, images = parse_output(result.text)
                visible_text = source if spec.input_set == "markdown" else self._plain(article_id)
                record.update(status="ok", accidents=[a.wire() for a in accidents],
                              images=[i.model_dump() for i in images],
                              quality=check_quotes(accidents, visible_text))
            except (ProviderError, ValueError, ValidationError, json.JSONDecodeError) as exc:
                record.update(status="failed", error=str(exc)[:500],
                              retryable=getattr(exc, "retryable", True))
            record["finished_at"] = _now()
            (config_dir / f"{article_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", "utf-8")
            with lock:
                state["done" if record["status"] == "ok" else "failed"] += 1
                state["input_tokens"] += record.get("input_tokens") or 0
                state["output_tokens"] += record.get("output_tokens") or 0
                if price:
                    state["cost_usd"] = round(
                        (state["input_tokens"] * price.input_per_million_usd
                         + state["output_tokens"] * price.output_per_million_usd) / 1e6, 6)
                self._write_status(state["config_id"], state)

        try:
            with ThreadPoolExecutor(max_workers=settings.concurrency) as pool:
                list(pool.map(one, ids))
        finally:
            state["status"] = "cancelled" if cancel.is_set() else "stopped" if state["stop_reason"] else "finished"
            state["finished_at"] = _now()
            self._write_status(state["config_id"], state)

    def _plain(self, article_id: str) -> str:
        from bs4 import BeautifulSoup

        raw = (self.root / "articles" / article_id / "model_raw.html").read_text("utf-8")
        return BeautifulSoup(raw, "html.parser").get_text(" ")
