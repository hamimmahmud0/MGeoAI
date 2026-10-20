# T06 UI rebuild

### 2026-10-20 — slice 1
- Did: removed old screens from `web/src` (backend routes untouched); kept `MapView.tsx` and `mapRegions.ts` for the Map tab. New shell with self-hosted JetBrains Mono, light/dark/system themes, role-gated tabs. Done: sign-in, Annotate, Control panel (keys, models/pricing/limits, accounts). Tried in Chromium via playwright-cli: sign-in, save, validation error, both themes. vitest 3 pass, eslint and tsc clean, build ok.
- Next: Map, Annotation score, LLM models tabs; run-inference controls.
- Note: `web/dist` rebuilt but not staged; force-add `web/dist/assets` before committing.
