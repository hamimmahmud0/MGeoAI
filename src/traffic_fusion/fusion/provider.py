from __future__ import annotations

import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from traffic_fusion.config import Settings
from traffic_fusion.models import (
    FusedFact,
    FusedIncident,
    Geolocation,
    IncidentMention,
    LocationCandidate,
    MatchDecision,
    MatchFeatures,
    ProviderRun,
)
from traffic_fusion.reporting import validate_fused_provenance
from traffic_fusion.utils import canonical_json, stable_hash, stable_id, write_json

T = TypeVar("T", bound=BaseModel)


class ProviderFailure(RuntimeError):
    """Terminal provider failure; callers must not fabricate a successful result."""


class FusionProvider(Protocol):
    name: str
    model: str

    def adjudicate(
        self, left: IncidentMention, right: IncidentMention, features: MatchFeatures
    ) -> MatchDecision: ...
    def fuse(self, cluster_id: str, bundle: dict[str, Any]) -> FusedIncident: ...
    @property
    def runs(self) -> list[ProviderRun]: ...


class MatchOutput(BaseModel):
    decision: str
    confidence: float
    decisive_evidence_ids: list[str] = []
    contradictions: list[str] = []
    rationale: str


class DeepSeekProvider:
    name = "deepseek"

    def __init__(self, settings: Settings, prompt_path: Path, cache_dir: Path):
        errors = settings.validate_live()
        if errors:
            raise ProviderFailure("; ".join(errors))
        self.settings = settings
        self.model = settings.deepseek_model or "unconfigured"
        self.prompt = prompt_path.read_text(encoding="utf-8")
        self.prompt_version = "1.2.0"
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._runs: list[ProviderRun] = []
        self._run_cost_usd = 0.0
        # Models are not hard-coded. Explicit mode selects Responses; auto uses the
        # broadly supported Chat Completions API until capability configuration says otherwise.
        self.endpoint_mode = "responses" if settings.api_mode == "responses" else "chat_completions"

    @property
    def runs(self) -> list[ProviderRun]:
        return self._runs

    def _request(
        self, operation: str, cluster_id: str, payload: dict[str, Any], output_model: type[T]
    ) -> T:
        if self._run_cost_usd >= self.settings.run_cost_limit_usd:
            raise ProviderFailure("per-run cost guardrail reached before provider request")
        schema = output_model.model_json_schema()
        request_material = {
            "bundle": payload,
            "prompt_hash": stable_hash(self.prompt, 64),
            "schema": schema,
            "provider": self.name,
            "model": self.model,
            "mode": self.endpoint_mode,
            "thinking": self.settings.thinking,
        }
        request_hash = stable_hash(canonical_json(request_material), 64)
        cache_path = self.cache_dir / f"{request_hash}.json"
        started = datetime.now(UTC)
        if cache_path.exists():
            parsed = output_model.model_validate_json(cache_path.read_text())
            if not self._provenance_errors(parsed, payload):
                self._runs.append(
                    ProviderRun(
                        run_id=stable_id("prun", request_hash, "cache"),
                        cluster_id=cluster_id,
                        operation=operation,
                        provider=self.name,
                        model=self.model,
                        endpoint_mode=self.endpoint_mode,
                        prompt_version=self.prompt_version,
                        prompt_hash=stable_hash(self.prompt, 64),
                        request_hash=request_hash,
                        started_at=started,
                        latency_ms=0,
                        retries=0,
                        finish_status="cached",
                        validation_status="valid",
                        cache_hit=True,
                    )
                )
                return parsed
        if self.endpoint_mode == "responses":
            url = f"{self.settings.deepseek_base_url.rstrip('/')}/responses"
            body: dict[str, Any] = {
                "model": self.model,
                "instructions": self.prompt,
                "input": canonical_json(payload),
                "max_output_tokens": self.settings.token_budget,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": output_model.__name__,
                        "schema": schema,
                        "strict": True,
                    }
                },
            }
        else:
            url = f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions"
            example = (
                {
                    "decision": "uncertain",
                    "confidence": 0.5,
                    "decisive_evidence_ids": [],
                    "contradictions": [],
                    "rationale": "Evidence is insufficient.",
                }
                if output_model is MatchOutput
                else {
                    "incident_id": "inc_stable_id",
                    "title": "Neutral incident title",
                    "event_type": "road_crash",
                    "source_ids": ["src_supplied"],
                    "evidence_ids": ["ev_supplied"],
                    "human_summary": "Attributed summary [ev_supplied].",
                    "generated_at": "2026-01-01T00:00:00Z",
                }
            )
            body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.prompt},
                    {
                        "role": "user",
                        "content": "Return one JSON object only. Evidence bundle follows:\n<UNTRUSTED_EVIDENCE>\n"
                        + canonical_json(payload)
                        + "\n</UNTRUSTED_EVIDENCE>"
                        + "\n<REQUIRED_JSON_SCHEMA>\n"
                        + canonical_json(schema)
                        + "\n</REQUIRED_JSON_SCHEMA>\nCompact shape example (values are placeholders, not evidence):\n"
                        + canonical_json(example),
                    },
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": self.settings.token_budget,
                "thinking": {"type": self.settings.thinking},
            }
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        last_error = "unknown provider error"
        usage: dict[str, Any] = {}
        for attempt in range(self.settings.retry_count + 1):
            before = time.monotonic()
            try:
                response = httpx.post(
                    url, headers=headers, json=body, timeout=self.settings.request_timeout
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise httpx.HTTPStatusError(
                        f"retryable status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                raw = response.json()
                usage = raw.get("usage", {})
                if self.endpoint_mode == "responses":
                    content = raw.get("output_text")
                    finish = raw.get("status", "unknown")
                else:
                    choices = raw.get("choices") or []
                    if not choices:
                        raise ProviderFailure("empty choices in provider response")
                    message = choices[0].get("message", {})
                    if message.get("refusal"):
                        raise ProviderFailure(f"provider refused request: {message['refusal']}")
                    content = message.get("content")
                    finish = choices[0].get("finish_reason", "unknown")
                    if finish == "length":
                        raise ProviderFailure("provider response truncated by token limit")
                if not content:
                    raise ProviderFailure("empty provider response")
                raw_dir = self.cache_dir.parent / "provider_responses"
                raw_dir.mkdir(parents=True, exist_ok=True)
                write_json(
                    raw_dir / f"{request_hash}.json",
                    {
                        "provider": self.name,
                        "model": self.model,
                        "mode": self.endpoint_mode,
                        "finish_status": finish,
                        "response": content,
                    },
                )
                try:
                    parsed = output_model.model_validate_json(content)
                except ValidationError as exc:
                    last_error = f"schema validation failed: {exc}"
                    if attempt >= self.settings.retry_count:
                        raise ProviderFailure(last_error) from exc
                    repair = f"Repair the JSON. Validation errors: {exc.errors(include_url=False)}"
                    if self.endpoint_mode == "responses":
                        body["input"] = f"{body['input']}\n{repair}"
                    else:
                        body["messages"].append({"role": "assistant", "content": content})
                        body["messages"].append({"role": "user", "content": repair})
                    continue
                provenance_errors = self._provenance_errors(parsed, payload)
                if provenance_errors:
                    last_error = "provenance validation failed: " + "; ".join(
                        provenance_errors
                    )
                    if attempt >= self.settings.retry_count:
                        raise ProviderFailure(last_error)
                    repair = (
                        "Repair the JSON using only source_id and evidence_id values present "
                        f"in the supplied bundle. Validation errors: {provenance_errors}"
                    )
                    if self.endpoint_mode == "responses":
                        body["input"] = f"{body['input']}\n{repair}"
                    else:
                        body["messages"].append({"role": "assistant", "content": content})
                        body["messages"].append({"role": "user", "content": repair})
                    continue
                input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
                output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
                estimated_cost = self._estimate_cost(input_tokens, output_tokens)
                self._run_cost_usd += estimated_cost
                if self._run_cost_usd > self.settings.run_cost_limit_usd:
                    raise ProviderFailure("per-run cost guardrail reached")
                if self._daily_spend() + estimated_cost > self.settings.daily_cost_limit_usd:
                    raise ProviderFailure("daily cost guardrail reached")
                self._record_daily_spend(estimated_cost)
                cache_path.write_text(parsed.model_dump_json(indent=2))
                self._runs.append(
                    ProviderRun(
                        run_id=stable_id("prun", request_hash, str(attempt)),
                        cluster_id=cluster_id,
                        operation=operation,
                        provider=self.name,
                        model=self.model,
                        endpoint_mode=self.endpoint_mode,
                        prompt_version=self.prompt_version,
                        prompt_hash=stable_hash(self.prompt, 64),
                        request_hash=request_hash,
                        started_at=started,
                        latency_ms=int((time.monotonic() - before) * 1000),
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        estimated_cost_usd=estimated_cost,
                        retries=attempt,
                        finish_status=str(finish),
                        validation_status="valid",
                    )
                )
                return parsed
            except (
                httpx.TimeoutException,
                httpx.HTTPStatusError,
                json.JSONDecodeError,
                ProviderFailure,
            ) as exc:
                last_error = str(exc)
                terminal = any(word in str(exc) for word in ("truncated", "guardrail", "refused"))
                if attempt >= self.settings.retry_count or (
                    isinstance(exc, ProviderFailure) and terminal
                ):
                    break
                time.sleep(min(4.0, (2**attempt) + random.random() * 0.25))
        self._runs.append(
            ProviderRun(
                run_id=stable_id("prun", request_hash, "failed"),
                cluster_id=cluster_id,
                operation=operation,
                provider=self.name,
                model=self.model,
                endpoint_mode=self.endpoint_mode,
                prompt_version=self.prompt_version,
                prompt_hash=stable_hash(self.prompt, 64),
                request_hash=request_hash,
                started_at=started,
                latency_ms=int((datetime.now(UTC) - started).total_seconds() * 1000),
                retries=self.settings.retry_count,
                finish_status="failed",
                validation_status="invalid",
                error=last_error,
            )
        )
        raise ProviderFailure(last_error)

    @staticmethod
    def _provenance_errors(parsed: BaseModel, payload: dict[str, Any]) -> list[str]:
        if not isinstance(parsed, FusedIncident):
            return []
        allowed_evidence = {
            str(item["evidence_id"])
            for item in payload.get("evidence", [])
            if isinstance(item, dict) and item.get("evidence_id")
        }
        allowed_sources = {
            str(item["source_id"])
            for item in payload.get("sources", [])
            if isinstance(item, dict) and item.get("source_id")
        }
        return validate_fused_provenance(parsed, allowed_evidence, allowed_sources)

    def _estimate_cost(self, input_tokens: int | None, output_tokens: int | None) -> float:
        input_rate = self.settings.input_cost_per_million_usd or 0
        output_rate = self.settings.output_cost_per_million_usd or 0
        return round(
            ((input_tokens or 0) * input_rate + (output_tokens or 0) * output_rate) / 1_000_000, 8
        )

    def _ledger_path(self) -> Path:
        return self.cache_dir / "cost-ledger.json"

    def _daily_spend(self) -> float:
        path = self._ledger_path()
        if not path.exists():
            return 0.0
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return 0.0
        return float(data.get(datetime.now(UTC).date().isoformat(), 0))

    def _record_daily_spend(self, cost: float) -> None:
        path = self._ledger_path()
        try:
            data = json.loads(path.read_text()) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            data = {}
        day = datetime.now(UTC).date().isoformat()
        data[day] = round(float(data.get(day, 0)) + cost, 8)
        write_json(path, data)

    def adjudicate(
        self, left: IncidentMention, right: IncidentMention, features: MatchFeatures
    ) -> MatchDecision:
        output = self._request(
            "match",
            f"{left.mention_id}:{right.mention_id}",
            {
                "task": "same_incident_adjudication",
                "left": left.model_dump(mode="json"),
                "right": right.model_dump(mode="json"),
                "deterministic_features": features.model_dump(mode="json"),
                "allowed_decisions": [
                    "same_incident",
                    "related_but_distinct",
                    "different_incident",
                    "uncertain",
                ],
            },
            MatchOutput,
        )
        if output.decision not in {
            "same_incident",
            "related_but_distinct",
            "different_incident",
            "uncertain",
        }:
            raise ProviderFailure(f"unsupported match decision: {output.decision}")
        return MatchDecision(
            left_mention_id=left.mention_id,
            right_mention_id=right.mention_id,
            decision=output.decision,
            confidence=output.confidence,
            decisive_evidence_ids=output.decisive_evidence_ids,
            contradictions=output.contradictions,
            rationale=output.rationale,
            features=features,
            provider_run_id=self._runs[-1].run_id,
        )

    def fuse(self, cluster_id: str, bundle: dict[str, Any]) -> FusedIncident:
        incident = self._request(
            "fusion", cluster_id, {"task": "cluster_fusion", **bundle}, FusedIncident
        )
        return self._reconcile_fusion(incident, bundle)

    @staticmethod
    def _reconcile_fusion(incident: FusedIncident, bundle: dict[str, Any]) -> FusedIncident:
        """Enforce stable semantic fields that must not depend on model wording."""
        candidates = [
            LocationCandidate.model_validate(location)
            for mention in bundle.get("mentions", [])
            if isinstance(mention, dict)
            for location in mention.get("locations", [])
            if isinstance(location, dict)
        ]
        located = [
            candidate
            for candidate in candidates
            if candidate.latitude is not None and candidate.longitude is not None
        ]
        if located:
            output_name = (incident.geolocation.display_name or "").casefold()

            def candidate_rank(candidate: LocationCandidate) -> tuple[int, float]:
                tokens = {
                    token
                    for token in candidate.normalized_name.replace(",", " ").split()
                    if len(token) > 3
                }
                overlap = sum(token in output_name for token in tokens)
                return overlap, candidate.confidence

            selected = max(located, key=candidate_rank)
            incident.geolocation = Geolocation.model_validate(
                {
                    **incident.geolocation.model_dump(mode="python"),
                    "display_name": selected.name,
                    "hierarchy": selected.hierarchy,
                    "latitude": selected.latitude,
                    "longitude": selected.longitude,
                    "granularity": selected.granularity,
                    "method": "source-named local gazetteer centroid",
                    "supporting_evidence_ids": selected.evidence_ids,
                    "confidence": min(incident.geolocation.confidence, selected.confidence),
                    "ambiguity_reason": selected.reason,
                    "uncertainty_radius_km": None,
                }
            )
        elif incident.geolocation.latitude is not None:
            incident.geolocation = Geolocation(
                display_name=incident.geolocation.display_name,
                granularity="unknown",
                method="unresolved; model coordinate discarded because no supplied candidate exists",
                confidence=0,
                ambiguity_reason="No source-grounded coordinate candidate was supplied.",
            )

        facts_by_field = {fact.field: fact for fact in incident.facts}
        evidence = [item for item in bundle.get("evidence", []) if isinstance(item, dict)]
        for field_name in ("fatalities", "injuries"):
            if field_name in facts_by_field:
                continue
            counts = {
                mention.get("casualties", {}).get(field_name)
                for mention in bundle.get("mentions", [])
                if isinstance(mention, dict)
                and isinstance(mention.get("casualties"), dict)
                and mention["casualties"].get(field_name) is not None
            }
            if len(counts) != 1:
                continue
            count = counts.pop()
            support_ids = sorted(
                {
                    str(item["evidence_id"])
                    for item in evidence
                    if item.get("evidence_id")
                    and isinstance(item.get("casualty_quantities"), dict)
                    and item["casualty_quantities"].get(field_name) == count
                }
            )
            incident.facts.append(
                FusedFact(
                    field=field_name,
                    value=count,
                    state="reported_zero" if count == 0 else "known",
                    support_evidence_ids=support_ids,
                    confidence=0.8,
                    selection_rationale=(
                        "Deterministic fallback from unanimous normalized source mentions; "
                        "the live provider omitted the canonical field."
                    ),
                )
            )
        return incident

    def persist_runs(self, path: Path) -> None:
        write_json(path, [run.model_dump(mode="json") for run in self._runs])
