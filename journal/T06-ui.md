# T06 UI rebuild

### 2026-10-20 — slice 1
- Did: removed old screens from `web/src` (backend routes untouched); kept `MapView.tsx` and `mapRegions.ts` for the Map tab. New shell with self-hosted JetBrains Mono, light/dark/system themes, role-gated tabs. Done: sign-in, Annotate, Control panel (keys, models/pricing/limits, accounts). Tried in Chromium via playwright-cli: sign-in, save, validation error, both themes. vitest 3 pass, eslint and tsc clean, build ok.
- Next: Map, Annotation score, LLM models tabs; run-inference controls.
- Note: `web/dist` rebuilt but not staged; force-add `web/dist/assets` before committing.

### 2026-10-20 — slice 2
- Open shell: World map, Annotation score and LLM models tabs need no account; Annotate (annotator role) and Control panel (admin) need sign-in. Map shows collection-country counts while labelling is open, gold or model incidents after. Retry-failed button and cumulative run totals in the Control panel. Not yet tried in a real browser with real run data (none exists yet).

### 2026-10-20 — slice 3
- `/` is the open world-map view; `/scores`, `/models` open; `/annotate`, `/control` need sign-in (signed-out visitors are sent to `/login` and back); header "Sign in" button; routes mirror the URL (pushState/popstate). Coverage layer now includes 7 countries missing from `global_countries.toml` (approximate centroids), so all 244 articles are counted.

### 2026-10-20 — slice 4
- Control panel: per-user "Set password" (12+ chars; ends that user's existing sessions via `password_changed_at`; the password is never returned). Runs: a run whose worker thread is gone (service restart) is now shown as `interrupted`, with Resume, Retry failed and Clear. Clear archives to `extraction/runs/_archived/<timestamp>__<id>/` instead of deleting, and archived runs drop out of lists and scores.
- Incident: deploys restart the service and kill a running extraction job; its saved state stayed "running" and Cancel could not work. Resume continues the remaining articles. Do not deploy while a run is active.

### 2026-10-20 — slice 5: article pages
- New open Articles tab (`/articles`, `/articles/<id>`) and "Full details" from a map point: original link, markdown text, images, plus (when labelling is closed) a side-by-side table of gold, each annotator (shown as Annotator A, B, C: usernames are never exposed) and each model run, with all accident records, evidence quotes, image analyses, token/latency/thinking settings and the raw model response. While labelling is open the link, text and images are visible but annotator and model output stay locked (blind annotation). `meta.admin` (group ids, agent claims) is never served.
- State when built: DeepSeek run complete (244 ok, 0 failed, thinking on); only 1 label exists (one annotator). Unticking "Labelling is open" now would show model output to annotators for the other ~243 articles.
- Open question for the paper: public republication of full article text and images has copyright implications; the original link is always shown.

### 2026-10-20 — slice 6: hover cards on the map
- Hovering a point opens a card that stays open while the pointer is on it. Incident markers (labelling closed): title, publisher, gold/model badge, killed/injured, date, place, "Open article details" and the original link. Collection-country points (labelling open): up to 8 article titles with publisher, each opening the article page, plus "+N more". Cards are built with textContent (page titles are untrusted). Tried in Chromium: hover, then click a title opened `/articles/<id>`.
- Note: the per-country article lists come from the browser agent's collection-country claim (`meta.admin.country`), shown as "collection country, not an incident location"; titles and text are already public, so this adds little hint for the annotators' country field, but it is a mild leak while labelling is open.
