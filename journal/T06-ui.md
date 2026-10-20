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
