# T05 LLM article extraction

### 2026-10-20 — slice 1
- Did: branch `feat/llm-extraction-ui`; plan in `~/.claude/plans/cozy-riding-treasure.md`. Built `extraction/{schema,prepare,intake,accounts,control,annotation_store,cli}.py`, `api/{x_auth,extraction}.py`, 5 offline tests (99 pytest pass, ruff and mypy clean).
- Decisions: httpx-only providers and an in-house markdown converter (no SDKs/markdownify). Roles admin/reviewer/annotator; API keys entered in the UI stay in server memory only. Geocoder = Nominatim (1 req/s, cached, admin-triggered, granularity recorded), not implemented yet.
- Intake rule (checked against `dropped_articles.json`): `<id> copy.html` beats `<id>.html`; the 19 copies are exactly the 19 short_text drops. 20 of 21 HTTP-403 pages recovered; 3 robots-disallowed pages were fetched by browser agent at the user's choice (meta.json variant `browser_recovery_robots_disallowed`; state as limitation).
- Result: 244 articles built. 24 missing: 23 from `candidates_b06` (not fetched) + `2427905c94d5afea` (dhakaprokash24, 403, no recovery file).
- Next: provider layer + runs from the control panel, scoring, images download, adjudication, map/score/model tabs, AGENTS.md update (raw-HTML rule).

### 2026-10-20 — slice 2 (user decisions + providers)
- User decisions: separate admin account (`admin`; `hamim` is annotator only, so blindness lock never hits an admin); drop `candidates_b06` and the one missing 403 page; first providers = DeepSeek (image-capable `deepseek-flash`) and OpenRouter free models; cost values are optional and imported manually, runs must work without them.
- Docs checked via Context7 (2026-10-20): DeepSeek chat completions accept `image_url` parts (http(s) or base64 data URL) for `deepseek-flash`; models `deepseek-flash`, `deepseek-v4-pro`. OpenRouter `image_url` parts, `:free` models limited to 50 req/day without purchased credits (1000/day with 10+ credits), 429 retry with backoff.
- Built: `extraction/{providers,runs,images}.py`, admin endpoints (estimate/start/list/cancel runs, pricing import), prompt `assets/mllm_prompts/accident_extraction_prompt.md`, Control panel run UI. OpenAI and Anthropic are registered but not implemented (Anthropic needs the claude-api skill first).
- Result: 105 pytest pass, ruff and mypy clean. No live call made (no key set yet).
- Images: `mgeoai x fetch-images` started in the background (robots.txt, 3 s per host, 5 MB cap); annotators see only the saved local copies.
- AGENTS.md updated: raw-HTML rule and pricing rule.

### 2026-10-20 — slice 3 (retry, open dashboard, scoring)
- Images: candidate filter (no svg/logo/icon/ads/`_files/`, lazy-load and srcset aware) and a quality gate (>= 8 KB, >= 200 px short side, >= 300 px long side); `mgeoai x fetch-images` refreshes candidates first. 631 good images, 236 of 244 articles have >= 1; the other 8 are robots-disallowed (sabcnews, iol, manobkantha) or return errors (ndtv). Not worked around.
- Retries: 2 retries inside a call for 408/409/429/5xx/timeouts (2 s, 4 s, Retry-After up to 30 s); parse/schema/truncation failures are not retried. "Retry failed" button per run row re-runs only failed articles (`only_failed`). Estimate now counts failed articles as still to do. Run totals shown are cumulative, derived from the per-article results; `attempt` keeps the latest start's counters. Daily cost limit is still not enforced (token limit and run cost limit are).
- Open dashboard (no login): everything beyond corpus facts is gated by `labelling_open` (Control panel switch). While open, anonymous visitors see only article/image counts, publisher/language counts, labelling counts and per-country article counts at collection-country centroids (explicitly not incident locations). Map, annotation agreement and model scores unlock when an admin unticks "Labelling is open". Reason: annotators are web users too; a public model-output view would defeat blind annotation.
- Gold rule: a field is gold only when a strict majority (> half, at least 3 annotators) gave the same normalised value, else unresolved. Per-field model metrics only on articles whose gold has exactly one accident; multi-accident articles are scored on the accident flag and accident count only. Bootstrap 95% CI by article (1,000 resamples, seed 7). Endpoint results are cached on file mtimes.
- Geocoding: Nominatim (1 req/s, cache `extraction/geocode_cache.json`, admin-triggered via `POST /api/x/admin/geocode`); points are place centroids with granularity and bbox-derived radius. No admin button yet.
- Result: 109 pytest pass, ruff and mypy clean, frontend 4 tests + lint + build pass.
