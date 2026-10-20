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
