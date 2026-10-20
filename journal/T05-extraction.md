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

### 2026-10-20 — DeepSeek truncation failures
- Symptom: 32 of 244 articles failed with `finish_reason=length`, empty answer text, 4,000 output tokens. Cause: `deepseek-flash` runs in thinking mode by default and reasoning tokens count against `max_tokens` (successful calls: median 2,084 output tokens for a ~500-token answer, max 3,965). Docs: `thinking: {type: disabled}` switches it off (Context7, 2026-10-20).
- Fix: provider setting `thinking` (default `disabled`, DeepSeek only) sent as `thinking={"type":"disabled"}`; Max output tokens and Thinking are now editable in the control panel; the truncation error now says why. Retry failed to finish the 32. Cost note: thinking-off answers are shorter, so the retry should be cheaper than the first pass; quality difference between thinking on/off is untested.

### 2026-10-20 — thinking on by default, max output
- DeepSeek defaults changed on request: thinking on (`thinking: default`, the model's own mode) and Max output tokens 393,216 (the documented API maximum for `max_tokens`), timeout 600 s (non-streaming thinking calls can take minutes). The input context window is the model's own and is not a setting; 393,216 is the output cap. Other providers keep 4,000 until set (their maximums differ per model; OpenRouter free models are unknown). Each stored result now records `call_settings` (thinking, max output) for provenance. Run folders are still named without the thinking flag, so do not mix thinking-on and thinking-off results in one run (clear/archive first).
- The earlier DeepSeek run was archived by the admin: `extraction/runs/_archived/20261020T142135__deepseek__deepseek-flash__markdown__txt` (244 results, 211 ok, 33 failed, thinking on, 4,000 cap).
