# MGeoAI beginner setup tutorial

This tutorial takes you from a fresh checkout to a working MGeoAI dashboard,
then explains how to enable live DeepSeek fusion and reviewer-approved runtime
submissions. No previous Python, React, or FastAPI experience is assumed.

MGeoAI combines attributed traffic-incident evidence. It does not independently
verify that a report is true, determine fault, or establish legal responsibility.

## 1. What you will set up

MGeoAI has two parts:

- a Python pipeline and FastAPI server; and
- a React dashboard in the `web/` directory.

The normal data flow is:

```text
saved HTML and analysis JSON
        ↓
discovery and safe parsing
        ↓
evidence and incident mentions
        ↓
matching, clustering, and fusion
        ↓
JSON, GeoJSON, Markdown, and dashboard API
```

There are two fusion modes:

- `recorded`: deterministic, offline, free, and best for setup and tests;
- `deepseek`: live model calls that require an API key, model, current pricing,
  and cost limits.

Start with recorded mode. Move to DeepSeek only after the offline pipeline and
dashboard work correctly.

## 2. Requirements

Install these tools before continuing:

- Git;
- Python 3.11 or newer;
- Node.js 20 or newer;
- npm, which normally comes with Node.js.

Check the installed versions:

```bash
git --version
python --version
node --version
npm --version
```

On Windows, the simplest supported workflow is Ubuntu under WSL. The commands
below are written for Linux, macOS, or WSL.

## 3. Download the repository

Clone the project and enter its directory:

```bash
git clone git@github.com:hamimmahmud0/MGeoAI.git
cd MGeoAI
```

If your GitHub SSH key is not configured, use the HTTPS clone URL instead:

```bash
git clone https://github.com/hamimmahmud0/MGeoAI.git
cd MGeoAI
```

All commands in the rest of this tutorial assume that your terminal is in the
repository root—the directory containing `pyproject.toml`, `README.md`, and
`web/`.

## 4. Create the Python environment

A virtual environment keeps MGeoAI dependencies separate from other Python
projects.

Create and activate one:

```bash
python -m venv .venv
source .venv/bin/activate
```

Your prompt should now include `(.venv)`. Install MGeoAI and its development
dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

The editable install provides the `mgeoai` command. Confirm it is coming from
the active environment:

```bash
which python
which mgeoai
mgeoai --help
```

Both `which` paths should normally point inside this repository's `.venv`.

Whenever you open a new terminal later, reactivate the environment:

```bash
cd /path/to/MGeoAI
source .venv/bin/activate
```

## 5. Install the dashboard dependencies

Install the frontend packages once:

```bash
cd web
npm install
cd ..
```

Do not run the Python commands from inside `web/`; return to the repository root
first.

## 6. Run the offline pipeline first

Validate the recorded-provider setup:

```bash
mgeoai doctor --provider recorded
```

Generate a demo dataset from the supplied immutable scraps:

```bash
mgeoai run \
  --input assets/scraps \
  --provider recorded \
  --output-dir outputs/demo
```

This run is offline and does not need an API key. A successful command prints a
summary with a completed run ID and creates files under `outputs/demo/`.

Useful first checks are:

```bash
python -m json.tool outputs/demo/run.json
python -m json.tool outputs/demo/incidents.json >/dev/null
```

Recorded output is intentionally labeled as recorded demo data. It demonstrates
the pipeline and UI, not independent verification of the reports.

## 7. Start the dashboard

### Development mode

Development mode uses two terminals and reloads frontend code automatically.

In terminal 1, activate the Python environment and start the API:

```bash
cd /path/to/MGeoAI
source .venv/bin/activate
export FUSION_PROVIDER=recorded
mgeoai serve --data-dir outputs/demo --host 127.0.0.1 --port 8000
```

Keep terminal 1 running. In terminal 2, start Vite:

```bash
cd /path/to/MGeoAI/web
npm run dev
```

Open these addresses:

- dashboard: `http://127.0.0.1:5173`;
- API documentation: `http://127.0.0.1:8000/docs`;
- health check: `http://127.0.0.1:8000/api/health`.

Vite forwards `/api` requests to the FastAPI server on port 8000.

### Production-style local mode

Build the frontend once and let FastAPI serve it:

```bash
cd web
npm run build
cd ..
export FUSION_PROVIDER=recorded
mgeoai serve --data-dir outputs/demo --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

Press `Ctrl+C` in a server terminal to stop that server.

## 8. Understand `.env` configuration

Copy the example before configuring live access or reviewer accounts:

```bash
cp .env.example .env
```

`.env` is ignored by Git and is where local secrets may be stored. Never commit
it, paste it into an issue, or include it in a screenshot.

Important: MGeoAI deliberately does not load `.env` automatically. After editing
the file, export all its variables into the current shell:

```bash
set -a
source .env
set +a
```

Run those three commands again in every new terminal and after changing `.env`.
Restart `mgeoai serve` after changing environment values because the running
server does not reread them.

You can confirm that the model and guardrails are visible without printing the
API key:

```bash
mgeoai doctor --provider deepseek
```

If `doctor` says the model is `unconfigured`, the `.env` file has not been
exported in that terminal.

## 9. Configure a live DeepSeek run

Open `.env` in your editor and set at least these values:

```dotenv
FUSION_PROVIDER=deepseek
DEEPSEEK_API_KEY='replace-with-your-key'
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_API_MODE=chat_completions
DEEPSEEK_THINKING=enabled
DEEPSEEK_INPUT_COST_PER_MILLION_USD=replace-with-current-numeric-price
DEEPSEEK_OUTPUT_COST_PER_MILLION_USD=replace-with-current-numeric-price
FUSION_RUN_COST_LIMIT_USD=5.00
FUSION_DAILY_COST_LIMIT_USD=20.00
```

Obtain current numeric input and output prices from the provider's official
pricing documentation. Prices change, so MGeoAI does not silently assume them.
The application refuses a live run when cost guardrails are enabled but pricing
is missing.

Load the file and validate it:

```bash
set -a
source .env
set +a
mgeoai doctor --provider deepseek
```

The `live_configuration_errors` list should be empty. First make the bounded
smoke call:

```bash
mgeoai smoke-live \
  --data-dir outputs/demo \
  --output-dir outputs/live-smoke
```

Only after the smoke call succeeds, run the full live pipeline into a separate
directory so the recorded demo remains available:

```bash
mgeoai run \
  --input assets/scraps \
  --provider deepseek \
  --output-dir outputs/live-demo
```

Inspect `outputs/live-demo/run.json`, `provider_runs.json`, and
`failed_clusters.json`. A live provider error remains failed or retryable; MGeoAI
does not silently substitute recorded results.

To serve the live dataset:

```bash
mgeoai serve --data-dir outputs/live-demo --host 127.0.0.1 --port 8000
```

## 10. Configure reviewer accounts

The public submission form does not require login. Approval and rejection do.
MGeoAI supports multiple reviewers through a JSON username-to-password-hash map.

Generate one hash per reviewer:

```bash
mgeoai hash-reviewer-password
```

The command asks for the password twice and prints a value beginning with
`pbkdf2_sha256$`. It does not print the original password.

Add the hashes to `.env` as one JSON object. Keep the entire value inside single
quotes so Bash does not expand the `$` characters:

```dotenv
MGEOAI_REVIEWERS_JSON='{"Hamim":"pbkdf2_sha256$...","Oishik":"pbkdf2_sha256$..."}'
```

Reviewer usernames are case-sensitive.

Generate a random session-signing secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the printed value into `.env`:

```dotenv
MGEOAI_SESSION_SECRET='replace-with-the-generated-random-value'
MGEOAI_DATA_DIR=outputs/demo
MGEOAI_BASE_SCRAPS_DIR=assets/scraps
MGEOAI_SECURE_COOKIES=false
```

For an HTTPS deployment, use `MGEOAI_SECURE_COOKIES=true`. Keep it `false` for
plain `http://127.0.0.1` development.

Load the updated file and restart the server:

```bash
set -a
source .env
set +a
mgeoai serve --data-dir outputs/demo --host 127.0.0.1 --port 8000
```

The provider loaded when `serve` starts is also the provider used when a reviewer
approves a submission:

- use `FUSION_PROVIDER=recorded` for offline demonstrations;
- use `FUSION_PROVIDER=deepseek` with a complete live configuration for real
  model generation.

This distinction is important because `mgeoai serve` has no `--provider` option.

## 11. Prepare source packages

The submission page accepts two input types matching the saved scrap formats.

### HTML scrap bundle

Create a folder containing:

```text
my_html_scrap/
├── content.html       # exactly one UTF-8 HTML page; the name may differ
├── SOURCE_INFO.md     # optional source metadata
└── image_01.json      # optional image-analysis JSON, not a raw image
```

The ZIP may contain these files at its root or under one shared top-level folder.
It must not contain unrelated files, nested extra folders, raw images, encrypted
entries, symbolic links, or more than one HTML page.

Create the archive from the directory containing `my_html_scrap/`:

```bash
zip -r report.zip my_html_scrap
```

Uploads and extracted contents are limited to 25 MB. `image_01.json` must contain
a supported image-analysis evidence section.

### Video-analysis JSON

Upload one UTF-8 `.json` object in the same shape as files under
`assets/scraps/youtube/`. This is analysis metadata, not a raw video. It must
contain at least one supported traffic evidence section such as
`traffic_incidents`, `traffic_conditions`, `traffic_affecting_events`,
`locations`, or `claims`.

## 12. Submit and review a source

1. Open the dashboard.
2. Select **Submit source**.
3. Choose **HTML page bundle** or **Video analysis JSON**.
4. Select the ZIP or JSON file.
5. Optionally enter the submitter's name.
6. Select **Submit for review** and save the returned submission ID.
7. Open **Review queue** and sign in with a configured reviewer account.
8. Inspect every quarantined file as text, its size and hash, and the original
   downloadable package.
9. Reject unsafe or irrelevant material, or approve it with a review note.

Approval returns quickly with `processing`. MGeoAI runs one approval pipeline at
a time in a background worker, while the review page polls with short requests
until the job finishes. This prevents a long live run from exceeding a reverse
proxy's request timeout. Keep the API server running while an approval is in
progress; a live run may take several minutes.

Submission states are:

- `pending`: waiting for review;
- `processing`: approval and pipeline loading are running;
- `approved`: package loaded and pipeline output published;
- `rejected`: reviewer rejected the package;
- `ingest_failed`: approval was recorded but pipeline loading failed; a reviewer
  can inspect the error and retry.

Approved packages are retained under `outputs/<run>/runtime_scraps/`. Quarantined
uploads, reviewer decisions, and audit events remain under
`outputs/<run>/moderation/`.

## 13. Inspect the generated data

The most useful output files are:

```text
outputs/demo/run.json              batch status and counts
outputs/demo/sources.jsonl         normalized sources
outputs/demo/evidence.jsonl        attributed evidence
outputs/demo/mentions.jsonl        incident mentions
outputs/demo/matches.json          pair matching decisions
outputs/demo/clusters.json         accepted clusters
outputs/demo/incidents.json        fused incident collection
outputs/demo/incidents.geojson     WGS84 map features
outputs/demo/provider_runs.json    provider metadata and usage
outputs/demo/failed_clusters.json  retained validation failures
outputs/demo/incidents/            per-incident JSON and Markdown reports
```

GeoJSON coordinates are `[longitude, latitude]`. Area and city centroids retain
their granularity and uncertainty; they are not exact crash coordinates.

## 14. Regenerate pipeline outputs

Stop the API server with `Ctrl+C` before regenerating the directory it serves.
This prevents the dashboard from reading a mixture of old and newly written
files.

### Rebuild the recorded demo

Use the recorded provider for a deterministic, offline rebuild of
`outputs/demo`:

```bash
cd /path/to/MGeoAI
source .venv/bin/activate
export FUSION_PROVIDER=recorded

mgeoai doctor --provider recorded
mgeoai run \
  --input assets/scraps \
  --provider recorded \
  --output-dir outputs/demo
```

Inspect the result before restarting the server:

```bash
python -m json.tool outputs/demo/run.json
python -m json.tool outputs/demo/failed_clusters.json
```

Serve the regenerated output:

```bash
mgeoai serve \
  --data-dir outputs/demo \
  --host 0.0.0.0 \
  --port 8000
```

### Generate fresh live DeepSeek output

Load the live configuration and validate it first:

```bash
cd /path/to/MGeoAI
source .venv/bin/activate
set -a
source .env
set +a

mgeoai doctor --provider deepseek
```

Generate into a separate directory so the recorded demo remains available:

```bash
mgeoai run \
  --input assets/scraps \
  --provider deepseek \
  --output-dir outputs/live-demo
```

Then inspect and serve it:

```bash
python -m json.tool outputs/live-demo/run.json
python -m json.tool outputs/live-demo/failed_clusters.json

mgeoai serve \
  --data-dir outputs/live-demo \
  --host 0.0.0.0 \
  --port 8000
```

Reusing a live output directory also reuses successful responses from its
`cache/` directory. Use a new directory such as `outputs/live-demo-2` when you
intentionally want fresh paid provider calls.

`mgeoai run --input assets/scraps` processes the checked-in base corpus only.
Approved runtime submissions are combined with the base corpus when they are
approved or retried through the review queue. Regenerating the tracked
`outputs/demo` directory also appears as a Git change, so inspect `git status`
before committing.

## 15. Reproduce the international corpus run

The checked-in international corpus is separate from the small immutable demo
under `assets/scraps`. It contains 51 collection-country groups, 510 accepted source
records, and 53 automated distinct-domain multi-source candidates. It stores direct
publisher links, short evidence excerpts, hashes, automated review metadata, and
country/multi-source coverage records. It does not redistribute full publisher pages.
The collection country is a discovery/source bucket, not a verified crash location;
pair identity and upstream independence still need qualified human review.

First validate all country and source requirements:

```bash
mgeoai corpus-validate --corpus-dir corpus/global-v1
```

The report must show `VALID`. It checks at least 50 countries, at least 10
accepted sources per country, one distinct-publisher multi-source incident per
country, artifact hashes, and matching review/link records.

Create the ordinary scrap-directory shape used by the pipeline:

```bash
mgeoai corpus-materialize \
  --corpus-dir corpus/global-v1 \
  --output-dir build/global-scraps
```

The materializer intentionally excludes curation-only incident memberships,
reviewer names, and pair labels so they cannot leak into model input. Run the
offline provider over the materialized input:

```bash
mgeoai run \
  --input build/global-scraps \
  --provider recorded \
  --output-dir outputs/global-v1
```

Copy the separately labeled country-coverage layer into the served output:

```bash
cp corpus/global-v1/reports/coverage.geojson outputs/global-v1/coverage.geojson
mgeoai serve --data-dir outputs/global-v1 --host 127.0.0.1 --port 8000
```

### How the global map location is derived

MGeoAI first extracts place wording from each source block and keeps the block's HTML
selector or JSON path. Normalization compares that wording with the checked-in offline
gazetteer and creates a location candidate containing its source evidence IDs,
administrative hierarchy, WGS 84 representative coordinate, granularity, confidence,
and uncertainty explanation. Matching compares only source-named candidates. Fusion
then chooses a supported candidate, preserves alternatives, and writes GeoJSON as
`[longitude, latitude]`.

If no source-named place can be resolved, `global-v1` still shows the record at a
low-confidence amber collection-country marker. The detail panel and legend label this
as `collection_country_fallback`: it comes from corpus collection metadata, is not the
reported crash location, is ignored during incident matching, and should be queued for
gazetteer expansion or reviewer correction. A red marker is a source-named
representative place; it may still be an intersection, road segment, or area centroid
rather than an exact crash point.

Open `http://127.0.0.1:8000` and choose **Global coverage**. These markers use
country centroids to show publisher/source representation. They are not crash
locations. The Overview map only displays incident locations supported by
extracted source evidence.

To check every original source manually, open:

```text
corpus/global-v1/reports/source_links.csv
```

The file contains country code, source ID, article title, publisher, domain,
publication time, direct verification URL, discovery URL, and any multi-source pair
key for every accepted source. The full country list
and quota counts are in `corpus/global-v1/reports/countries.md`. Study design and
limitations are documented in `METHODOLOGY.md`.

Best-effort public social discovery is stored separately in
`work/global_candidates/group_social/`. Those Bluesky metadata candidates are not
accepted sources: they deliberately remain `requires_human_incident_and_location_review`
and include no downloaded media or full thread capture.

## 16. Run the test suite

Backend checks from the repository root:

```bash
pytest
ruff check src tests
mypy src/traffic_fusion
```

Frontend checks:

```bash
cd web
npm test
npm run lint
npm run build
cd ..
```

Automated tests are offline. Do not put a live API call into the test suite; use
`mgeoai smoke-live` when an explicitly bounded live check is required.

## 17. Common problems

### `mgeoai: command not found`

Activate the virtual environment and reinstall the editable package:

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
which mgeoai
```

### `model: unconfigured` even though `.env` is filled in

The file has not been exported into the current shell:

```bash
set -a
source .env
set +a
mgeoai doctor --provider deepseek
```

Restart the API server after loading it.

### Missing current input/output prices

Enter plain numeric per-million-token prices in `.env`, load the file again, and
rerun `doctor`. Do not include currency symbols or explanatory text in numeric
values.

### Reviewer login returns `Method Not Allowed`

An older backend or a different service is probably listening on port 8000.
Stop it, activate the current repository environment, reinstall, and restart:

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
mgeoai serve --data-dir outputs/demo --host 127.0.0.1 --port 8000
```

Confirm that `http://127.0.0.1:8000/docs` contains the reviewer login endpoint.

### Reviewer queue shows `502`

First check the backend directly:

```bash
curl http://127.0.0.1:8000/api/health
```

If local health works but a public tunnel fails, restart the tunnel against
`http://127.0.0.1:8000`. Current approval requests return quickly with
`processing`, so older deployments that time out during approval should be
updated and restarted. If a submission becomes `ingest_failed`, run
`mgeoai doctor --provider deepseek` in the same exported environment used to
start the server. Then restart the server and retry approval.

### Port 8000 is already in use

Find the process before stopping anything:

```bash
ss -ltnp | grep ':8000'
```

Stop the known development server with `Ctrl+C`, or use another port and update
the Vite proxy if developing the frontend.

### Frontend changes do not appear

For development, open port 5173 and keep `npm run dev` running. For the
production-style server, rebuild before restarting FastAPI:

```bash
cd web
npm run build
cd ..
mgeoai serve --data-dir outputs/demo
```

### A run is `partial`

Inspect `failed_clusters.json` and `provider_runs.json`. Partial means useful
outputs were produced but at least one cluster failed strict fusion or provenance
validation. Do not describe a partial run as fully successful.

## 18. Security and deployment notes

- Treat saved HTML and submitted text as untrusted data.
- Never execute scripts found in submitted HTML.
- Never commit `.env`, API keys, reviewer passwords, session secrets, or raw
  provider responses containing unnecessary private data.
- Rotate a key immediately if it appears in Git history, chat logs, screenshots,
  or terminal output shared with others.
- Use HTTPS, secure cookies, reverse-proxy upload limits, and rate limiting for an
  internet-facing service.
- The local moderation store and lock are intended for one application instance.
  Multi-instance deployment requires shared storage, a database, and a
  distributed job queue.
- Back up moderation and runtime data before replacing an output directory.

## 19. Everyday command checklist

Offline development:

```bash
source .venv/bin/activate
export FUSION_PROVIDER=recorded
mgeoai run --input assets/scraps --provider recorded --output-dir outputs/demo
mgeoai serve --data-dir outputs/demo
```

Live development:

```bash
source .venv/bin/activate
set -a
source .env
set +a
mgeoai doctor --provider deepseek
mgeoai serve --data-dir outputs/live-demo
```

Before committing code:

```bash
pytest
ruff check src tests
mypy src/traffic_fusion
cd web && npm test && npm run lint && npm run build
```

For architecture, API contracts, current limitations, and extension points, see
the main [README](README.md).
