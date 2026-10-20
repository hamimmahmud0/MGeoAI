# Transfer prompt: continue the MGeoAI paper-revision work

Paste this into a new Claude Code session started in `~/Workspace/MGeoAI`.
(Written 2026-10-20. The repo-root `PROMPT.md` is the original build brief; do not overwrite it.)

## Who and what
I am preparing a revision of a paper on MGeoAI, a provenance-preserving pipeline that fuses
traffic-news HTML plus pre-analysed image/video JSON into attributed incident records
(Python package `traffic_fusion`, FastAPI API, React/MapLibre dashboard). Reviewers' main
complaints, which drive the work:

1. The manual evaluation is tiny (6 incidents, 17 resolved mentions, 136 non-independent
   pairs, 93.6% pairwise F1) and the heuristic-only ablation equals the hybrid F1, so no LLM
   accuracy benefit is shown. Needs a larger, independently annotated set with hard cases and
   proper baselines.
2. The international corpus shows processing, not usable intelligence (49/441 multi-source,
   +0.6 pp completeness, 0.9% source-named locations; provenance links are not correctness).
3. Multimodal and sentiment parts are not validated enough to be in the title.
4. Camera-ready: two figures both numbered "Figure 2"; clarify "a MLLM particularly GPT 5.6 Sol"
   in Section 3.2; put the fatality bootstrap interval (33.3 to 100%) in the abstract.

## Repository and rules
- Work only in `/home/hamim-mahmud/Workspace/MGeoAI` (git, remote origin `hamimmahmud0/...`,
  default branch `main`). The old copy `~/Workspace/ASCE` is a frozen snapshot: do not use it.
  Use absolute paths, `.venv` (Python 3.13), `web/node_modules` exists.
- Read `AGENTS.md`. Key rules: never modify `assets/scraps` or the extraction prompts;
  tests offline; never log or store API keys; DeepSeek is the live default and a live failure
  stays failed (no silent fallback to the recorded provider); never infer fault or precise
  coordinates; GeoJSON is `[lon, lat]`.
- Definition of done: pytest, ruff, `mypy src/traffic_fusion`, `web` npm test/lint/build.
  `ruff check .` has 5 pre-existing errors in `work/global_candidates/` (not ours).
- Run Python with `PYTHONDONTWRITEBYTECODE=1`: `__pycache__/*.pyc`, `web/dist`,
  `web/node_modules/.vite` are tracked in git and get dirtied otherwise. `web/dist` is
  git-ignored but its built assets must be force-added (`git add -f web/dist/assets`) when
  rebuilt, or a fresh clone serves a blank dashboard (already fixed once, PR #2).
- Git: branch first (never commit to `main` directly), commit only when I ask, end commit
  messages with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. I open the PRs
  myself and have merged #1 (annotation) and #2 (dashboard assets).
- Secrets: never print or journal passwords; `annotation/initial_passwords.txt` and
  `.env` are secret. Ask before deleting anything.
- Style: concise answers, lead with the result, flag uncertainty, tell me what I must do.

## Task tracker (`journal/`)
One journal file per task, append-only entries (newest last): `journal/README.md` (index),
`T01-benchmark.md`, `T02-baselines.md`, `T03-llm-claim.md`, `T04-abstract-interval.md`.
Work one task at a time and update the journal and status as you go.

| ID | Task | Status |
|---|---|---|
| T01 | Enlarge and independently annotate the benchmark | in progress (labelling not started) |
| T02 | Add baselines for matching (time+location rule, lexical, embeddings, LLM-only) | todo, needs T01 |
| T03 | Reframe the LLM-adjudication claim (no accuracy benefit shown) | todo, needs T02 |
| T04 | Put the fatality bootstrap interval in the abstract | todo, needs T01 |

Not yet tasks (add as T05+ if I ask): human-validate a sample of the international records and
narrow geographic/operational claims; decide multimodal and sentiment (evaluate or drop from
title); fix duplicate "Figure 2"; clarify "GPT 5.6 Sol".

## State of T01 (what exists)
- Candidate collection: `benchmark/browser_agent_prompt.md` and `candidates.schema.json` were
  run by me in a browser agent; 5 batches are in `benchmark/scraps/candidates_b01..b05.json`
  (100 groups, 245 articles). The agent only proposes candidates; it supplies no labels.
- Pipeline: `benchmark/check_robots.py` (robots.txt, RFC 9309), `fetch_pages.py` (polite, no
  circumvention; 21 pages returned 403 and were skipped), `build_items.py` (extraction, pairs).
  Result: 186 articles, 54 usable same-incident groups, **230 pairs** = 134 positive,
  66 hard negative, 30 easy negative; 121 international, 109 Bangladesh; 42 cross-language.
- FROZEN item set: `annotation/items.json` sha256
  `cb336e0be75dd984c877b1cd6068f5ebcc55f7af93c60976dfa14ce9208527ab`, seed 20260101.
  Do not change it once labels exist (`import-items` refuses unless `--force`).
- Annotation tool (merged to `main`): `src/traffic_fusion/annotation/{store,stats,cli}.py`,
  `src/traffic_fusion/api/annotation.py`, `web/src/components/Annotate.tsx` ("Benchmark
  annotation" nav), `mgeoai annotate init-users|import-items|status|agreement|export`.
  Blind by design: the API never serves other annotators' labels, `admin_meta.json`
  (category, agent claim, difficulty) or pipeline decisions; order and left/right placement
  are shuffled per annotator. Labels: same_incident, related_distinct, different,
  cannot_tell; append-only `annotation/labels/<name>.jsonl`, latest wins.
- Auth reuses the repo's reviewer login (`MGEOAI_REVIEWERS_JSON` PBKDF2 hashes,
  `MGEOAI_SESSION_SECRET` 32+ chars, cookie `mgeoai_reviewer`, `X-CSRF-Token` on writes).
  Annotators: hamim, oishik, mubasshir, rubayet (all four label every pair). No lockout and
  no password-change page. Accounts and `initial_passwords.txt` were generated in
  `annotation/`; I have not confirmed they were handed out. No labels exist yet.
- Docs: `docs/ANNOTATION.md` (runbook) and `docs/ANNOTATION_GUIDELINES.md` (annotators).
  Small known doc slip: `--reset` is a flag (`init-users NAME... --reset`), not `--reset NAME`.
- Tests: 94 pytest tests pass (13+ in `tests/test_annotation.py`), vitest 13 pass, mypy and
  eslint clean. The annotation UI has never been tried in a real browser.
- Git-ignored on purpose: `/annotation/`, `benchmark/pages/`, `benchmark/scraps/` (it leaks
  match-vs-decoy status; commit it only after annotation closes), `items_import.json`,
  `dropped_articles.json`, `robots_report.json`, `fetch.log`.

## What to do next
1. Check whether labelling has started: `mgeoai annotate status` (run from the repo root; if
   `annotation/labels/` is missing, nothing has been labelled).
2. When all four are done: `mgeoai annotate agreement --output annotation/agreement.json`
   and `mgeoai annotate export --output annotation/gold.json` (strict majority of at least 3;
   unresolved pairs go to `gold.unresolved.json`, never guessed). Interpret Krippendorff's
   alpha (>= 0.80 good, 0.667 to 0.80 tentative). Adjudicate unresolved items with the four
   annotators; there is no merge command yet for `annotation/adjudication.json` (build it).
3. Score the pipeline on the benchmark (the hard part). Gold pairs are article pairs; the
   pipeline evaluates mention pairs (`split_mentions` can yield several mentions per page).
   - Materialize the 186 fetched pages as scraps like `mgeoai corpus-materialize` does
     (`html/<id>/content.html` plus `SOURCE_INFO.md`; check the format in
     `assets/scraps/html/*`; the 30% time feature needs URL, publisher and date), without
     leaking labels.
   - Run the pipeline into a separate output directory, never served from the annotators'
     server before labelling ends (Overview/Sources would reveal clustering).
   - Define and document the article-pair to mention-pair label mapping.
   - Add a benchmark section to `src/traffic_fusion/paper_evaluation.py` (the existing code
     writes `evaluation/results/ablation_metrics.csv` with `heuristic_only` and `full_hybrid`
     identical and a blank `llm_only`); bootstrap by incident, carrying each incident's decoy
     pairs; report per category (positive, hard negative, easy negative), region and
     cross-language.
   - Live LLM calls need explicit credentials, model, current pricing, timeout, token and
     cost limits (AGENTS.md); tests stay offline with the recorded provider.
4. Then T02 (baselines), T03 (wording), T04 (abstract interval, recomputed on the final
   benchmark), and the unlisted reviewer items above.

## Gotchas learned
- The browser agent's URLs are not all article URLs (several New Age URLs were listing pages);
  only text-verified articles are kept. 90 of 100 groups were tagged "hard", so that tag is
  not a stratifier. The international set skews to mass-casualty bus plunges: state it as a
  selection-bias limitation in the paper.
- `assets/scraps/html/08/SOURCE_INFO.md` differs between the old and new repo (one line);
  `MGeoAI` is the source of truth.
- Site access (see memory `asce-news-pipeline`): newagebd.net now allows crawling; sky.com,
  apnews.com, jagonews24, daily-sun, ndtv, dhakaprokash24, kalbela return 403; sabcnews.com
  robots.txt returns 500 (treated as disallow).
- Auto-memory lives in `~/.claude/projects/-home-hamim-mahmud-Workspace-ASCE/memory/`
  (`mgeoai-repo-migration.md`, `asce-news-pipeline.md`).
