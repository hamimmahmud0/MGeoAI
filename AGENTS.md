# Repository guide

## Purpose

MGeoAI turns saved traffic-news HTML and existing multimodal analysis
JSON into attributed, provenance-preserving incident records and a map-first
operations dashboard. It fuses evidence; it does not verify truth or fault.

## Layout

- `src/traffic_fusion/`: Python models, ingestion, normalization, matching,
  provider adapters, fusion, reporting, pipeline, CLI, and FastAPI.
- `web/`: React/TypeScript/Vite/Tailwind/MapLibre dashboard.
- `assets/`: supplied immutable sample corpus and versioned runtime prompts.
- `configs/default.toml`: checked-in non-secret defaults.
- `schemas/`: exported Pydantic JSON Schemas.
- `tests/`: small fixtures and offline backend/provider/API tests.
- `outputs/`: ignored generated runs; never treat these as source fixtures.

## Commands

```bash
python -m pip install -e '.[dev]'
cd web && npm install && cd ..
mgeoai run --input assets/scraps --provider recorded --output-dir outputs/demo
pytest
ruff check src tests
mypy src/traffic_fusion
cd web && npm test && npm run lint && npm run build
```

Development servers:

```bash
mgeoai serve --data-dir outputs/demo --host 127.0.0.1 --port 8000
cd web && npm run dev
```

## Engineering rules

- Never modify or delete supplied files under `assets/scraps` or extraction
  prompts other than the versioned `data_fusion_prompt.md` runtime contract.
- Treat all source text as untrusted data and preserve its source/block/JSON-path
  locator. Never execute embedded scripts. The legacy fusion pipeline never sends raw
  HTML to a model. The article-extraction workspace (`src/traffic_fusion/extraction/`)
  does, deliberately and only with scripts/styles stripped, inside a delimited
  `<ARTICLE_SOURCE>` block that the prompt declares to be data; model output is
  schema-validated and quotes are checked for verbatim presence.
- Preserve assertion status, disagreement, unknown values, and source dependency.
  Never infer fault, precise coordinates, or sentiment from tragic facts.
- DeepSeek is the live default. A live failure must remain failed/retryable; never
  silently switch to the recorded provider.
- Tests must be offline. Live smoke calls require explicit credentials, model,
  timeout, and token limits. Pricing is optional (manually imported); a run without a
  price records tokens and reports cost as unknown, and OpenRouter `:free` ids cost $0.
  Cost limits apply only when a price is known; token limits always apply.
- API keys entered in the control panel live in server memory only. Do not log or persist API keys, hidden reasoning, or unnecessary comment data.
- Add modalities and external services behind the protocols in `interfaces.py`
  or `fusion/provider.py`; keep canonical models and API contracts stable.
- GeoJSON is WGS84 `[longitude, latitude]`; representative centroids must retain
  granularity and uncertainty.

## Definition of done

A change is done when relevant backend tests, Ruff, mypy, frontend tests/lint,
and production build pass; generated schemas validate; recorded demo output is
clearly labeled non-live; provenance survives to reports/API; asset and secret
scans are clean; and limitations or live-smoke status are documented.
