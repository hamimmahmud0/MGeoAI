# Same-accident grouping benchmark: how to reproduce it

Question: can an LLM tell which news articles report the **same** road accident? Reference ("gold") = the browser
agent's 100 groups (`meta.json:admin.group_id`). They are **not human-verified**, so every result is *agreement with those
groups*, not accuracy.

## One command

```bash
export DEEPSEEK_API_KEY=...                       # never put the key on a command line or in a file in the repo
scripts/run_grouping_benchmark.sh /path/to/extraction-root            # dry run: checks data, prints token/cost projection
scripts/run_grouping_benchmark.sh /path/to/extraction-root --yes      # runs everything (about 8.3M tokens in, 2.3M out, ~$3-5)
# equivalent: mgeoai x group-benchmark --root /path/to/extraction-root --yes
```

Options: `--methods pair-full,cluster-cards,...`, `--concurrency 25`, `--repeats 3`, `--token-limit 8000000` (hard stop per
method), `--refresh-pairs` (rebuild and re-freeze the pair set, which invalidates earlier results),
`--skip-annotation-check`.

## Inputs the extraction root must contain
- `articles/<id>/{meta.json, article.md, ...}`: the 244 saved articles (`meta.json:admin.group_id` and `.country` are used).
- `labels/*.jsonl`: annotations. **Every article needs at least one** (the run refuses to start otherwise). The human record
  for each article comes from the first of oishik, mubasshir, hamim who labelled it.
- `runs/deepseek__deepseek-flash__markdown__txt__meta/`: the model extraction used for the "model fields" inputs.
- `benchmark/scraps/candidates_b0[1-5].json` in the repo checkout (group kinds and `decoy_for`).
All of these are in the Hugging Face bucket `hamimmahmud0/mgeoai-backup` under `latest/` (see its README).

## What the command does
1. **Coverage check**: every article has >= 1 annotation.
2. **Frozen pair set**: if `matching/pairs.json` exists its sha256 must equal `matching/pairs.sha256`, otherwise the run stops.
   If it does not exist it is built with seed `20261109`: all 232 within-group pairs plus 741 sampled negatives in four strata
   (decoy-vs-main group; same country with publication date within 4 days; TF-IDF nearest neighbours; random). Negatives are
   sampled, so scores are re-weighted to the full 29,646-pair population.
3. **Methods** (each resumable: existing good replies are reused, failed calls get a second pass):
   - `pair-full`: the model reads both articles (12,000 characters each).
   - `pair-fields-both|human|model`: the model sees only extracted fields (annotator record and/or model extraction).
   - `cluster-cards`: the model groups all articles from compact cards (title, lead, fields); 3 shuffled runs.
   - `cluster-full`: the same from full texts (4,000 characters each); 3 shuffled runs.
   Every pair is judged in both orders (A,B) and (B,A). **A pair is predicted SAME only if both orders say `same_incident`**
   (fixed before any call). Model: DeepSeek `deepseek-flash`, temperature 0, thinking on, 16k output cap per pair call.
4. **Scoring**: re-weighted precision, recall and F1 with 95% intervals from resampling whole incident groups (1,000
   resamples); false-SAME rate per negative stratum; recall for cross-language pairs and pairs whose death tolls differ; order
   inconsistency; clustering pair F1, B-cubed F1, ARI, groups recovered exactly, merged and split groups; two baselines (tf-idf
   with a threshold tuned on the same sample, which is optimistic; and a fixed country/date/place rule on the model fields).
5. **Outputs** in `<root>/matching/`: `report.html` (full, private: names articles), `results.json`, `public_summary.json`
   (aggregates only, published on the website), `run_manifest.json` (git commit, versions, seeds, prompt hashes, settings,
   token use, pair-set hash), plus every raw reply under `pair-*/` and `cluster-*/`.

## Repeatability and its limits
- Re-running with the same root resumes from disk: no new API calls, same scores (this takes seconds).
- A fresh run (empty `matching/` except the frozen pair files) re-calls the model. LLM output is not bit-for-bit
  repeatable even at temperature 0, so expect small differences; the stored replies are the record of what was measured.
- Changing a prompt, the pair set, a seed or the label data changes the results: compare `run_manifest.json`
  (`prompt_sha256`, `pairs_sha256`, `label_lines`, `git_commit`) between runs.
- The tests (`tests/test_extraction.py`: `test_group_benchmark_*`) exercise the whole pipeline offline with a mocked model.

## Publishing
`public_summary.json` carries no article ids, titles, links, group ids or pair ids. The website serves it at
`/api/x/public/grouping` and shows it on the "Same-accident grouping" page. Deploy it by copying `matching/public_summary.json`
into the server's `extraction/matching/` directory (no restart needed).
