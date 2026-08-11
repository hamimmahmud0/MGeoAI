# MGeoAI

MGeoAI is a preliminary, provenance-preserving pipeline for turning
saved traffic-related news, social posts, and existing image/video analysis JSON
into reviewable incident records. It clusters reports about the same real-world
incident, retains conflicts and attribution, estimates location at defensible
precision, aggregates aspect-based sentiment, and serves JSON, GeoJSON,
Markdown, and a map-first operations dashboard.

The application fuses attributed evidence. It does **not** independently verify
that an incident occurred, determine fault, or establish that a claim is true.

## Quick start

Requirements: Python 3.11+, Node 20+, and npm.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cd web && npm install && cd ..
mgeoai doctor --provider recorded
mgeoai run --input assets/scraps --provider recorded --output-dir outputs/demo
```

The recorded provider is deterministic, offline, costs nothing, and is labeled
as non-live in every incident. Start development servers in separate terminals:

```bash
mgeoai serve --data-dir outputs/demo --host 127.0.0.1 --port 8000
cd web && npm run dev
```

Open `http://127.0.0.1:5173`. API documentation is at
`http://127.0.0.1:8000/docs`.

For a production frontend build served by FastAPI:

```bash
cd web && npm run build && cd ..
mgeoai serve --data-dir outputs/demo --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

## Live DeepSeek run

Copy `.env.example` to an ignored `.env` or export values from a secret manager.
The CLI intentionally does not auto-load arbitrary `.env` files; activate them
in your shell or deployment system.

```bash
export FUSION_PROVIDER=deepseek
export DEEPSEEK_API_KEY='...'
export DEEPSEEK_MODEL='deepseek-v4-flash'
export DEEPSEEK_API_MODE=chat_completions
export DEEPSEEK_THINKING=disabled
export DEEPSEEK_INPUT_COST_PER_MILLION_USD='current-provider-price'
export DEEPSEEK_OUTPUT_COST_PER_MILLION_USD='current-provider-price'
mgeoai doctor --provider deepseek
mgeoai smoke-live --data-dir outputs/demo --output-dir outputs/live-smoke
mgeoai run --input assets/scraps --provider deepseek --output-dir outputs/live-demo
```

The model is not hard-coded. Check the current provider documentation and choose
an available JSON-output-capable model. In `auto`, the adapter currently chooses
the broadly supported Chat Completions JSON mode. `responses` explicitly requests
JSON Schema output. A failed live call produces a failed/retryable cluster; it
never activates recorded or deterministic fusion silently.

The adapter caps timeouts, retries, concurrency configuration, and output tokens.
It records endpoint mode, prompt/schema/provider/request hashes, latency, usage,
retry and validation state. Successful calls are cached using canonical evidence,
prompt, schema, provider, mode, and model. Credentials are never included in
requests logs, outputs, API data, or the browser.

## Runtime source submission and review

The dashboard includes a public **Submit source** form and an authenticated
**Review queue**. A submitted news report or social post is stored as pending
text. Reviewers can inspect the exact text, metadata, original link, and audit
history before rejecting it or approving it for ingestion. Approval converts
the text to escaped, inert HTML under `outputs/<run>/runtime_scraps/`, combines
it with the configured base scraps, and reruns the pipeline with the configured
provider. Markup supplied by a contributor is displayed and stored as text; it
is never executed.

Configure any number of reviewers with PBKDF2 password hashes. Generate each
hash interactively, then provide a JSON username-to-hash mapping and a random
session-signing secret of at least 32 characters:

```bash
mgeoai hash-reviewer-password
export MGEOAI_REVIEWERS_JSON='{"alice":"pbkdf2_sha256$...","bob":"pbkdf2_sha256$..."}'
export MGEOAI_SESSION_SECRET='replace-with-a-random-secret-at-least-32-characters'
export MGEOAI_DATA_DIR='outputs/demo'
export MGEOAI_BASE_SCRAPS_DIR='assets/scraps'
mgeoai serve --data-dir outputs/demo
```

Set `MGEOAI_SECURE_COOKIES=true` when serving over HTTPS. Reviewer sessions use
an eight-hour, HTTP-only, SameSite cookie and mutating actions also require a
CSRF token. In an internet-facing deployment, terminate TLS and apply request
size/rate limits at the reverse proxy. Reviewer passwords and the signing secret
belong in a secret manager, not in the repository or generated data.

Approval is synchronous in v0.2.0. A live provider failure stays visible as an
`ingest_failed` submission that can be retried; MGeoAI never silently changes to
the recorded provider.

## Commands

```bash
mgeoai doctor --provider recorded
mgeoai hash-reviewer-password
mgeoai ingest assets/scraps --output outputs/demo/manifest.jsonl
mgeoai export-schemas --output-dir schemas
mgeoai run --input assets/scraps --provider recorded --output-dir outputs/demo
mgeoai evaluate --data-dir outputs/demo --output outputs/demo/evaluation.json
mgeoai run --input assets/scraps --provider deepseek --output-dir outputs/live-demo
mgeoai smoke-live --data-dir outputs/demo --output-dir outputs/live-smoke
mgeoai serve --data-dir outputs/demo
```

`run` is the end-to-end command: discovery, HTML conversion, modality adapters,
normalization, incident splitting, candidate matching, provider adjudication,
constraint-aware clustering, provider fusion, provenance validation, geolocation,
sentiment, and reporting.

## Inputs and outputs

Supported inputs are local saved HTML, `SOURCE_INFO.md` metadata next to HTML,
the supplied video/general analysis JSON, and the supplied image-analysis JSON.
Raw media inference, scraping, and platform access are not implemented.

Generated data is ignored under `outputs/<run>/`:

```text
manifest.jsonl                 discovered artifacts and hashes
sources/<source_id>/content.md clean model-readable Markdown
sources/<source_id>/blocks.json reversible block/provenance sidecar
sources.jsonl                  canonical source records
evidence.jsonl                 normalized evidence items
mentions.jsonl                 incident-level mentions (one source may have many)
sentiment.jsonl                holder/target/aspect sentiment evidence
matches.json                   features and provider adjudications
clusters.json                  accepted incident clusters
incidents/<id>/incident.json   canonical validated incident
incidents/<id>/report.md       deterministic human-readable report
incidents.json                 API collection
incidents.geojson              WGS84 [longitude, latitude] mapped collection
provider_runs.json             operational metadata without hidden reasoning
failed_clusters.json           terminal failures retained for retry/review
run.json                       batch summary and recorded/live mode
cache/                         successful request cache
moderation/submissions/        pending/reviewed submissions and audit history
runtime_scraps/                approved text materialized as inert HTML
```

Versioned JSON Schemas are exported to `schemas/`.

## Configuration

Checked-in defaults live in `configs/default.toml`; environment values override
provider secrets and deployment-specific settings. The major controls are
documented in `.env.example`: endpoint, model, API mode, timeout, retry count,
concurrency, token budget, and cost guardrails. Manual must-link/cannot-link pairs
can be placed in the TOML `[overrides]` section.

The local Bangladesh gazetteer stores representative area/city centroids for the
demo corpus. Its coordinates never claim rooftop precision. Unmapped incidents
remain available in the dashboard list.

## API and dashboard

The FastAPI service provides:

- `GET /api/incidents` with bbox, date, type, severity, confidence, source-count,
  sentiment, search, and pagination filters;
- `GET /api/incidents/{incident_id}`;
- `GET /api/incidents/{incident_id}/evidence` with full cited claims and provenance;
- `GET /api/incidents.geojson` with server-side spatial/filter handling;
- `GET /api/sources` and `GET /api/sources/{source_id}` with safe extracted
  content, plus `GET /api/runs` and `GET /api/health`;
- `POST /api/submissions` and `GET /api/submissions/{submission_id}/status` for
  public runtime source intake and status receipts;
- `POST /api/reviewer/login`, `GET /api/reviewer/me`, and reviewer-only queue,
  logout, approval, rejection, retry, and audit endpoints under `/api/reviewer`.

The React interface starts on a world map and includes marker clustering,
map/list synchronization, URL-preserved filters and selected incident, location
precision and named uncertainty regions, labeled roads and administrative
boundaries, informative fused summaries, a detailed fact/conflict/source review,
inspectable evidence and source content, unmapped records, source and run tables,
loading/error/empty states, a system/light/dark theme selector, and a small-screen
map/list toggle. Override the light map with
`VITE_MAP_STYLE_LIGHT_URL` (or the legacy `VITE_MAP_STYLE_URL`) and the dark map
with `VITE_MAP_STYLE_DARK_URL`; selected styles must provide their required
attribution.

## Development and verification

```bash
pytest
ruff check .
mypy src/traffic_fusion
cd web
npm test
npm run lint
npm run build
```

Tests use the recorded provider and mocked network responses. They must not make
live paid calls. Use a short, explicitly configured smoke run for DeepSeek.

## Extension points

To add a modality, implement an adapter that maps the new extraction contract to
`EvidenceItem`, preserving unknown fields and a source locator. Then register the
artifact in discovery and add sample-derived fixtures.

To add a provider (including the planned OpenAI provider), implement the small
`FusionProvider` protocol: `adjudicate`, `fuse`, `runs`, `name`, and `model`.
Canonical models, orchestration, CLI, reports, and API do not need to change.

## Matching and confidence design

Candidate matching is intentionally transparent. The deterministic score weighs
time (30%), normalized location (35%), named entities (15%), vehicles (5%), and
distinctive lexical overlap (15%). Generic crash terms are excluded. Specific
date/location conflicts become hard cannot-links before the provider is called;
distinctive shared anchors raise recall, while the provider still adjudicates the
bounded candidate. Cluster construction refuses a transitive merge that would
violate any cannot-link.

Recorded fusion confidence starts from direct normalized support, adds repeated
independent agreement, and subtracts conflicting alternatives; it is capped at
0.90. Live DeepSeek confidence is accepted only after schema, ID, quantity, and
provenance validation. Extraction confidence never changes an attributed
allegation into an observation.

## Current limitations

- HTML extraction is reproducible and provenance-preserving but heuristic; large
  site redesigns need publisher-specific selectors.
- The incident splitter uses transparent lexical/location anchors suited to the
  supplied Bangladesh corpus. Broader deployment needs learned extraction plus a
  larger evaluated gazetteer.
- No raw image/audio/video inference, live scraping, external geocoder, or
  multi-tenant retention service is included.
- The moderation queue and reviewer sessions use local files and process-local
  locking. Multi-instance deployment needs a shared database, distributed job
  queue, centralized rate limiting, and coordinated pipeline publication.
- The small evaluation corpus is a development fixture, not an accuracy claim.
- The production frontend is functional but MapLibre keeps the initial JavaScript
  bundle above Vite's 500 kB advisory threshold; route/map code splitting is a
  performance follow-up, not a build failure.
