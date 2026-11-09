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

### 2026-11-09 — grouped incident map with fused summaries
- `mgeoai x build-incidents` (DeepSeek): the cluster-cards consensus gives 100 incidents; each gets a neutral fused summary (headline, <= 70-word summary, killed/injured as the highest source figure, source disagreements, English place query), 207k tokens in / 138k out (< $0.5). Places are looked up on OpenStreetMap Nominatim with a fallback that drops the most specific components one at a time and a radius floor (0.3/2/5/15 km by level); country-level results are discarded. Result: 97 of 100 incidents placed (10 point, 7 road segment, 26 area, 22 city, 32 district; median radius 11 km, 36 within 5 km, 9 at 100 km or more). Unplaced: three vague places (Kampala-Gulu highway, Cambodia, southern Peruvian Andes). A separate 70-string sample of raw model location strings: 95% found but only 15 at full specificity, so street-level positions are rare; district or area level is what OpenStreetMap supports for these descriptions.
- Map: new source "Grouped incidents" (one marker per incident; hover card with fused summary, killed/injured, date, place, radius, disagreements and its source articles). It is model output, so it stays behind the labelling lock for anonymous visitors and annotators; a signed-in admin or reviewer who is not an annotator can see it while labelling is open. Tried in Chromium as admin.

### 2026-11-09 — world map reworked: full screen, no side menu
- The World map page is now a full-screen map. Floating controls (data source, colour by people killed / vehicle / year, "killed at least", year chips) and a legend overlay the map; incident details open as a closable card over the map (click) or as the hover card. Circle size = people killed (highest figure reported per incident), colour = severity bucket / vehicle group / year; numbered circles are clusters coloured by the total killed; only the selected incident shows its uncertainty circle. The old side panel (stats, top publishers, lock notice) is gone; the locked view keeps a small floating notice. Backend adds flat properties `killed_n`, `injured_n`, `vehicle_main`, `year` for styling. Tried in Chromium as admin (97 incidents, 1,184 killed as reported).

### 2026-11-09 — one circle per accident, no overlaps; themed scroll bars
- "Labelling is open" was already unticked on the server when checked (16:50 UTC), so the accident map is public; the public view shows incidents, not the 124-article country circle seen while it was locked.
- Map: below zoom 6 nearby incidents merge into numbered circles; from zoom 6 every accident is its own circle (one per incident, not per article). Circles that overlap or share a place (for example several accidents with the same district centroid) are pushed apart on screen only as far as needed (iterative collision resolution, deterministic), with a thin line back to the true place when moved more than 5 px. Unit tests: 7 incidents on one point end up non-overlapping within an 80 px cloud; incidents with room stay put. Tried in Chromium at Bangladesh zoom: 40+ incidents separate, no overlaps.
- Scroll bars (Firefox and Chromium/Safari) now use the theme tokens in both light and dark.
