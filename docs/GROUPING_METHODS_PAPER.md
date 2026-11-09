# Same-accident grouping: method descriptions with worked examples

Draft text for the paper. All numbers are agreement with the browser agent's 100 incident groups (not human-verified), on a
frozen sample of 973 article pairs (232 same-incident, 741 different) re-weighted to the 29,646 possible pairs; intervals are 95%
bootstrap intervals over incident groups. Model: DeepSeek `deepseek-flash`, temperature 0, thinking on. Examples are real items
from the benchmark (article titles shortened).

## Shared setup
**Task.** Given news articles about road accidents, decide which articles report the *same* accident. The 244 articles cover
100 incidents (1 to 4 articles each, Bangladeshi and international, English and Bangla). **Pairs.** All 232 within-group pairs
plus negatives from four strata: *decoy* (a similar crash chosen to be confusable with an incident), *near* (same country,
publication dates within four days), *similar* (TF-IDF nearest neighbours) and *random*. **Order rule.** Each pair is judged
twice, with the articles in both orders; it is predicted *same* only if both answers are `same_incident`. The sample, the prompts
and this rule were frozen before any model call (pair-set hash `bc70f312…`).

## Method 1. Pair judge on full articles (`pair-full`)
**Algorithm.** For a pair (A, B) the model receives, for each article, the publisher, publication date, title and the cleaned
article text (first 12,000 characters), wrapped in delimiters that mark it as untrusted data. The instructions define the
decision: *same incident* means the same crash (same vehicles, place and time) and explicitly allows articles to differ in
language, wording, detail and casualty numbers, because tolls rise and early reports are wrong; two crashes of the same kind on
the same road, in the same city or on the same day are different incidents unless the details match; *related but distinct*
covers directly connected events (a blockade or court case); *uncertain* is reserved for genuinely undecidable pairs. The model
returns JSON with a decision, a confidence, verbatim evidence quotes from each article and a two-sentence rationale. The pair is
presented a second time with A and B swapped, and the final label follows the order rule. 94% of quoted evidence (4,421 of
4,721) appears verbatim in the article, which makes the judgements auditable.
**Result.** Precision 100%, recall 99.1%, F1 99.6% [99-100]; no false match in any negative stratum; recall 98.1% on
cross-language pairs and 96.8% on pairs whose death tolls differ; 0.4% of pairs got different answers in the two orders.

**Working case.** The Daily Star (English, 26 Mar 2026) "At least 18 killed as bus plunges into Padma" and Prothom Alo
(Bangla, 25 Mar 2026) "Two bodies recovered after a bus fell into the Padma; rain hampers rescue". The languages differ and the
death toll is 18 versus 2. Both orders answered `same_incident` (confidence 0.99): "Both reports describe the same Souhardo
Paribahan bus falling from the Daulatdia ferry terminal pontoon into the Padma around 5:15pm, and they name the same two initial
victims; Article A is a later update with a higher death toll." The model used shared specifics (operator, place, time, named
victims) and treated the toll gap as an update.

**Failure case.** New Age (31 Jan 2026) "Five national-minority men among seven killed in road accidents" versus Khulna Gazette
(Bangla) "Five killed by a dump truck in Naogaon". The first article is a roundup of several crashes of which one matches the
second. With the pair in order (A, B) the judge said `same_incident` and noted that the shared five-victim crash matches; with the
articles swapped it said `uncertain` (confidence 0.5). Under the both-orders rule the pair counts as *different* and is a missed
positive. The failure is order instability on a multi-incident roundup, not a wrong belief about the facts; a rule such as "same
if either order says same" would recover it but would have been chosen after seeing the data, so it was not used.

## Method 2. Pair judge on extracted data only (`pair-fields-*`)
**Algorithm.** The model never sees article text. For each article it receives the publication date and up to two extracted
records: the annotator's record (fatalities, killed-or-injured, vehicles, date, country, location, coordinates) and the record
extracted by the LLM from the same article (`both`); two ablations give only the annotator record (`human`) or only the model
record (`model`). The instructions are those of Method 1 with two changes: fields can be wrong or missing, null means not stated,
and missing values must not be assumed to match; no evidence quotes are requested. Both orders and the same order rule are used.
This method asks how much of the decision is carried by the structured fields alone, and costs about a third of the tokens
(1.5M versus 3.8M input tokens for the whole sample).
**Result.** `both`: F1 98.9% [98-100]; `human` only: 97.6%; `model` only: 95.8% [92-98] with 3.1% of decoy pairs wrongly matched.

**Working case.** The same Padma pair as above, seen only through fields: both records give 25 Mar 2026 17:15, a bus, and a place
at the Daulatdia ferry pontoon in Rajbari; fatalities 18 versus 2. Both orders `same_incident` (confidence 0.95): "The matching
time, exact ferry-terminal location and bus involvement indicate the same incident; the large casualty discrepancy is best
explained by a later updated toll."

**Failure cases.** (a) *Details that the sources themselves disagree on.* Two reports of a 4 Nov 2025 Noakhali crash with six
dead (Bangladesh Sangbad and Prothom Alo). The annotator recorded "in front of Islamia Senior Madrasa, Kabirhat-Basurhat Road,
14:15, CNG autorickshaw" for one and "in front of Kabirhat Alim Madrasa, Sonapur-Companiganj Road, 14:30, battery autorickshaw"
for the other. Each record is faithful to its article, but the judge, seeing only the fields, concluded "the specific road,
madrasa, time and vehicle type differ, indicating two separate crashes" (human-only and both-fields variants both missed it).
The article text is needed to see that one is a loosely reported version of the other. (b) *Roundup articles in the model-only
variant.* Sky News "More than 30 killed in Bolivia bus crash" mentions several crashes, so its extracted record contains one that
matches BBC's report of a different crash; the model-only judge answered `same_incident` in both orders, a false match against
the group label (the roundup does mention that crash, so this pair may itself be a labelling ambiguity). (c) *Missing fields.*
A New Age article had no extracted fields, and the judge answered `uncertain` in both orders for three of its true matches.

## Method 3. LLM clustering of the whole corpus (`cluster-cards`, `cluster-full`)
**Algorithm.** Instead of judging pairs, the model sees all 244 articles at once and partitions them. Each article becomes a
numbered *card* with an opaque short id (A001, A002, …); the card order is shuffled per run with a fixed seed so that no
position or id carries information. The instructions state the same notion of "same incident" as above, require every id to
appear exactly once and allow singleton groups; the model returns clusters with a one-sentence summary. In `cluster-cards` a
card has publisher, date, title, the first 350 characters of text and the two extracted records (this variant therefore
includes the fields of Method 2); in `cluster-full` a card has publisher, date, title and the first 4,000 characters of the
article, with no extracted fields. The response is validated: unknown or duplicate ids are counted and dropped, missing ids become singletons (none occurred in
the six runs). Three independently shuffled runs are made per variant; a *consensus* clustering links two articles if they were
together in at least two of three runs (transitive closure). Scoring uses every one of the 29,646 pairs: pairwise precision,
recall and F1, B-cubed F1, adjusted Rand index, and counts of true groups recovered exactly, clusters that merge several groups
and groups that are split. One call per run: 82k input and 17k output tokens (cards), 169k and 21k (full text).
**Result.** `cluster-cards`: all 100 groups recovered exactly in all three runs (pairwise F1, B-cubed F1 and ARI all 1.0).
`cluster-full`: 100 clusters (run 0, exact), 101 clusters (runs 1 and 2, one group split), consensus F1 99.6%, ARI 0.996.

**Working case.** Four reports of a 23 Jul 2025 crash in Natore, in two languages with four different death tolls: Prothom Alo
(English, "6 killed in truck-microbus head-on collision"), BSS (Bangla, toll "rises to 8"), Amar Barta (Bangla, "rises to 7")
and New Age ("Eight killed in Natore road accident"). All four were put in a single cluster in every run of both variants,
despite the different tolls and languages.

**Failure case (`cluster-full`).** The New Age roundup "Five national-minority men among seven killed in road accidents" was left
as a singleton in runs 1 and 2, while the two Bangla articles about the Naogaon dump-truck crash were clustered together (run 0
had joined all three). The full text of the roundup describes several crashes, so a model reading all articles at once
may reasonably decline to attach it to a single one. This is the same article that defeated the full-article pair judge in
one order, and it is the only error of the clustering methods. `cluster-cards`, whose cards hold only a short lead and the
extracted fields, made no error at all in this benchmark, so there is no failure case to show for that variant.

## Baselines
**TF-IDF cosine (`baseline tf-idf`).** Title plus the first 1,500 characters are tokenised into words (any script), weighted
with log term frequency times a smoothed inverse document frequency, and compared by cosine; a pair is *same* above a
threshold. The threshold (0.2175) was tuned on this same sample, so the result is optimistic. F1 29.3%.
*Working:* two Bangla articles on a truck overturning near the Jamuna bridge in Tangail (cosine 0.78). *Failure:* the English
"5 Killed as BRTC Bus Hits Ambulance Head-On in Faridpur" and the Bangla Dhaka Post article about the same crash have cosine
0.00 (no shared words), and, in the other direction, two Bangla Dhaka Times 24 pages about different crashes (16 Jun and 24 May
2026) score 0.96 because most of their text is shared page boilerplate.

**Fields rule (`baseline fields rule`).** On the model-extracted records, a pair is *same* if both articles have exactly one
accident, the countries are equal, the dates are at most one day apart and the location word-sets overlap (Jaccard >= 0.3). Fixed
in advance. Precision 99.1%, recall 49.6%. *Working:* the Padma pair (same country and date, shared words "Daulatdia ferry
pontoon Rajbari"). *Failure (miss):* the Natore crash reported by Amar Barta ("Royna Tormuj Petrol Pump area, Baraigram Union")
and BSS ("Airmari Bridge area, Bonpara-Hatikumrul highway"): the two articles name different landmarks for the same crash, so
the overlap is below the threshold. *Failure (false match):* The Daily Star's Chattogram highway crash of 2 Apr 2025 and its
Gazipur policeman crash of 1 Apr 2025 share generic words ("area", "highway", "upazila"), the country and a one-day gap.

## What the comparison supports
The LLM methods clearly outperform the lexical and rule baselines, especially for Bangla-English pairs and revised tolls. They
are within each other's confidence intervals, so this benchmark cannot rank them: the groups were built by an LLM agent, the hard
negatives were chosen by the same agent, and no method found a pair that every method contradicted. Harder, human-verified items
(same-day same-city crashes, follow-up articles, roundups) are needed to separate them.
