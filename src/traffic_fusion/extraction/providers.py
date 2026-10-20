"""Chat-completions providers for article extraction (DeepSeek, OpenRouter).

Request shapes follow each vendor's current docs (checked 2026-10-20):
- DeepSeek: POST {base}/chat/completions, models `deepseek-flash` (accepts images as
  `image_url` parts with http(s) or base64 data URLs) and `deepseek-v4-pro`.
- OpenRouter: POST /api/v1/chat/completions, `image_url` parts (URL or base64), free
  variants use the `:free` suffix and are rate limited (HTTP 429 → retry with backoff).
OpenAI and Anthropic are registered but intentionally not implemented yet.
A failure is raised, never replaced by another provider.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_BASE = {
    "deepseek": "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
}
IMPLEMENTED = tuple(DEFAULT_BASE)


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class CallResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    finish_reason: str | None
    model_returned: str | None
    retries: int = 0
    notes: list[str] = field(default_factory=list)


def image_part(media_type: str, data: bytes) -> dict[str, Any]:
    encoded = base64.b64encode(data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}}


def call_chat(
    provider: str,
    *,
    api_key: str,
    model: str,
    system: str,
    user_parts: list[dict[str, Any]],
    base_url: str = "",
    timeout: int = 120,
    max_output_tokens: int = 4000,
    max_retries: int = 2,
    json_mode: bool = True,
) -> CallResult:
    if provider not in DEFAULT_BASE:
        raise ProviderError(f"provider {provider!r} is not implemented yet", retryable=False)
    if not model:
        raise ProviderError("no model configured", retryable=False)
    url = (base_url or DEFAULT_BASE[provider]).rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_parts},
        ],
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "stream": False,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    notes: list[str] = []
    started = time.monotonic()
    retries = 0
    while True:
        try:
            response = httpx.post(url, json=body, headers=headers, timeout=timeout)
        except httpx.TimeoutException as exc:
            error: ProviderError = ProviderError(f"timeout after {timeout}s: {type(exc).__name__}")
        except httpx.HTTPError as exc:
            error = ProviderError(f"network error: {type(exc).__name__}")
        else:
            if response.status_code == 200:
                return _parse(response, started, retries, notes)
            detail = _error_detail(response)
            if response.status_code == 400 and "response_format" in body:
                # Parameter-level fallback on the SAME model; recorded, not silent.
                del body["response_format"]
                notes.append("json response_format rejected by endpoint; retried without it")
                continue
            error = ProviderError(
                f"HTTP {response.status_code}: {detail}",
                retryable=response.status_code in {408, 409, 429} or response.status_code >= 500,
            )
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                time.sleep(min(int(retry_after), 30))
        if not error.retryable or retries >= max_retries:
            raise error
        retries += 1
        time.sleep(min(2.0**retries, 8.0))


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        error = payload.get("error", payload)
        message = error.get("message") if isinstance(error, dict) else str(error)
        return str(message)[:300]
    except ValueError:
        return response.text[:200]


def _parse(response: httpx.Response, started: float, retries: int, notes: list[str]) -> CallResult:
    try:
        data = response.json()
        choice = data["choices"][0]
        text = choice["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ProviderError("malformed provider response", retryable=True) from exc
    usage = data.get("usage") or {}
    return CallResult(
        text=text,
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        latency_ms=int((time.monotonic() - started) * 1000),
        finish_reason=choice.get("finish_reason"),
        model_returned=data.get("model"),
        retries=retries,
        notes=notes,
    )
