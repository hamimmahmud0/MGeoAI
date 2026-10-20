"""Control-panel state: persisted non-secret settings plus in-memory API keys.

API keys entered in the UI live only in this process's memory. They are never written
to disk, logged, or returned by any endpoint (AGENTS.md: do not persist API keys). After a
restart, keys come from the environment again or must be re-entered.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PROVIDERS: tuple[str, ...] = ("openai", "anthropic", "openrouter", "deepseek")
KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(default="", max_length=200)
    base_url: str = Field(default="", max_length=300)
    input_cost_per_million_usd: float | None = Field(default=None, ge=0, le=10000)
    output_cost_per_million_usd: float | None = Field(default=None, ge=0, le=10000)
    timeout_seconds: int = Field(default=120, ge=5, le=900)
    max_output_tokens: int = Field(default=4000, ge=256, le=64000)
    supports_images: bool = False


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_per_million_usd: float = Field(ge=0, le=10000)
    output_per_million_usd: float = Field(ge=0, le=10000)


class ControlSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    labelling_open: bool = True
    # Manually imported prices keyed "provider/model". A model without a price (and not
    # a ":free" id) runs with cost = unknown; limits then apply to tokens only.
    pricing: dict[str, ModelPrice] = Field(default_factory=dict)
    run_token_limit: int = Field(default=2_000_000, ge=1000, le=500_000_000)
    max_images_per_article: int = Field(default=3, ge=0, le=6)
    run_cost_limit_usd: float = Field(default=5.0, ge=0, le=1000)
    daily_cost_limit_usd: float = Field(default=20.0, ge=0, le=10000)
    concurrency: int = Field(default=2, ge=1, le=8)
    providers: dict[str, ProviderConfig] = Field(
        default_factory=lambda: {name: ProviderConfig() for name in PROVIDERS}
    )


class ControlStore:
    def __init__(self, root: Path) -> None:
        self.path = root / "control.json"
        self._lock = threading.Lock()
        self._secrets: dict[str, str] = {}

    def settings(self) -> ControlSettings:
        try:
            value = ControlSettings.model_validate(json.loads(self.path.read_text("utf-8")))
        except (OSError, json.JSONDecodeError, ValueError):
            value = ControlSettings()
        for name in PROVIDERS:
            value.providers.setdefault(name, ProviderConfig())
        return value

    def price(self, provider: str, model: str) -> ModelPrice | None:
        """Known price for a model, $0 for OpenRouter ':free' ids, else None (unknown)."""
        settings = self.settings()
        manual = settings.pricing.get(f"{provider}/{model}")
        if manual:
            return manual
        config = settings.providers.get(provider)
        if (
            config
            and config.model == model
            and config.input_cost_per_million_usd is not None
            and config.output_cost_per_million_usd is not None
        ):
            return ModelPrice(
                input_per_million_usd=config.input_cost_per_million_usd,
                output_per_million_usd=config.output_cost_per_million_usd,
            )
        if provider == "openrouter" and model.endswith(":free"):
            return ModelPrice(input_per_million_usd=0, output_per_million_usd=0)
        return None

    def save(self, value: ControlSettings) -> ControlSettings:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(value.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return value

    # secrets ---------------------------------------------------------------
    def set_key(self, provider: str, key: str | None) -> None:
        if provider not in PROVIDERS:
            raise ValueError("unknown provider")
        with self._lock:
            if key:
                self._secrets[provider] = key
            else:
                self._secrets.pop(provider, None)

    def get_key(self, provider: str) -> str | None:
        return self._secrets.get(provider) or os.getenv(KEY_ENV.get(provider, ""))

    def key_status(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "configured": bool(self.get_key(name)),
                "source": "ui_memory"
                if name in self._secrets
                else "environment"
                if os.getenv(KEY_ENV[name])
                else "none",
            }
            for name in PROVIDERS
        }
