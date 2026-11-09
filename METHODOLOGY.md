# Methodology

How MGeoAI turns news articles about road accidents into structured records, checks them against people, and
works out which articles describe the **same accident**. Written for readers who are not machine-learning
specialists: every technical word is explained the first time it appears, and the short glossary below collects them.

All numbers come from the public dataset
([`hamimmahmud0/mgeoai-road-accident-news`](https://huggingface.co/datasets/hamimmahmud0/mgeoai-road-accident-news))
and can be regenerated with one command (section 8). The system **fuses evidence; it does not decide what is true or
who is at fault.**

## Contents

1. [Words used in this document](#1-words-used-in-this-document)
2. [The articles](#2-the-articles)
3. [(a) How an article is prepared for the model](#3-a-how-an-article-is-prepared-for-the-model)
4. [(b) How the model was run](#4-b-how-the-model-was-run)
5. [(c) What the model is asked to find](#5-c-what-the-model-is-asked-to-find)
6. [How the answers are checked against people](#6-how-the-answers-are-checked-against-people)
7. [(d) Finding articles about the same accident](#7-d-finding-articles-about-the-same-accident)
8. [Reproducing everything](#8-reproducing-everything)
9. [Limits you should know about](#9-limits-you-should-know-about)

## 1. Words used in this document

| Term | Plain meaning |
|---|---|
| **LLM** (large language model) | A program that reads text and writes text in reply, such as DeepSeek, Qwen or MiniMax. We give it written instructions and an article; it answers. |
| **Prompt** | The written instructions given to the LLM. Ours are saved in the repository (`assets/`) and have a fingerprint (hash) so a result can be tied to the exact wording used. |
| **Inference** | Asking an LLM to answer. "Running inference on 244 articles" means making 244 requests. |
| **Token** | The unit an LLM reads and writes: roughly three-quarters of an English word, and more per word for Bengali. Limits and costs are counted in tokens. |
| **Temperature** | A dial for randomness. At 0 the model picks its most likely answer every time, which makes runs more repeatable. We use 0. |
| **Thinking** | Some models write hidden reasoning before the answer. It can improve accuracy but uses tokens. We keep the answer, never the reasoning. |
| **JSON** | A strict text format for structured data (`{"fatalities": 6}`) that programs can check. |
| **Schema** | The list of allowed fields and values for a JSON answer. An answer that breaks the schema is rejected. |
| **Annotator / annotation** | A person who reads an article and fills in the same fields by hand, without seeing any model answer (blind). |
| **Reference** | The annotation we treat as the correct answer when scoring: one annotation per article. Several articles have more than one annotation, which lets us measure how much people agree with each other. |
| **Precision / recall / F1** | Precision: of the pairs we called "same", how many really were. Recall: of the pairs that really were the same, how many we found. F1 combines the two (1.0 is perfect). |
| **Confidence interval (CI)** | A range that shows how much a number could move if we had collected different articles. A wide range means "do not over-read this". |
| **Bootstrap** | A way to get that range: repeat the scoring many times on re-drawn samples of the data. |
| **Geocoding** | Turning a place name ("Daulatdia ferry terminal, Rajbari") into map coordinates. |
| **TF-IDF** | A classic word-counting similarity score. It rewards words two texts share, and rewards rare words more than common ones. |

## 2. The articles

- **244 articles**, 102 publishers, 208 in English and 36 in Bengali; 124 about Bangladesh, 120 about other countries.
- They were collected by hand and with a browser agent, saved as web pages, and grouped into **100 incidents** (1 to 4
  articles each; 192 articles belong to a real shared incident, 52 are look-alike "decoys" added on purpose to make the
  grouping test harder). The browser agent proposed the groups and **people then checked them**.
- The saved pages are the source material. They are not redistributed (they belong to the publishers).

## 3. (a) How an article is prepared for the model

A saved web page is mostly not the article: it has menus, ads, "related news" lists, scripts and a header showing
today's date. Feeding it all to a model wastes tokens and invites mistakes (for example, picking up a related
headline's death toll). Each page goes through these steps (`src/traffic_fusion/extraction/prepare.py`):

1. **Clean the HTML.** Remove scripts, styles, forms, buttons, embedded frames and vector graphics. Scripts are never
   executed. For the markdown version also remove navigation bars, page headers, footers and sidebars.
2. **Convert to markdown.** Markdown is plain text with light formatting (headings, paragraphs, links). It keeps the
   article's reading order and is much shorter than HTML. This is the form used for all published runs.
3. **Add the publication time, when known.** Taken from the page's own metadata or the search record, and placed in a
   labelled `PAGE_METADATA` block with a warning that it may be wrong and is *not* the accident date. It exists only so
   the model can turn "last night" or "on Friday" into a date.
4. **Attach images (some runs).** Up to 6 images per article are downloaded (junk such as logos and icons is filtered;
   each file is capped at 5 MB). At most 3 are sent to the model, shrunk so the longest side is 1,024 pixels where the
   model needs that. Image content may help describe the scene but is never allowed to set a death toll.
5. **Wrap the article as data.** The text is put between `<ARTICLE_SOURCE>` and `</ARTICLE_SOURCE>` markers, and the
   prompt says that everything inside is data, not instructions. This blunts *prompt injection*, where a web page
   contains text such as "ignore your instructions". The model's answer must still pass the schema, so a hijacked
   answer is rejected rather than trusted.
6. **Cap the length.** Very long pages are cut at 400,000 characters (raw HTML) before sending.

What is **never** sent to a model: annotator answers, group ids, or anything that reveals which articles belong
together. Models see one article at a time when extracting.

## 4. (b) How the model was run

**One request per article.** The prompt (`assets/mllm_prompts/accident_extraction_prompt.md`, versioned and hashed)
tells the model to (1) find the article body and ignore menus and related headlines, (2) decide whether the article
reports a specific road accident, (3) fill in the fields in section 5, and (4) answer with JSON only.

**Providers and runs.** Calls go directly to each provider's API. No key is ever written to disk or the logs.

| Run | Model | Input | Settings |
|---|---|---|---|
| `deepseek__deepseek-flash__markdown__txt` | DeepSeek `deepseek-flash` | markdown | thinking on, up to 393,216 output tokens, temperature 0 |
| `deepseek__deepseek-flash__markdown__txt__meta` | DeepSeek `deepseek-flash` | markdown + publication time | same |
| `custom__qwen3-8-27b__markdown__img__meta` | Qwen 27B (self-hosted, OpenAI-compatible) | markdown + time + images | 8,192 output tokens, thinking off |
| `openrouter__minimax-minimax-m3-1-flash-free__markdown__img` | MiniMax (free tier via OpenRouter) | markdown + images | 524,288 output tokens |

**Failures are visible, never hidden.** A failed call stays `failed` and can be retried; the system never silently
falls back to another model. Transient errors (timeouts, rate limits, server errors) are retried up to twice with
waiting in between. If the model runs out of output tokens before finishing its JSON, the article is marked
truncated and the message says to raise the cap or turn thinking off. Up to 50 articles run in parallel.

**Every answer is checked.**
- The JSON must match the schema (allowed field names, number ranges, date format, vehicle vocabulary).
- Each *evidence quote* the model gives must appear word for word in the article. The share that does is reported per
  run (88-98 %). This catches invented support, and does not catch a wrong reading of real text.
- Token counts and time per article are stored. Cost is recorded only if a price was entered by hand; otherwise cost
  is "unknown", and `:free` models cost $0. Token limits always apply.

**Cost note.** DeepSeek's 244-article run used about 13 seconds per article on average; the self-hosted Qwen run about
78 seconds; the free MiniMax tier about 45 seconds and many requests were refused (only 72 of 215 attempted articles
succeeded), so its scores cover those 72.

## 5. (c) What the model is asked to find

For each road accident in the article, the model fills the same fields a person does. `null` means "the article does
not say"; it is never a guess.

| Field | What it means | Rule the prompt gives |
|---|---|---|
| `accident` | Is this a specific, real road accident? | `false` for statistics roundups, policy news, old court cases, non-road incidents |
| `fatalities` | People killed | The article's latest explicit figure, including later hospital deaths |
| `casualities` | People killed **or** injured (spelling kept from the original schema) | Killed plus surviving injured, no double counting; vague "many injured" uses the known minimum |
| `vehicles` | Vehicle types involved | From a fixed list (car, bus, truck, motorcycle, CNG autorickshaw, …) or `other:<name>` |
| `date` | When the accident happened | Not the publication time; relative terms resolved from the dateline; ISO format with local timezone |
| `country` | Where | Full English name |
| `location` | Where, most to least specific | Only parts the article states |
| `longitude and latitude` | Coordinates | **Only** if printed in the article. Never from memory |
| `evidences` | Proof | A verbatim quote for every non-null field, with a one-line note when a value was derived |

An article reporting several accidents returns several records. The model is told **never to infer fault, sentiment or
precise coordinates**. Victim names are not extracted.

**Placing incidents on the map** (a later, separate step): the articles of each group found by `cluster-cards` are read together
by DeepSeek and summarised in at most 70 words (a *fusion*; source disagreements such as different death tolls are
listed, not hidden), the place is looked up with OpenStreetMap's Nominatim, and
the result is shown as a **place centre with an uncertainty radius**, not a crash coordinate. Country-level answers are
discarded; 97 of 100 incidents were placed.

## 6. How the answers are checked against people

People filled the same fields from scratch, blind to any model output (3 annotators; 328 annotations; every one of the
244 articles has at least one, 82 have two or more). For scoring, one annotation per article is the reference (the
annotator who labelled most articles, ties broken by name).

- **How much people agree** (82 doubly-annotated articles; exact match): fatalities 97.7 %, country 91.8 %, date 87.1 %,
  casualties 78.8 %, vehicles 35.3 %, location 0 %. Exact free-text match is almost impossible ("Kabirhat Road" vs
  "Kabirhat-Basurhat Road"), so a looser word-overlap measure is also shown on the website.
- **How well models match the reference** (accident flag F1 99.4-100 %; fatalities 96.5-97.8 % exact; country 95.5-97.8 %;
  date 63-83 %, much higher when the publication time is supplied, e.g. DeepSeek 63.3 % to 81.0 %; casualties 60-76 %;
  vehicles 60-61 %). Each number has a confidence interval in `model_performance.json`.
- **The accident flag cannot be properly tested here**: all 244 articles were chosen because they report an accident,
  so there are no "not an accident" examples to separate. Agreement statistics for it are undefined.

## 7. (d) Finding articles about the same accident

**The question.** News about one accident appears in many outlets, languages and updates. Which articles report the
same accident? This matters for counting accidents once and for fusing facts. Death tolls rise over time and early
reports are wrong, so equal numbers are not required to be "the same".

**What counts as "same".** The same crash: same vehicles, place and time. Articles may differ in language, wording,
detail and toll. Two crashes of the same kind on the same road, in the same city or on the same day are **different**
unless the details match. A follow-up event such as a road blockade is "related but distinct".

### 7.1 How the test was set up (shared by every method)

- **Reference.** The 100 incident groups described in section 2.
- **Test pairs.** Checking all 29,646 possible article pairs with an LLM would be costly and mostly pointless (most pairs
  are obviously unrelated). So a fixed sample of **973 pairs** was drawn: all 232 truly-same pairs plus 741 different
  pairs from four groups: *decoy* (a look-alike crash chosen to confuse), *near* (same country, published within 4 days),
  *similar* (the most word-similar articles) and *random*. Scores are **re-weighted** to represent all 29,646 pairs, so
  hard pairs do not inflate the result.
- **Frozen in advance.** The sample, the prompts and the decision rule were fixed and fingerprinted
  (`bc70f312…`) *before* any model call, so nothing could be tuned after seeing results.
- **The two-order rule.** A pair-judging model sees articles in order (A, B) and again as (B, A). A pair counts as
  "same" only if **both** answers are `same_incident`. This blocks answers that depend on which article came first.
- **Settings.** DeepSeek `deepseek-flash`, temperature 0, thinking on.
- **Error bars.** 95 % bootstrap intervals, re-drawing whole incident groups (articles of one incident are not
  independent).

### 7.2 Method 1: pair judge on the full articles (`pair-full`)

**How it works.** For a pair, the model reads both articles in full (publisher, date, title, first 12,000 characters)
and answers: `same_incident`, `different_incident`, `related_distinct`, or `uncertain`, with a confidence, short
word-for-word quotes from each article, and a two-sentence reason. Then the pair is judged again swapped.

**Result.** Precision 100 %, recall 99.1 %, F1 99.6 %. Even English-vs-Bengali pairs (recall 98.1 %) and pairs whose
death tolls differ (96.8 %) were found. 94 % of the quotes given were genuinely in the article.

**Example that works.** *The Daily Star* (English): "At least 18 killed as bus plunges into Padma" and *Prothom Alo*
(Bengali): "Two bodies recovered after a bus fell into the Padma". Different language, toll 18 vs 2. The model matched
them through the operator, place, time and named victims, and read the toll gap as a later update.

**Example that fails.** A roundup titled "Five national-minority men among seven killed in road accidents" covers
several crashes; one matches a Naogaon dump-truck article. One order said "same", the swapped order said "uncertain",
so the both-orders rule called it "different".

| Advantages | Disadvantages |
|---|---|
| Most accurate and easiest to trust: it reads everything and shows quotes you can check | Most expensive: 3.8 M input and 0.8 M output tokens for the 973 pairs |
| Handles languages, wording changes and revised tolls | Cost grows with the *square* of the number of articles if run on all pairs |
| Gives a reason for every decision, which helps audit | Long articles are cut at 12,000 characters |
| | Roundup articles that mention several crashes can confuse it |

### 7.3 Method 2: pair judge on extracted fields only (`pair-fields-*`)

**How it works.** The model never sees article text. It sees the publication date and the extracted records
(fatalities, killed-or-injured, vehicles, date, country, location). Three variants test where the information comes
from: the **human** record only, the **model** record only, or **both**. The instructions are the same as Method 1
with two changes: fields may be wrong or missing, and `null` must never be treated as a match.

**Result.** Both records: F1 98.9 %. Human only: 97.6 %. Model only: 95.8 %, with 3.1 % of decoy pairs wrongly matched.
Cost: about 40 % of Method 1's input tokens (1.5 M vs 3.8 M for the both-records variant).

**Example that works.** The same Padma pair seen only as fields: same time (25 Mar 2026, 17:15), a bus, and the
Daulatdia ferry pontoon in Rajbari; toll 18 vs 2 was explained as a later update.

**Example that fails.** Two reports of a Noakhali crash on 4 Nov 2025 (six dead). One field record says "Islamia Senior
Madrasa, Kabirhat-Basurhat Road, 14:15, CNG autorickshaw", the other "Kabirhat Alim Madrasa, Sonapur-Companiganj Road,
14:30, battery autorickshaw". Each record is faithful to its article, but without the text the model concluded they
were two crashes.

| Advantages | Disadvantages |
|---|---|
| Cheaper and faster; the structured fields can be stored and reused | Only as good as the extraction: a wrong or missing field leads to a wrong answer |
| Needs no article text, so it can be shared and re-run on the public dataset | Cannot tell when two sources describe the same event with differently-reported details |
| Shows how much of the decision the fields alone carry | Roundups produce a confusing record and false matches (model-only variant) |
| | An article with no extracted fields ends up "uncertain" |

### 7.4 Method 3: cluster everything at once (`cluster-cards`, `cluster-full`)

**How it works.** Instead of judging pairs, the model reads **all 244 articles in one request** and sorts them into
groups. Each article is a short *card* with an opaque id (A001, A002, …) in an order shuffled by a fixed seed, so
neither position nor id carries information. Every id must appear exactly once and single-article groups are allowed.
Two variants:
- `cluster-cards`: publisher, date, title, the first 350 characters, and the extracted records (cost: 82 k input and
  17 k output tokens per run).
- `cluster-full`: publisher, date, title and the first 4,000 characters, with no extracted fields (169 k and 21 k).

Each variant is run **three times** with different shuffles. A *consensus* groups two articles if they were together in
at least two of three runs. The response is validated (unknown or duplicate ids counted and dropped, missing ids become
single-article groups; none occurred).

**Result.** `cluster-cards` recovered all 100 groups exactly in all three runs (F1 100 %). `cluster-full` consensus
F1 99.6 %: one group was split in two runs, and it is the roundup article again.

**Example that works.** Four reports of a 23 Jul 2025 crash in Natore, in two languages, with tolls of 6, 7 and 8, were
placed together in every run of both variants.

**Example that fails** (`cluster-full`). The roundup was left alone in two runs while two Bengali articles on the
Naogaon crash were grouped together.

| Advantages | Disadvantages |
|---|---|
| By far the cheapest: one call covers every pair (even with three runs, about 1/15 of Method 1's tokens) | The model must hold all articles in mind at once: this limits how many articles fit in one request |
| Sees the whole picture, so it can use transitivity (if A=B and B=C then A=C) | Answers depend on the order shown, hence three shuffled runs and a consensus |
| Gives groups directly, ready for the map | Little explanation per decision; harder to audit one pair |
| | A single mistake can merge or split several articles |

### 7.5 Baselines (no LLM)

**TF-IDF word similarity.** Compares title plus first 1,500 characters. Two articles are "same" if their similarity is
above a threshold. The threshold was tuned on this same sample, so the result is **optimistic**. Precision 19.1 %,
recall 63.4 %, **F1 29.3 %**. Advantages: free, instant, language-independent in principle. Disadvantages: an English
article and a Bengali article about the same crash share no words (similarity 0.00), while two different crashes from the
same site can score 0.96 because of repeated page boilerplate.

**Fields rule.** Using the model's extracted records: same if both articles have exactly one accident, the same country,
dates at most one day apart, and location words overlapping (at least 30 %). Fixed in advance. Precision 99.1 %, recall
49.6 %, **F1 66.1 %**. Advantages: transparent and cheap; almost never wrong when it says "same". Disadvantages: misses
half of true matches because different outlets name different landmarks for the same crash; generic words ("area",
"highway") can cause false matches.

### 7.6 Side-by-side

| Method | Reads | Precision | Recall | F1 | Tokens (in / out) |
|---|---|---|---|---|---|
| `pair-full` | full text | 100 % | 99.1 % | 99.6 % | 3.78 M / 0.76 M |
| `pair-fields-both` | extracted fields (human + model) | 100 % | 97.8 % | 98.9 % | 1.49 M / 0.46 M |
| `pair-fields-human` | human fields | 100 % | 95.3 % | 97.6 % | 1.14 M / 0.45 M |
| `pair-fields-model` | model fields | 97.3 % | 94.4 % | 95.8 % | 1.13 M / 0.50 M |
| `cluster-cards` (consensus) | 350-char lead + fields | 100 % | 100 % | 100 % | 0.25 M / 0.05 M (3 runs) |
| `cluster-full` (consensus) | 4,000 chars | 100 % | 99.1 % | 99.6 % | 0.51 M / 0.07 M (3 runs) |
| TF-IDF baseline | title + 1,500 chars | 19.1 % | 63.4 % | 29.3 % | none |
| Fields rule baseline | model fields | 99.1 % | 49.6 % | 66.1 % | none |

**What this supports, and what it does not.** All LLM methods are far better than the word-counting and rule baselines,
particularly across languages and for revised tolls. The LLM methods are **within each other's error bars**, so this
benchmark cannot rank them: the reference groups were proposed by an AI agent (then human-checked), the hard negatives were chosen by the same
agent, and no pair was found that every method contradicted. A perfect score means "agrees with the reference", not
"correct". Harder items (same-day same-city crashes, follow-up articles, roundups) are needed to
separate the methods. Per-pair answers and explanations are public, so anyone can inspect the disagreements.

## 8. Reproducing everything

```bash
pip install git+https://github.com/hamimmahmud0/MGeoAI
mgeoai x reproduce --dataset hamimmahmud0/mgeoai-road-accident-news --output reproduced/
# or: scripts/reproduce_reports.sh
```

This downloads the public dataset and regenerates the annotation score, model performance, grouping benchmark report,
model-versus-annotator report and the incident map data, then compares the grouping numbers with those published.
No article text and no API key is needed. Re-running the *models* (not just the scoring) needs the article text, which
you must fetch from the publishers using the URLs in `articles.jsonl`.

## 9. Limits you should know about

- **Small, hand-collected set.** 244 articles chosen on purpose; rates do not describe the news in general.
- **The reference is human-checked but not independent of the agent.** The agent found the groups and chose the hard
  negatives; people checked them. A blind spot shared by the agent and the models could remain.
- **Mostly one annotator per article.** Reference quality is limited by that; 82 articles have two or more annotations,
  which is how agreement is measured.
- **No negative examples for the accident flag** (see section 6).
- **Place coordinates are place centres**, from OpenStreetMap, with a stated uncertainty. They are not crash sites.
- **Model results depend on the day.** Providers update models; records store the run settings and prompt hashes so a
  re-run can be compared, but identical output is not guaranteed.
- **No fault or sentiment.** Nothing here decides who caused an accident or how anyone feels about it.
