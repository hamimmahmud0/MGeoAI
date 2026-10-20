# T06 UI rebuild

### 2026-10-20 — slice 1
- Did: removed old screens from `web/src` (backend routes untouched); kept `MapView.tsx` and `mapRegions.ts` for the Map tab. New shell with self-hosted JetBrains Mono, light/dark/system themes, role-gated tabs. Done: sign-in, Annotate, Control panel (keys, models/pricing/limits, accounts). Tried in Chromium via playwright-cli: sign-in, save, validation error, both themes. vitest 3 pass, eslint and tsc clean, build ok.
- Next: Map, Annotation score, LLM models tabs; run-inference controls.
- Note: `web/dist` rebuilt but not staged; force-add `web/dist/assets` before committing.

### 2026-10-20 — slice 2
- Open shell: World map, Annotation score and LLM models tabs need no account; Annotate (annotator role) and Control panel (admin) need sign-in. Map shows collection-country counts while labelling is open, gold or model incidents after. Retry-failed button and cumulative run totals in the Control panel. Not yet tried in a real browser with real run data (none exists yet).
