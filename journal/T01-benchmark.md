# T01 — Enlarge and independently annotate the benchmark

Status: in-progress

## Goal
Replace the 6-incident / 17-mention / 136-pair benchmark with a larger,
independently annotated set that includes difficult same-incident cases and
related-but-distinct cases. If a larger set is not feasible, the manuscript must
state the 93.6% F1 is proof-of-concept and that the 136 pairs are not independent
(effective n is about 6 clusters).

## Done when
- [ ] Annotation protocol written (guidelines, labels, hard-case categories).
- [ ] At least two independent annotators; agreement (e.g. Cohen's kappa) reported.
- [ ] Hard negatives (same place/time, different incident) and hard positives
      (differing details, languages, outlets) are explicitly included and tagged.
- [ ] Metrics resolved at cluster level with bootstrap CIs resampled by incident,
      not by pair.
- [ ] Fixture added under `tests/fixtures/` (offline, no source corpus edits).
- [ ] Manuscript wording updated to match what was actually achieved.

## Notes
- Existing fixture: `tests/fixtures/golden_pairs.json`; evaluator: `src/traffic_fusion/evaluation.py`.
- Never modify `assets/scraps`.

## Journal

### 2026-10-19 — Plan, annotation tool, search prompt
- Plan agreed: browser agent finds candidate groups (user transports prompt and
  JSON), I fetch and validate pages, four annotators label blind in the app, then
  agreement and consensus export feed `evaluation.py`. Browser agent only finds
  candidates; it does not supply labels. CAPTCHA dropped; password login kept.
- Annotators: hamim, oishik, mubasshir, rubayet (4, fully crossed: all label every item).
- Built (additive): `src/traffic_fusion/annotation/{store,auth,stats,cli}.py`,
  `api/annotation.py` (router registered in `api/app.py` before the SPA catch-all),
  `mgeoai annotate ...` CLI, `web/src/components/Annotate.tsx` ("Annotate" nav item).
- Auth: scrypt hashes, server-side sessions in HttpOnly SameSite=Strict cookie
  (`MGEOAI_COOKIE_SECURE=true` behind HTTPS), 5-failure lockout, forced password
  change at first login. Submits and edits need a signed-in session. Sessions are
  in memory, so run one process.
- Blindness: API never returns other annotators' labels, category/selection
  metadata (kept in `annotation/admin_meta.json`, never served) or pipeline
  decisions. Order and left/right placement differ per annotator.
- Storage: `annotation/` (gitignored), one append-only JSONL per annotator, latest
  wins. Gold export keeps the `golden_pairs.json` shape; `related_distinct`
  and `different` map to `different`, `cannot_tell` to `ambiguous`; unresolved
  items are written separately, not guessed.
- Users created with `mgeoai annotate init-users`; one-time passwords are in
  `annotation/initial_passwords.txt` (0600). Not recorded here. Delete after handing out.
- Search deliverables: `benchmark/browser_agent_prompt.md`, `benchmark/candidates.schema.json`.
- Verification: pytest 44 passed (11 new in `tests/test_annotation.py`), ruff, mypy
  strict, vitest, eslint, production build all clean. Synthetic seed in
  `tests/fixtures/annotation_seed_items.json`, not imported into the real `annotation/` dir.
- Next: user runs the prompt in the browser agent and returns the JSON; I fetch pages
  (check robots/terms first), build pairs, and `import-items`. Open: confirm region,
  date window and target size (about 100 incidents) before sending the prompt.

### 2026-10-19 — Search prompt v2 (Bangladesh + international)
- Prompt now sets a per-batch quota of 20 groups: 12 same_incident (6 BD, 6 intl) and
  8 decoy (4 BD, 4 intl); at least 6 hard groups; intl English-only, 4+ countries,
  max 3 groups per country; max 5 articles per outlet; max 6 groups per month.
- Strict duplicate rules (URL canonicalisation, one incident one group, repost
  handling, cross-language pairs stay in one group); user pastes earlier batches' URLs
  into `<<ALREADY_COLLECTED>>`.
- Schema v2 adds `region`, `country`, `difficulty`, `batch_report` (counts + skipped with
  reasons); max 4 articles per group, 20 groups per batch.
- Expected yield per batch about 12 x 3 + 8 x 2 = 50 articles before attrition; about 5
  batches for 100 groups (60 same-incident, 40 decoy).

### 2026-10-19 — Batches b01-b05 received, validated, fetched, imported
- Input: `benchmark/scraps/candidates_b01..b05.json`. All 5 pass the schema. 100 groups
  (30+30 same_incident BD/intl, 20+20 decoy), 245 articles, 245 unique canonical URLs,
  quotas met exactly, batch_report counts match. No duplicate URL or incident found
  (title-overlap flags were different crashes). Weak points: 10 articles lack
  `published_date`; 90/100 groups tagged "hard" so the tag is not a useful stratifier;
  intl set skews to mass-casualty bus plunges (selection bias to state in the paper).
- Robots: `benchmark/check_robots.py` (report in `benchmark/robots_report.json`). 245 URLs ->
  242 allowed; 3 `sabcnews.com` URLs excluded (robots.txt returned 5xx = disallow, RFC 9309).
  newagebd.net now permits crawling (differs from the 2026-07 note).
- Fetch: `benchmark/fetch_pages.py`, UA identifies the project, >= 3 s per origin (honours
  Crawl-delay), no circumvention. 221 fetched, 21 returned 403 (sky, apnews, jagonews24,
  daily-sun, ndtv, dhakaprokash24, kalbela, wivb): skipped, not worked around. Raw HTML in
  gitignored `benchmark/pages/`.
- Extraction: `benchmark/build_items.py` (JSON-LD articleBody, else article paragraphs;
  unescapes embedded HTML; drops contact/footers; drops text < 300 chars or without crash
  vocabulary). Dropped 43 articles (24 fetch failures, 19 empty/short, mostly JS-rendered
  pages incl. several New Age URLs). Several New Age URLs look like listing pages
  (`.../articlelist/...`), so agent URLs are not all article URLs; only text-verified
  articles are kept.
- Result: 186 articles, 54 of 60 same_incident groups usable, 230 pairs imported
  (134 positive, 66 hard negative vs decoys, 30 easy negative); 42 cross-language pairs;
  119 international / 109 Bangladesh. Seeded (20260101) and re-runnable.
- Annotation store: `annotation/items.json` (served, verified no category/agent fields in
  served JSON) and `annotation/admin_meta.json` (category, agent claim, difficulty,
  never served). Both chmod 600.
- Open: Bangla title-overlap check passed on inspection (tokenizer artifact only). Caspian
  Post/Al Jazeera items carry short footer lines in the text. Class balance is 58% positive (134/230); this is by design:
  report per-category metrics. Annotators must still change
  initial passwords; annotation not started. Pages are third-party content: not committed.

### 2026-10-19 — Item set frozen (before any password handed out)
- Fix: groups with 4 kept articles now use a random spanning tree (3 pairs) so every kept
  article is covered by a human-labelled pair; 2- and 3-article groups use all pairs.
  Verified connectivity for all 54 groups. Rebuild is deterministic (seed 20260101).
- Guard: `mgeoai annotate import-items` refuses when any `labels/*.jsonl` exists unless
  `--force` (test added: `test_import_refuses_after_labels_exist`).
- FROZEN BENCHMARK: `annotation/items.json` sha256
  `cb336e0be75dd984c877b1cd6068f5ebcc55f7af93c60976dfa14ce9208527ab` (1,239,625 bytes);
  230 pairs = 134 positive + 66 hard negative + 30 easy negative; 121 international +
  109 Bangladesh; 42 cross-language; 54 same-incident groups; 186 articles; seed 20260101.
- Smoke test on a copy of the real data (throwaway user, never in real `users.json`):
  login, 230 items, save one label all worked. `/items` response is about 1.2 MB and is
  reloaded after every save: fine on localhost, slow if hosted remotely.
- Verification: pytest 45 passed, ruff (whole repo), mypy strict clean. The UI has not
  been tried in a real browser, only vitest and API tests.
- Next (scoring the pipeline on this benchmark, after annotation):
  1. Each fetched page needs the metadata the pipeline expects (URL, publisher, date);
     check the `SOURCE_INFO.md` format in `assets/scraps/html/*`. Without it the 30% time
     feature has nothing to use.
  2. `split_mentions` can yield several mentions per page; define how an article-pair gold
     label maps to mention-pair decisions.
  3. Bootstrap unit: resample target incidents and carry each incident's decoy pairs.
- Before annotating: each annotator signs in, changes the initial password, then delete
  `annotation/initial_passwords.txt`.

### 2026-10-20 — Migrated to ../MGeoAI (branch t01-annotation-benchmark)
- Reason: `ASCE/` was an older snapshot. `MGeoAI/` (git, v0.2.4) holds `paper_evaluation.py`,
  `evaluation/gold`, the 51-country corpus and the reviewer login. `ASCE/` is now frozen.
- Decisions (user): reuse the repo's reviewer auth; copy data as-is.
- Ported: `src/traffic_fusion/annotation/{store,stats,cli}.py`, `api/annotation.py`
  (registered in `api/app.py` via new `annotation_dir` param, before the SPA catch-all),
  `mgeoai annotate ...` in `cli.py`, `web/.../Annotate.tsx`, `api.ts`/`types.ts`/`App.tsx`
  ("Benchmark annotation" nav), tests, `benchmark/`, `journal/`, `docs/ANNOTATION.md`.
- Auth change: the scrypt user store, forced password change, password-change page and
  login lockout are gone. Labels now need the reviewer session cookie plus `X-CSRF-Token`.
  Annotators are the reviewer accounts, so they can also use the review queue.
  Names must match `^[a-z][a-z0-9_]{1,31}$` (else 403). Old `ASCE/annotation/users.json` and
  its passwords are obsolete (hamim's changed password cannot be converted).
- Data: `annotation/items.json` byte-identical (sha256 `cb336e0b...27ab`), `admin_meta.json`,
  `benchmark/{scraps,pages}` copied. Fresh PBKDF2 accounts issued with `init-users`
  (`annotation/reviewers.json`, `initial_passwords.txt`, both 0600). No labels exist.
- Verification: pytest 93 passed (13 annotation), mypy strict clean, vitest 13 passed,
  eslint clean, production build ok. `ruff check .` reports 5 pre-existing errors in
  `work/global_candidates/**` (same on the unmodified branch). API smoke test on a copy of
  the real items: login, 230 items, save, wrong password 401.
- Repo quirks: `web/dist`, `__pycache__/*.pyc` and `web/node_modules/.vite` are tracked in
  git. The rebuilt `web/dist` is modified on purpose (it contains the Annotate page);
  run Python with `PYTHONDONTWRITEBYTECODE=1` to avoid dirtying tracked .pyc files.
- Not committed. UI still not exercised in a real browser.
- Next: scoring on this benchmark via `paper_evaluation.py`: materialize the 186 fetched
  pages as scraps (as `corpus-materialize` does, without labels), run the pipeline, map
  article-pair labels to mention pairs, fill the blank `llm_only`/baseline rows in
  `ablation_metrics.csv` (T02), and bootstrap over incidents.

### 2026-10-20 — Migration follow-ups (advisor review)
- `benchmark/scraps/*.json` carry `kind`/`decoy_for`/`confusable_by` (match vs decoy), so the
  directory is git-ignored until annotation closes; commit it afterwards. Checked: no other
  tracked-to-be file holds per-item labels (journal has aggregate counts only).
- `init-users` now keeps existing accounts and merges new names unless `--reset` (test added).
- Scoring step: do not serve the pipeline output over these pages from the annotators' server
  until labelling is finished (Overview/Sources would leak clustering decisions).
- Handover notes: old ASCE passwords are void; `ASCE/annotation/initial_passwords.txt` still holds
  them in plaintext (delete only with the user's approval).
