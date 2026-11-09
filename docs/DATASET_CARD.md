---
license: cc-by-4.0
pretty_name: MGeoAI Road-Accident News (annotations, model extractions, same-accident grouping)
language:
- en
- bn
task_categories:
- text-classification
- token-classification
tags:
- road-accidents
- news
- information-extraction
- event-deduplication
- geospatial
- bangladesh
size_categories:
- 1K<n<10K
configs:
- config_name: articles
  data_files: data/articles.jsonl
- config_name: annotations
  data_files: data/annotations.jsonl
- config_name: model_extractions
  data_files: data/model_extractions.jsonl
- config_name: grouping_pairs
  data_files: data/grouping_pairs.jsonl
- config_name: grouping_pair_predictions
  data_files: data/grouping_pair_predictions.jsonl
- config_name: grouping_clusters
  data_files: data/grouping_clusters.jsonl
- config_name: grouping_embedding_baseline
  data_files: data/grouping_embedding_baseline.jsonl
- config_name: incidents
  data_files: data/incidents.jsonl
---

# MGeoAI Road-Accident News

Human and machine readings of **244 news articles about road accidents** (124 from Bangladesh, 120 from other
countries; 208 English, 36 Bengali), plus a benchmark for deciding **whether two articles report the same
accident**, and 100 fused, map-ready incident summaries.

> **The article text and images are not included.** They belong to the publishers. Every article is identified by
> its URL, publisher, title and date so you can fetch it yourself. Everything else here is our own work.

Code, website and methodology: <https://github.com/hamimmahmud0/MGeoAI> (see `METHODOLOGY.md`).
Live site: <https://mgeoai.cartmind.xyz>.

## What is in the dataset

| File (`data/`) | Rows | What it holds |
|---|---|---|
| `articles.jsonl` | 244 | One row per article: URL, publisher, title, date, language, collection country and region, and the **reference group** (`reference_group_id`) the article belongs to. |
| `annotations.jsonl` | 328 | Human annotations (3 pseudonymous annotators). At least one per article. |
| `model_extractions.jsonl` | 947 | What each language model extracted from each article, across 4 runs. |
| `grouping_pairs.jsonl` | 973 | The frozen sample of article pairs used to test same-accident methods, with the reference label. |
| `grouping_pair_predictions.jsonl` | 7,784 | Every answer of every pair-judging method (both presentation orders). |
| `grouping_clusters.jsonl` | 6 | Each "cluster everything at once" run: the groups the model returned. |
| `grouping_embedding_baseline.jsonl` | 1,946 | Cosine similarity of every sampled pair under two multilingual embedding models (LaBSE, multilingual E5), the scores behind the embedding baselines. |
| `incidents.jsonl` | 100 | One fused summary per group of articles, with a place lookup (97 placed on the map). |
| `grouping_meta.json` | 1 | Sampling seed, decision rule, population sizes, model settings, prompt hashes, token totals. |
| `expected_results.json` | 1 | Headline numbers, used by the reproduction script to check itself. |

### Annotation fields (`annotations.jsonl`, `model_extractions.jsonl`)

Each row has a list of `accidents` (an article can report several). Per accident:
`accident` (true/false), `fatalities`, `casualities` (the spelling is kept from the original schema; it means
*people killed or injured*), `vehicles` (from a fixed vocabulary, or `other:<name>`), `date` (ISO 8601),
`country`, `location` (free text), `coordinates` (`"lat,lon"` only when stated or marked by the annotator).
`null` means *the article does not say*; it is never a guess. No fault, blame or coordinates are inferred.

`annotations.jsonl` adds `annotator` (`annotator_1` … `annotator_3`), `revision`, `unusable` (page is not an
article), and per-image descriptions. `model_extractions.jsonl` adds the run settings (`provider`, `model`,
`input_set`, `with_images`, `with_meta`, `thinking`), `status` (`ok` / `failed` + `error_kind`), token counts,
latency, and `quote_check` (how many of the evidence quotes the model gave were found word for word in the article).

### Grouping benchmark

`grouping_pairs.jsonl` is a sample of 973 pairs (232 same-accident, 741 different) drawn from 29,646 possible
pairs, stratified so that the hard cases (look-alike accidents, same-day same-country decoys) are over-represented.
`label` is `same` or `different`, derived from `group_a == group_b`. Each pair has `stratum`, `tfidf`
(word-overlap similarity), `same_publisher`, `cross_language`, `toll_differs`.
Methods in `grouping_pair_predictions.jsonl`: `pair-full`, `pair-fields-both`, `pair-fields-human`,
`pair-fields-model`. Methods in `grouping_clusters.jsonl`: `cluster-cards`, `cluster-full` (3 runs each, different
article orders). A method name with a suffix (`pair-full@openrouter-...`) marks a second model that answered the same
questions; `grouping_meta.json` lists these under `extra_models` with call and token counts. The embedding baselines
are computed from `grouping_embedding_baseline.jsonl` (two variants each: threshold tuned on the whole sample, or
learned on held-out folds of accident groups). `expected_results.json` holds the headline scores.

## Reproduce every report

```bash
pip install git+https://github.com/hamimmahmud0/MGeoAI
mgeoai x reproduce --dataset hamimmahmud0/mgeoai-road-accident-news --output reproduced/
```

This downloads the dataset and regenerates: `annotation_scores.json`, `model_performance.json`,
`grouping_results.json` + `grouping_report.html`, `model_vs_annotators.html`, and `incidents.geojson`, then checks
the grouping numbers against `expected_results.json`. No API key and no article text is needed.

## Read this before using the numbers

- **One annotation per article is the reference.** It is the annotation of the first annotator, in a fixed order, who
  labeled the article. In this file the annotators are numbered in that order (`annotator_1` first), so the reference
  of an article is the lowest-numbered annotator who labeled it. Some articles have two or more annotations; the model
  scores in the paper use only the reference annotation.
- **The accident flag has no variance.** Every one of the 244 articles was selected because it reports an accident,
  so agreement statistics for that flag (kappa, alpha) are undefined. Do not use this set to test "is this an accident?".
- **The grouping reference was human-checked, but is still a reference.** A browser agent collected the articles and
  proposed the same-accident groups; people then checked them. The agent also chose the hard negatives, so a blind
  spot shared by the agent and the models is possible. Scores near 1.0 mean agreement with this reference, not
  proof of perfection.
- **Selection bias.** Articles were collected on purpose (hand-picked searches, decoys for hard cases). Rates here
  do not describe news coverage in general.
- **The 244 articles are small.** Per-field confidence intervals are in `model_performance.json`.
- **One free-model run is incomplete** (`openrouter__minimax-…-free`: 72 of 215 attempted articles succeeded because
  of free-tier limits). Its scores cover only those articles.
- `published_at` is stored as scraped; a few rows hold a Unix timestamp in milliseconds instead of ISO text.

## What was removed, and why

Article text, HTML, images, and the quotes models copied from them (copyright). Annotator account names (replaced by
`annotator_N`), free-text annotator notes, and submission times (privacy). Raw model replies and hidden reasoning.
The export script refuses to write if a real account name or an article body slips through.

## Licence and attribution

Annotations, model extractions, grouping labels/predictions and incident summaries: **CC BY 4.0**.
Titles, URLs and publishers are factual metadata about third-party articles and stay with their owners.
Place coordinates in `incidents.jsonl` come from **OpenStreetMap Nominatim**: © OpenStreetMap contributors, data
under the **ODbL**; they are place centres (with an uncertainty radius), never crash coordinates.
Model extractions were produced with DeepSeek (`deepseek-flash`), a Qwen 27B model and a MiniMax free model through
OpenRouter; check each provider's terms if you reuse their outputs commercially.

## Ethics

The articles describe real deaths. This dataset records reported facts and does not infer fault, sentiment, or
identities. Victims' names are not extracted. Please keep it that way.

## Citation

```bibtex
@dataset{mgeoai_road_accident_news_2026,
  title  = {MGeoAI Road-Accident News: annotations, model extractions and same-accident grouping},
  author = {hamimmahmud0 and contributors},
  year   = {2026},
  url    = {https://huggingface.co/datasets/hamimmahmud0/mgeoai-road-accident-news}
}
```
