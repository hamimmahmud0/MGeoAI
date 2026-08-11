from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Settings:
    provider: str = "deepseek"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str | None = None
    api_mode: str = "auto"
    thinking: str = "disabled"
    request_timeout: float = 45.0
    retry_count: int = 2
    concurrency: int = 2
    token_budget: int = 6000
    run_cost_limit_usd: float = 5.0
    daily_cost_limit_usd: float = 20.0
    input_cost_per_million_usd: float | None = None
    output_cost_per_million_usd: float | None = None
    match_threshold: float = 0.72
    possible_match_threshold: float = 0.45
    max_days_apart: int = 3
    max_file_bytes: int = 5_000_000
    redact_comment_authors: bool = False
    map_style_url: str = "https://tiles.openfreemap.org/styles/liberty"
    must_link: list[list[str]] = field(default_factory=list)
    cannot_link: list[list[str]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        config_path = (
            os.getenv("MGEOAI_CONFIG")
            or os.getenv("TRAFFIC_FUSION_CONFIG")
            or "configs/default.toml"
        )
        path = path or Path(config_path)
        raw: dict[str, Any] = {}
        if path.exists():
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        fusion = raw.get("fusion", {})
        matching = raw.get("matching", {})
        limits = raw.get("limits", {})
        privacy = raw.get("privacy", {})
        map_config = raw.get("map", {})
        overrides = raw.get("overrides", {})
        redact_authors = (
            os.getenv("MGEOAI_REDACT_AUTHORS")
            or os.getenv("TRAFFIC_FUSION_REDACT_AUTHORS")
            or str(privacy.get("redact_comment_authors", False))
        )
        return cls(
            provider=os.getenv("FUSION_PROVIDER", fusion.get("provider", "deepseek")),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL") or None,
            api_mode=os.getenv("DEEPSEEK_API_MODE", "auto"),
            thinking=os.getenv("DEEPSEEK_THINKING", "disabled"),
            request_timeout=float(
                os.getenv("FUSION_REQUEST_TIMEOUT", fusion.get("request_timeout", 45))
            ),
            retry_count=int(os.getenv("FUSION_RETRY_COUNT", fusion.get("retry_count", 2))),
            concurrency=int(os.getenv("FUSION_CONCURRENCY", fusion.get("concurrency", 2))),
            token_budget=int(os.getenv("FUSION_TOKEN_BUDGET", fusion.get("token_budget", 6000))),
            run_cost_limit_usd=float(
                os.getenv("FUSION_RUN_COST_LIMIT_USD", fusion.get("run_cost_limit_usd", 5))
            ),
            daily_cost_limit_usd=float(
                os.getenv("FUSION_DAILY_COST_LIMIT_USD", fusion.get("daily_cost_limit_usd", 20))
            ),
            input_cost_per_million_usd=float(os.environ["DEEPSEEK_INPUT_COST_PER_MILLION_USD"])
            if os.getenv("DEEPSEEK_INPUT_COST_PER_MILLION_USD")
            else None,
            output_cost_per_million_usd=float(os.environ["DEEPSEEK_OUTPUT_COST_PER_MILLION_USD"])
            if os.getenv("DEEPSEEK_OUTPUT_COST_PER_MILLION_USD")
            else None,
            match_threshold=float(matching.get("match_threshold", 0.72)),
            possible_match_threshold=float(matching.get("possible_match_threshold", 0.45)),
            max_days_apart=int(matching.get("max_days_apart", 3)),
            max_file_bytes=int(limits.get("max_file_bytes", 5_000_000)),
            redact_comment_authors=redact_authors.lower() == "true",
            map_style_url=os.getenv(
                "MAP_STYLE_URL",
                map_config.get("style_url", "https://tiles.openfreemap.org/styles/liberty"),
            ),
            must_link=overrides.get("must_link", []),
            cannot_link=overrides.get("cannot_link", []),
        )

    def validate_live(self) -> list[str]:
        errors: list[str] = []
        if self.provider == "deepseek":
            if not self.deepseek_api_key:
                errors.append("DEEPSEEK_API_KEY is required for live mode")
            if not self.deepseek_model:
                errors.append("DEEPSEEK_MODEL is required for live mode")
        if self.api_mode not in {"auto", "responses", "chat_completions"}:
            errors.append("DEEPSEEK_API_MODE must be auto, responses, or chat_completions")
        if self.thinking not in {"enabled", "disabled"}:
            errors.append("DEEPSEEK_THINKING must be enabled or disabled")
        if self.run_cost_limit_usd > 0 and (
            self.input_cost_per_million_usd is None or self.output_cost_per_million_usd is None
        ):
            errors.append(
                "current DeepSeek input/output prices are required for enabled cost guardrails"
            )
        return errors
