# Benchmark annotation procedure (task T01)

How the independently annotated matching benchmark is built, labelled, checked and used.
Annotators should read [ANNOTATION_GUIDELINES.md](ANNOTATION_GUIDELINES.md).

## Purpose and design
The earlier gold set covers 6 incidents, 17 resolved mentions and 136 non-independent pairs,
so it only supports proof-of-concept claims. This benchmark replaces it with a larger,
blind, multi-annotator set that includes hard same-incident cases and related-but-distinct
cases. The human labels are the ground truth; the browser agent that found the candidates
supplies **no** labels.

- **Blind:** each annotator sees only the two reports. No pipeline decision, agent grouping,
  difficulty tag or other annotator's label is ever served.
- **Fully crossed:** all four annotators label every pair, so agreement can be estimated
  with Krippendorff's alpha and pairwise Cohen's kappa.
- **Item order and left/right placement** are shuffled per annotator (seeded by the name).

## Pipeline at a glance

| Stage | Tool | Output |
|---|---|---|
| 1. Candidate search (browser agent) | `benchmark/browser_agent_prompt.md`, `benchmark/candidates.schema.json` | `benchmark/scraps/candidates_bNN.json` |
| 2. robots.txt check | `benchmark/check_robots.py` | `benchmark/robots_report.json` |
| 3. Polite page fetch | `benchmark/fetch_pages.py` | `benchmark/pages/*.html`, `manifest.jsonl` |
| 4. Text extraction and pair building | `benchmark/build_items.py` | `benchmark/items_import.json` |
| 5. Import | `mgeoai annotate import-items` | `annotation/items.json`, `admin_meta.json` |
| 6. Labelling | web page "Benchmark annotation" | `annotation/labels/<name>.jsonl` |
| 7. Agreement and consensus | `mgeoai annotate agreement`, `export` | `agreement.json`, `gold.json` |

## The frozen benchmark
- Source: 5 browser-agent batches (100 groups, 245 articles). After robots checks, fetching
  and text extraction: **186 articles, 54 usable same-incident groups, 230 pairs**.
- Pairs: 134 same-incident (all pairs within a group of up to 3 articles; a random spanning
  tree for groups of 4, so every article is covered), 66 hard negatives (a decoy article
  against articles of the group it was meant to be confused with), 30 easy negatives (two
  unrelated incidents from the same region).
- 121 international and 109 Bangladesh pairs; 42 cross-language (Bangla/English) pairs.
- Reproducible: seed 20260101, `annotation/items.json` sha256
  `cb336e0be75dd984c877b1cd6068f5ebcc55f7af93c60976dfa14ce9208527ab`. Record the hash again
  in the paper's reproducibility notes. **Do not change the item set once labels exist.**

### Collection rules that matter for reporting
Pages were fetched only where robots.txt allowed, at least 3 s apart per site, with an
identifying user agent. Pages that returned 403 (bot blocking) were skipped, not worked
around. 43 articles were dropped (24 failed fetches, 19 empty or unreadable). The agent's
grouping was never trusted: it only proposed candidates.

## Roles
- **Annotators (4):** hamim, oishik, mubasshir, rubayet. They sign in with reviewer accounts.
- **Administrator:** runs setup, monitors progress, computes agreement, exports gold. The
  administrator must not label before the others have finished if they also annotate; the
  admin files `admin_meta.json` and `benchmark/scraps/` reveal the intended match or decoy
  status and must not be opened by annotators.

## Setup (once)
```bash
pip install -e '.[dev]'                      # from the MGeoAI repository root
cd web && npm install && npm run build && cd ..
mgeoai annotate init-users hamim oishik mubasshir rubayet
```
`init-users` writes, with permissions 0600 and without printing passwords:
`annotation/reviewers.json` (PBKDF2 hashes) and `annotation/initial_passwords.txt`.
Give each person only their own line, then delete the password file. Existing accounts are
kept on re-runs (use `--reset NAME` to re-issue); new names are merged in.

To rebuild the item set from scratch (only before any labels exist):
```bash
python benchmark/check_robots.py 'benchmark/scraps/candidates_b*.json' benchmark/robots_report.json
python benchmark/fetch_pages.py benchmark/robots_report.json benchmark/pages
python benchmark/build_items.py benchmark/scraps benchmark/pages benchmark/items_import.json
mgeoai annotate import-items benchmark/items_import.json
```
`import-items` refuses to overwrite once any `annotation/labels/*.jsonl` exists, unless
`--force` (which would orphan labels).

## Running the annotation server
```bash
export MGEOAI_REVIEWERS_JSON="$(cat annotation/reviewers.json)"
export MGEOAI_SESSION_SECRET="<32+ random characters, generated once, stored in a 0600 file>"
PYTHONDONTWRITEBYTECODE=1 mgeoai serve --host 127.0.0.1 --port 8000
```
Open `http://127.0.0.1:8000`, sidebar **Benchmark annotation**.

- A new `MGEOAI_SESSION_SECRET` at each start signs everyone out. Run **one** server process.
- `MGEOAI_REVIEWERS_JSON` replaces any other configured reviewers; merge the JSON if real
  reviewers exist. Annotators are reviewer accounts, so they can also use the review queue
  (approving a submission re-runs the pipeline on the served data).
- For several machines on a trusted network use `--host 0.0.0.0`. Over plain HTTP, passwords
  and cookies travel unencrypted. Otherwise use an HTTPS tunnel or proxy and set
  `MGEOAI_SECURE_COOKIES=true`. Each save reloads about 1.2 MB, slow over a remote link.
- There is no login lockout and no password-change page (fixed at issue; use
  `mgeoai hash-reviewer-password` for your own).
- **Do not serve a pipeline run over these pages from this server before labelling ends.**
  The Overview and Sources pages would show which articles the pipeline clustered.
- Allowed names match `^[a-z][a-z0-9_]{1,31}$`; any other reviewer name gets a 403 here.

### Interface
Each pair shows Report A and B (title, outlet, date, text, "Open original" link). Choose one
of four labels, add an optional note, press **Submit label** (**Update label** to edit).
Previous/Next move through the shuffled queue; the header shows `x/230 labelled`.

### API (for reference)
| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/reviewer/login`, `GET /api/reviewer/me`, `POST /api/reviewer/logout` | signed session cookie | shared reviewer login |
| `GET /api/annotate/items` | session | your queue, your own labels only |
| `PUT /api/annotate/labels/{item_id}` | session + `X-CSRF-Token` | save or edit one label |

## Data layout (`annotation/`, git-ignored)
```
items.json            served to annotators (item_id, left, right)
admin_meta.json       NEVER served: category, agent claim, difficulty, region, country, ...
reviewers.json        PBKDF2 hashes (0600)
initial_passwords.txt hand out, then delete (0600)
labels/<name>.jsonl   append-only; one record per save: item_id, label, notes, submitted_at, revision
```
The latest record per item and annotator is the label; earlier records give the edit history.
`annotation/` and `benchmark/pages/` hold secrets or third-party text, and
`benchmark/scraps/` reveals the intended match or decoy status; all three are git-ignored.
Commit `benchmark/scraps/` only after annotation closes.

## Monitoring
```bash
mgeoai annotate status            # x/230 per annotator
```
Send reminders based on counts only. Do not share anyone's label distribution while
labelling is in progress.

## After labelling: agreement and gold
```bash
mgeoai annotate agreement --output annotation/agreement.json
mgeoai annotate export --output annotation/gold.json        # --min-labels 3 by default
```
- `agreement`: Krippendorff's alpha (nominal) for the four labels and for same-vs-not, plus
  pairwise Cohen's kappa for the six annotator pairs. Rule of thumb: alpha of at least 0.80
  is good, 0.667 to 0.80 allows tentative conclusions, below that the guidelines or the
  items need review. Report both alphas and the per-pair kappas.
- `export`: strict-majority consensus of at least 3 labels. Same incident stays
  `same_incident`; Related, distinct and Different both become `different`; Cannot tell
  becomes `ambiguous` and is excluded from F1. Items without a strict majority are written to
  `gold.unresolved.json` with their votes; they are **not guessed**.
- Gold entries use the existing `golden_pairs.json` shape (`left`, `right`, `label`), with
  article IDs as `left`/`right` and the four-way label kept as `annotation_label`.

### Adjudicating unresolved items
After agreement is computed, the four annotators meet and resolve each unresolved pair by
discussion. Record the result in `annotation/adjudication.json` (`item_id`, final label,
one-line rationale) and cite it in the paper as adjudicated. A merge command for this file
is not built yet.

## Using the gold set (next work)
Gold pairs are **article** pairs; the pipeline evaluates **mention** pairs. To score it:
materialize the 186 pages as scraps (as `corpus-materialize` does, without labels), run the
pipeline, map article-pair labels to mention pairs, fill the baseline rows in
`ablation_metrics.csv` (T02), and bootstrap by incident. Run that pipeline output on a
separate machine or directory, never on the annotators' server.

## What to report in the paper
- Item counts, selection procedure, seed and sha256; drop-out numbers above.
- Agreement statistics with the guideline wording; share of unresolved and Cannot tell.
- Per-category results (positive, hard negative, easy negative; region; cross-language).
- Confidence intervals that resample incidents, not pairs.
- Limitations: candidates were found by a search agent, so selection bias remains (the
  international articles skew toward mass-casualty bus crashes); one language pair only;
  text-only and pre-extracted, no raw media; 58% of pairs are positives by design.

## Troubleshooting
| Symptom | Cause and fix |
|---|---|
| 503 "Reviewer sessions require MGEOAI_SESSION_SECRET" | Set a secret of 32+ characters. |
| 503 "Reviewer authentication is misconfigured" | `MGEOAI_REVIEWERS_JSON` is empty or not a JSON object of PBKDF2 hashes. |
| 401 after restart | Sessions are signed with the secret; a new secret invalidates them. |
| 403 "Annotator names must be..." | Reviewer name is not lowercase letters, digits or underscores. |
| 403 on save | Missing or wrong `X-CSRF-Token`; sign in again. |
| Page shows "No items" | `annotation/items.json` missing; run `import-items`. |
| `import-items` refuses | Labels exist; do not re-import (orphans labels) unless `--force`. |
| New `.pyc` changes in git | Run Python with `PYTHONDONTWRITEBYTECODE=1`. |
