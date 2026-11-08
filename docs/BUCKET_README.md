---
license: other
pretty_name: MGeoAI annotation, model-output and news-source backup
---

# MGeoAI backup bucket (`hamimmahmud0/mgeoai-backup`, private)

A live backup of the **MGeoAI road-accident extraction workspace**: the human annotations, every LLM
extraction run, and the saved news articles they refer to. It is written by an automatic worker every
6 hours. Code: https://github.com/hamimmahmud0/MGeoAI (package `traffic_fusion`, subpackage `extraction`).
If you are an agent: read this file fully, then `manifest/status.json`, before touching anything.

## What the project does (30 seconds)
~244 saved news articles (Bangladesh + international road crashes) were collected. For each article:
1. an **LLM** (DeepSeek / OpenRouter models) reads the article and returns a JSON record of the accident(s);
2. **human annotators** read the same article and fill the same fields **blind** (they never see model output
   or each other's labels);
3. a report compares model vs humans vs each other. Gold = strict majority of >= 3 annotators per field.
The research question is whether LLM extraction is accurate and whether it needs human checking.

## Layout
```
README.md                       this file
latest/                         mirror of the source, updated every backup. NEVER deletes: a file removed at
                                the source can linger here, so use manifest/latest.json as the truth.
  articles/<article_id>/        one folder per news article (the "news source")
      meta.json                 url, publisher, title, dates, language, image list, + "admin" block (see below)
      article.md                cleaned markdown of the page (what annotators and the "markdown" model input see)
      model_raw.html            page HTML with scripts/styles stripped (the "raw" model input)
      raw.html                  the original saved HTML, untouched
      images/<n>.<ext>          article photos saved from the page (jpg/png/gif/webp)
  labels/<annotator>.jsonl      human annotations, append-only (one file per annotator)
  runs/<config_id>/             LLM results, one folder per model configuration
      run.json                  state of the run (status, token counts, cost, spec)
      <article_id>.json         result for one article
  runs/_archived/<ts>__<config_id>/   runs an admin cleared; kept, not deleted
  control.json                  provider settings (models, limits, prices). No secrets.
  geocode_cache.json            place -> coordinates cache (only if geocoding was run)
  sources.csv                   one row per article: id, publisher, title, url, dates, language, images saved
  schemas/                      JSON Schemas for a label and an accident record
history/<UTC timestamp>/        created ONLY when labels, runs or settings changed since the previous backup
  CHANGES.json                  per-annotator label counts before/after, changed files, warnings
  labels/*.jsonl                full label files as they were at that time
  runs/...                      only the run result files that changed
  control.json                  if it changed
manifest/latest.json            sha256 + size of every backed-up file at the last backup + label stats
manifest/status.json            last_backup_utc, whether anything changed, counts. Liveness signal: if
                                last_backup_utc is older than ~7 hours the worker is down.
reports/<UTC timestamp>/        generated analysis reports (HTML), e.g. model_vs_annotators.html
```
Timestamps are UTC, format `YYYYMMDDTHHMMSSZ`. Not in this bucket on purpose: user accounts and password hashes,
initial passwords, API keys, lock files.

## Data formats

### Article `meta.json`
`id` (= first 16 hex of sha256 of the URL), `url`, `publisher`, `title`, `published_at`, `language`,
`sha256` (of raw.html), `source_file`, `source_variant`, `markdown_chars`, `images[]`
(`url, source, alt, status, file, sha256, content_type, bytes`; `file` set only when saved), and `admin`:
`group_id, batch, region, country, agent_claim, http_status, drop_reason` = benchmark-construction data from
a browser agent (which articles were meant to describe the same crash). **`admin` can bias annotators and
models. Never show it to annotators or put it in a model prompt.**
`source_variant`: `http_fetch` (downloaded politely), `browser_resave` (browser re-save of a page whose
fetch had no text), `browser_recovery_after_http_error` (HTTP 403 pages saved in a browser),
`browser_recovery_robots_disallowed` (3 pages the site's robots.txt disallowed, saved in a browser by choice:
state this as a limitation in any write-up).

### Annotation line (`labels/<annotator>.jsonl`)
Append-only; **the last line for a given `article_id` is that annotator's current answer**; earlier lines are
revisions (`revision` counts up). Keys: `article_id, annotator, accidents[], images[], unusable, notes,
submitted_at, revision`. `accidents[]` holds one record per separate accident (or one record with
`accident: false`). `unusable: true` = the page is not a usable article.

### Accident record (annotators and models share it; key spelling is part of the contract)
`accident` (bool), `casualities` (int, killed + injured; sic), `fatalities` (int), `vehicles` (list from:
car, bus, truck, covered_van, pickup, microbus, motorcycle, cng_autorickshaw, battery_autorickshaw, rickshaw,
human_hauler, bicycle, tractor, train, ambulance, van, or `other:<name>`), `date` (`YYYY-MM-DD` or ISO with
offset; the date of the ACCIDENT), `country`, `location` (specific to general), `longitude and latitude`
(string `"lat,lon"`, only if the article states it; GeoJSON elsewhere is `[lon, lat]`), `evidences[]`
(`field, quote, note`; quotes are verbatim from the article). Unknown = `null`, never "N/A".

### Model result (`runs/<config_id>/<article_id>.json`)
`status` (`ok` | `failed`), `error`, `accidents[]` (same record), `images[]` (what the model says it sees),
`quality {quotes, verbatim}` (evidence quotes found verbatim in the article), `input_tokens`, `output_tokens`,
`latency_ms`, `finish_reason`, `model_returned`, `images_sent`, `call_settings {thinking, max_output_tokens}`,
`raw_text` (the model's raw reply), `retries`, `prompt_hash`, `spec`, `started_at`, `finished_at`.
Folder name `config_id` = `<provider>__<model slug>__<markdown|raw>__<img|txt>`. It does NOT include the thinking
setting or the output cap: check `call_settings` inside each result before comparing runs. Only the latest
attempt per article is kept (a retry overwrites a failed record).
Prompt: `assets/mllm_prompts/accident_extraction_prompt.md` in the GitHub repo (hash in `prompt_hash`).

## How to work with this bucket
```bash
export HF_TOKEN=...                                    # a token with access to this private bucket
hf buckets sync hf://buckets/hamimmahmud0/mgeoai-backup/latest ./extraction     # restore everything
hf buckets sync hf://buckets/hamimmahmud0/mgeoai-backup/history/<ts> ./snapshot # one point in time
hf buckets list hamimmahmud0/mgeoai-backup --recursive --format json            # browse
```
To restore the live app: put `labels/` and `runs/` back under the server's `extraction/` directory
(`MGEOAI_EXTRACTION_DIR`) and restart the service; accounts must be recreated (`mgeoai x init-accounts`).
Latest answer per (annotator, article): read each JSONL, keep the last line per `article_id`.
Gold and scoring rules live in `src/traffic_fusion/extraction/scoring.py`; the comparison report in
`.../report.py` (`mgeoai x report --root <dir> --output out.html`).

## State and caveats (as of the first backup, 2026-11-08)
- Labelling is **still open**: annotators oishik (~122 articles) and mubasshir (~89) are mid-way; hamim has 1
  test label; rubayet none. **No article has the 3 labels needed for gold yet.** Do not call anything "accuracy".
- Every human label so far says "accident". Nobody has used "no accident" or "unusable".
- Model runs: DeepSeek `deepseek-flash` (markdown, no images, thinking on, max output 393,216) covers all 244
  articles; an OpenRouter `minimax/minimax-m3.1-flash:free` run with images is partial (many requests failed:
  free-tier rate limits).
- The model's markdown input lacks the page's publication date (annotators see it), which explains most
  model-vs-human date mismatches. Vehicles and place names are free-form, so exact agreement is low.
- 8 articles have no images (robots.txt or errors).
- Articles are third-party copyrighted text and images; keep this bucket private.

## Rules for agents
1. Treat the bucket as append-only history: do not delete or overwrite `history/` or `latest/` by hand.
2. Never commit or upload tokens, accounts, or password files here.
3. Do not show annotators anything from `runs/`, other annotators' labels, or `meta.json:admin`.
4. Say "agreement", not "accuracy", until gold exists.
5. Add new analyses under `reports/<UTC timestamp>/` with a short note on what produced them.
