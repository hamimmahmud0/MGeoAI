"""Run LLM extraction over the article set; job state and results live on disk.

One folder per (provider, model, input set, images) configuration:
`extraction/runs/<config_id>/{run.json, <article_id>.json}`. Re-running resumes: articles
with a stored successful result are skipped. Results are never served to annotators.
"""

from __future__ import annotations

import json
import os
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
REASONING_OUTPUT_TOKENS = 262_144  # no practical cap: the model's whole context window


class RunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str = Field(min_length=1, max_length=200)
    input_set: str = Field(pattern="^(raw|markdown)$")
    with_images: bool = False
    limit: int | None = Field(default=None, ge=1, le=100000)
    # Give the model the page's publication date (meta.json) on its own labelled line, outside
    # the article text. Part of the run name so runs with and without it never mix.
    with_meta: bool = False
    only_failed: bool = False  # retry just the articles whose stored result is a failure
    # None = the provider's own default (run names unchanged). True / False = switch the model's reasoning
    # ("thinking") on / off explicitly, for deepseek and custom endpoints. Part of the run name, so the two
    # modes never overwrite each other. Reasoning tokens count against the output cap, so for custom endpoints
    # the cap is raised to REASONING_OUTPUT_TOKENS when it is on.
    reasoning: bool | None = None
    article_ids: list[str] | None = None

    def config_id(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", self.model.lower()).strip("-")[:60]
        base = f"{self.provider}__{slug}__{self.input_set}__{'img' if self.with_images else 'txt'}"
        base = f"{base}__meta" if self.with_meta else base
        if self.reasoning is None:
            return base
        return f"{base}__think" if self.reasoning else f"{base}__nothink"


def _pid_alive(pid: Any) -> bool:
    """True if a process with this pid exists (a run started from the CLI has no thread here)."""
    if not isinstance(pid, int) or pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def page_metadata_block(published_at: object) -> str:
    """The labelled metadata line. Empty when the page has no known publication date."""
    if not published_at:
        return ""
    return (
        "<PAGE_METADATA>\n"
        f"published: {published_at}\n"
        "</PAGE_METADATA>\n"
        "PAGE_METADATA is the publication time of the page, taken from the page or the search "
        "record. It may be missing or wrong and is not part of the article. Use it only as the "
        "reference point for relative dates such as \"on Friday\" or \"last night\". It is not "
        "the accident date unless the article says so.\n"
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


KNOWN_KEYS = {"accident", "casualities", "fatalities", "vehicles", "date", "country", "location",
              "longitude and latitude", "evidences"}


def parse_output(text: str, ignored: list[dict[str, Any]] | None = None
                 ) -> tuple[list[AccidentRecord], list[ImageAnalysis]]:
    """Accept the envelope, a bare list, or a single accident object.

    Unknown extra keys on an accident object (models sometimes add a `note` or `date_note`)
    are dropped and reported through `ignored`; wrong values still fail validation.
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)  # reasoning leaked into the reply
    payload: Any = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()))
    images_raw: list[Any] = []
    if isinstance(payload, dict) and "accidents" in payload:
        images_raw = payload.get("images") or []
        payload = payload["accidents"]
    items = payload if isinstance(payload, list) else [payload]
    cleaned = []
    for item in items:
        if isinstance(item, dict):
            extra = {k: v for k, v in item.items() if k not in KNOWN_KEYS}
            if extra and ignored is not None:
                ignored.append(extra)
            item = {k: v for k, v in item.items() if k in KNOWN_KEYS}
        cleaned.append(item)
    accidents = [AccidentRecord.model_validate(item) for item in cleaned]
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

    def _status_of(self, config_id: str, article_id: str) -> str | None:
        path = self.runs_dir / config_id / f"{article_id}.json"
        try:
            return str(json.loads(path.read_text("utf-8")).get("status"))
        except (OSError, json.JSONDecodeError):
            return None

    def _pending(self, spec: RunSpec) -> list[str]:
        """Articles still to do: no result yet, or a failed one. only_failed skips unseen."""
        config_id = spec.config_id()
        todo = []
        for article_id in self._articles(spec):
            status = self._status_of(config_id, article_id)
            if status == "failed" or (status is None and not spec.only_failed):
                todo.append(article_id)
        return todo

    def _published_at(self, article_id: str) -> object:
        meta = json.loads((self.root / "articles" / article_id / "meta.json").read_text("utf-8"))
        return meta.get("published_at")

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
        todo = self._pending(spec)
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
        """Run state with cumulative totals derived from the per-article results.

        `attempt` keeps the counters of the latest start (a retry resets those only).
        """
        path = self.runs_dir / config_id / "run.json"
        try:
            state: dict[str, Any] = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        thread = self._threads.get(config_id)
        if state.get("status") == "running" and not (thread and thread.is_alive()) \
                and not _pid_alive(state.get("pid")):
            # No live worker (service restart or crash): never show it as running.
            state["status"] = "interrupted"
        state["attempt"] = {
            key: state.get(key) for key in ("done", "failed", "input_tokens", "output_tokens")
        }
        done = failed = tokens_in = tokens_out = 0
        for result in path.parent.glob("*.json"):
            if result.name == "run.json":
                continue
            try:
                row = json.loads(result.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            done += row.get("status") == "ok"
            failed += row.get("status") == "failed"
            tokens_in += row.get("input_tokens") or 0
            tokens_out += row.get("output_tokens") or 0
        spec = state.get("spec") or {}
        price = self.control.price(str(spec.get("provider")), str(spec.get("model")))
        state.update(done=done, failed=failed, input_tokens=tokens_in, output_tokens=tokens_out)
        state["cost_usd"] = (
            round((tokens_in * price.input_per_million_usd
                   + tokens_out * price.output_per_million_usd) / 1e6, 6)
            if price else None
        )
        return state

    def list(self) -> list[dict[str, Any]]:
        if not self.runs_dir.is_dir():
            return []
        rows = [
            self.status(p.name)
            for p in sorted(self.runs_dir.iterdir())
            if p.is_dir() and not p.name.startswith("_")
        ]
        return [row for row in rows if row]

    def archive(self, config_id: str) -> Path:
        """Clear a run from the list and from all scores. Results are moved, not deleted,
        to `runs/_archived/<timestamp>__<config_id>/` so they can be restored by hand."""
        if not re.fullmatch(r"[a-z0-9_-]+", config_id):
            raise ValueError("invalid run id")
        source = self.runs_dir / config_id
        if not source.is_dir():
            raise ValueError("run not found")
        thread = self._threads.get(config_id)
        if thread and thread.is_alive():
            raise ValueError("cancel the run before clearing it")
        target = self.runs_dir / "_archived" / f"{datetime.now(UTC):%Y%m%dT%H%M%S}__{config_id}"
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        return target

    def _write_status(self, config_id: str, state: dict[str, Any]) -> None:
        path = self.runs_dir / config_id / "run.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2) + "\n", "utf-8")

    # control -----------------------------------------------------------------
    def start(self, spec: RunSpec, concurrency: int | None = None) -> dict[str, Any]:
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
                "stop_reason": None, "pid": os.getpid(),
            }
            self._write_status(config_id, state)
            thread = threading.Thread(target=self._run, args=(spec, state, cancel, concurrency), daemon=True)
            self._threads[config_id] = thread
            thread.start()
        return state

    def cancel(self, config_id: str) -> bool:
        event = self._cancel.get(config_id)
        if event:
            event.set()
        return event is not None

    def _run(self, spec: RunSpec, state: dict[str, Any], cancel: threading.Event,
             concurrency: int | None = None) -> None:
        settings = self.control.settings()
        config = settings.providers[spec.provider]
        price = self.control.price(spec.provider, spec.model)
        extra_body = dict(config.extra_body)
        max_output = config.max_output_tokens
        thinking = config.thinking
        if spec.reasoning is not None:
            thinking = "default" if spec.reasoning else "disabled"
            if spec.provider == "custom":
                extra_body = {"chat_template_kwargs": {"enable_thinking": spec.reasoning}}
                if spec.reasoning:
                    max_output = max(max_output, REASONING_OUTPUT_TOKENS)
        system = PROMPT_PATH.read_text("utf-8")
        prompt_hash = stable_hash(system, 16)
        config_dir = self.runs_dir / state["config_id"]
        lock = threading.Lock()
        ids = self._pending(spec)

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
            record: dict[str, Any] = {"article_id": article_id,
                                      "call_settings": {"thinking": thinking if spec.provider == "deepseek" else
                                                                   ("on" if spec.reasoning else "off") if spec.provider == "custom" and spec.reasoning is not None else None,
                                                        "max_output_tokens": max_output}, "spec": spec.model_dump(exclude={"article_ids", "limit"}),
                                      "prompt_hash": prompt_hash, "started_at": _now()}
            try:
                source = self._source(article_id, spec.input_set)
                meta_block = (page_metadata_block(self._published_at(article_id))
                              if spec.with_meta else "")
                parts: list[dict[str, Any]] = [{"type": "text", "text": (
                    meta_block + "<ARTICLE_SOURCE>\n" + source + "\n</ARTICLE_SOURCE>\n"
                    "Extract the road accident(s) as specified.")}]
                sent = []
                if spec.with_images:
                    for image_id, media_type, data in self._image_files(article_id, settings.max_images_per_article):
                        parts += [{"type": "text", "text": f"IMAGE {image_id}"},
                                  image_part(media_type, data, config.max_image_side)]
                        sent.append(image_id)
                record["images_sent"] = sent
                result: CallResult = call_chat(
                    spec.provider, api_key=self.control.get_key(spec.provider) or "", model=spec.model,
                    system=system, user_parts=parts,
                    base_url=config.base_url or (os.getenv("CUSTOM_BASE_URL", "")
                                                 if spec.provider == "custom" else ""),
                    timeout=config.timeout_seconds, max_output_tokens=max_output,
                    thinking=thinking, extra_body=extra_body or None,
                )
                record.update(raw_text=result.text, input_tokens=result.input_tokens,
                              output_tokens=result.output_tokens, latency_ms=result.latency_ms,
                              finish_reason=result.finish_reason, model_returned=result.model_returned,
                              retries=result.retries, notes=result.notes)
                if result.finish_reason == "length":
                    hint = ("no answer text: the output budget was likely used up by hidden reasoning"
                            if not result.text.strip() else "answer cut off")
                    raise ValueError(
                        f"response truncated (finish_reason=length, {result.output_tokens} output "
                        f"tokens, {hint}); raise 'max output tokens' or turn thinking off")
                ignored: list[dict[str, Any]] = []
                accidents, images = parse_output(result.text, ignored)
                if ignored:
                    record["ignored_extra_keys"] = ignored
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
            with ThreadPoolExecutor(max_workers=concurrency or settings.concurrency) as pool:
                list(pool.map(one, ids))
        finally:
            state["status"] = "cancelled" if cancel.is_set() else "stopped" if state["stop_reason"] else "finished"
            state["finished_at"] = _now()
            self._write_status(state["config_id"], state)

    def _plain(self, article_id: str) -> str:
        from bs4 import BeautifulSoup

        raw = (self.root / "articles" / article_id / "model_raw.html").read_text("utf-8")
        return BeautifulSoup(raw, "html.parser").get_text(" ")
