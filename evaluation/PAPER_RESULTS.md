# mGeoAI Experimental Results

Generated deterministically from `outputs/deepseek-refusion` for the manually verified subset and
`outputs/global-v1` for corpus-wide descriptive analysis. Gold and unlabeled results are
kept separate throughout.

## 1. Experimental Setup

The manually verified evaluation subset contains 6 incidents.
Stable input artifact paths identify its source membership; source 12 is split with
location-specific mention selectors because it contains two incidents. Bootstrap 95%
confidence intervals use 2,000 resamples and the configured deterministic seed.
The full corpus has no exhaustive human truth labels, so its results are coverage,
structure, consistency, uncertainty, or efficiency statistics—not accuracy.

Gold source-to-mention resolution produced 17
evaluable mentions and 2 unresolved assignments
(no_matching_mention: 2).

## 2. Corpus Characteristics

| Metric | Value |
|---|---:|
| Raw input artifacts | 510 |
| Accepted source records | 510 |
| Collection countries | 51 |
| Languages | 26 |
| Publishers | 311 |
| Unique domains | 300 |
| Evidence items | 2887 |
| Incident mentions | 511 |
| Fused incident records | 441 |
| Source-named incident locations | 4 (0.9070%) |
| Map-visible records | 441 (100.0000%) |
| Collection-country fallback markers | 437 |

These counts describe processed records and source coverage. They do not establish the
number of true incidents in the world or the factual correctness of generated records.

## 3. Gold-Set Evaluation

| Field | Metric | Score | N | 95% CI |
|---|---|---:|---:|---|
| Fatalities | Exact match | 66.7% | 6 | [0.3333, 1.0] |
| Fatalities | MAE | 1.6667 | 6 | [0.0, 3.6667] |
| Injuries | Exact match | 50.0% | 2 | [0.0, 1.0] |
| Location | Required-term agreement | 83.3% | 6 | [0.5, 1.0] |
| Location | Coordinate error | not evaluable km median | 0 | not applicable |

Missing predictions are shown separately and are not silently converted to zero.
No coordinate-accuracy result is reported because the supplied gold labels contain no
trusted coordinates. Incident type and event time are also unevaluable because those
fields were not human-labelled.

## 4. Same-Incident Matching

The gold-derived pair set contains 136 evaluable pairs, including
25 positive and 111
negative pairs. Pairwise precision is 100.0%, recall
is 88.0%, F1 is 93.6%,
with incident-cluster bootstrap 95% CI [0.7, 1.0];
accuracy is 97.8%, and specificity is
100.0%. A missing candidate decision is treated
as a negative prediction because no same-incident edge was produced.

## 5. Incident Clustering

B-cubed precision, recall, and F1 are respectively
100.0%,
91.2%, and
95.4% over
17 resolved gold mentions. The run contains
1 fragmented gold incidents and
0 over-merged predicted clusters.

## 6. Multi-Source Fusion

Across 49 automatically
identified multi-source records, mean best-single completeness was
38.6% and
mean fused completeness was 39.1%.
The absolute field-coverage gain was
0.6%.
This is information completeness gain, not fusion accuracy.

| Multi-source fusion characteristic | Value |
|---|---:|
| Evaluable multi-source records | 49 |
| Best-single completeness (mean) | 38.6% |
| Fused completeness (mean) | 39.1% |
| Absolute completeness gain | 0.6% |
| Sources per incident (mean) | 1.1587 |
| Modalities per incident (mean) | 1.0000 |
| Conflict incident rate | 0.4% |
| Provenance coverage | 100.0% |

## 7. Multimodal Evidence Contribution

The text-only global corpus has 0
incidents with evidence from at least two modalities. In the multimodal gold-prediction
run, 4 fused records had
at least two modalities and 1
had at least three. The matrices are available in `results/modality_contribution.csv`
and `results/gold_run_modality_contribution.csv`; they report support frequency, not
modality accuracy.

## 8. Conflict Preservation

2 fused records contained at least one
represented conflict (0.4% of
records). The alternative-preservation rate was
100.0%. This is a structural
schema result, not conflict-detection accuracy.

Top retained cases:

- `inc_b0eae1856641ab8d` — fatalities: [9]
- `inc_fff928196c25af3b` — fatalities: [34]

## 9. Provenance

211 of
211 canonical fused facts retained at least
one resolvable evidence-to-source path (coverage
100.0%).
**Provenance coverage measures traceability, not factual correctness.**

## 10. Geolocation

4 of
441 records contain source-named incident
locations (0.9070%). Separately,
441 records are map-visible
(100.0000%), including
437 explicitly non-incident
collection-country fallback markers. The median uncertainty
radius is 3.0000 km (P90
25.4000 km). These values describe
representation and uncertainty, not spatial accuracy.

| Geolocation characteristic | Value |
|---|---:|
| Source-named incident locations | 4 |
| Collection-country fallback markers | 437 |
| Map marker coverage | 100.0% |
| Incident-location coverage | 0.9% |
| Median uncertainty radius | 3.0000 km |
| P90 uncertainty radius | 25.4000 km |

## 11. Efficiency and Cost

The run considered 130304
theoretical cross-source mention pairs and persisted
5913 candidate decisions.
It recorded 199 provider
adjudication-path decisions and 0
actual live LLM calls. In a live run those adjudication-path decisions require the
configured model, producing candidate-denominator call avoidance of
96.6%.
The recorded provider/model is `recorded` /
`recorded-fixture-v2`. Estimated cost is
0.0000 USD;
this is null when cost metadata is incomplete.

| Matching efficiency characteristic | Value |
|---|---:|
| Theoretical cross-source pairs | 130304 |
| Candidate decisions | 5913 |
| Deterministic decisions | 5714 |
| Recorded/provider match adjudications | 199 |
| Live LLM match calls | 0 |
| Candidate-denominator call avoidance | 96.6% |
| Total provider latency | 0.0000 ms |
| Estimated provider cost | 0.0000 USD |

The heuristic-only matching ablation uses the predeclared configuration threshold 0.72;
its F1 is 93.6%,
compared with 93.6% for the
full stored decisions. LLM-only and modality ablations are marked `not_run` because the
necessary all-pair or modality-specific artifacts do not exist and generating them would
require paid calls or alter pipeline semantics.

## 12. Error Analysis

The evaluator recorded 8 observed discrepancies. Counts and exact
incident examples are in `results/error_cases.csv`; no illustrative error is counted.

| Error category | Count | Share of observed discrepancies | Representative incident |
|---|---:|---:|---|
| location_granularity_disagreement | 4 | 50.0% | `gold-001-purbachal` |
| geographic_disagreement | 1 | 12.5% | `gold-004-mirsharai` |
| fatalities_underestimate | 1 | 12.5% | `gold-005-sylhet` |
| injuries_overestimate | 1 | 12.5% | `gold-005-sylhet` |
| fatalities_overestimate | 1 | 12.5% | `gold-006-bogura` |

## 13. Representative Cases

### inc_b0eae1856641ab8d: Passenger-bus collision in Osmaninagar, Sylhet

- Sources: 5 (`src_1f216a200c947a9b, src_4d82b7e87ecfc5fa, src_6e56eed9ea5d3d70, src_9a000ba483d1029f, src_f169afeba22bd6f6`)
- Publishers: Dhaka Tribune, Just News BD, The Business Standard, bdnews24.com
- Modalities: text
- Evidence items: 11
- Fused facts: fatalities=16 (known), injuries=25 (known)
- Conflicts retained: 1
- Geolocation: Kashikapan, Osmaninagar, Sylhet; granularity=area; uncertainty radius=3.0 km
- Summary: The fused record concerns this reported incident: Passenger-bus collision in Osmaninagar, Sylhet. The reported date is August 7, 2026, retained at day precision. Reports identify the location as Kashikapan, Osmaninagar, Sylhet; fusion retains it at area precision with 88% location confidence. The reconciled casualty assessment records 16 reported fatalities and 25 reported injuries. Identified vehicles or road users include bus. No explicit traffic congestion, delay, or obstruction was reported. The record combines 5 source record(s) representing 4 independent source group(s) and 11 cited evidence item(s). Important location limitation: Coordinates represent a named-area centroid, not the exact crash point, with an approximate 3 km uncertainty radius. Representative decisive evidence: [ev_02e1248ad077ecae] [ev_10cec01ebd4f8df5] [ev_2a045075fbf8c346].

### inc_7f5a385c571d19e6: Papa Leão XIV homenageia jovens mortos em acidente de ônibus em Tauá (CE)

- Sources: 4 (`src_13a603e08989801f, src_9ceb2cca9dfdc2a2, src_a0e9a459859f8b30, src_fa2c16d6b3d22cd8`)
- Publishers: ACI Digital, Correio Braziliense, Leia Sempre Brasil, blogdosilvalima.com.br
- Modalities: text
- Evidence items: 20
- Fused facts: fatalities=None (not_reported), injuries=None (not_reported)
- Conflicts retained: 0
- Geolocation: Brazil — collection-country fallback; incident place unresolved; granularity=country; uncertainty radius=None km
- Summary: The fused record concerns this reported incident: Papa Leão XIV homenageia jovens mortos em acidente de ônibus em Tauá (CE). The reported date is June 22, 2026, retained at day precision. Reports identify the location as Brazil — collection-country fallback; incident place unresolved; fusion retains it at country precision with 18% location confidence. The reconciled casualty assessment records fatalities not reported and injuries not reported. Identified vehicles or road users include bus. No explicit traffic congestion, delay, or obstruction was reported. The record combines 4 source record(s) representing 4 independent source group(s) and 20 cited evidence item(s). Important location limitation: Incident place unresolved. This marker represents only the source's collection-country metadata and is not a reported crash location. Representative decisive evidence: [ev_236d29d623251ad5] [ev_2bd54fbed584721c] [ev_2dc6133733efc49b].

### inc_1da2a4076b766070: Fatal Peki-Tsame road crash claims 15 lives, 25 injured

- Sources: 4 (`src_74d24b7a1d3dceb9, src_8e80b17e427f3cb2, src_c0454c8046a51745, src_f48d913a9be2b902`)
- Publishers: CitiNewsroom.com, Ghanaian Times, Graphic Online
- Modalities: text
- Evidence items: 20
- Fused facts: fatalities=15 (known), injuries=25 (known)
- Conflicts retained: 0
- Geolocation: Ghana — collection-country fallback; incident place unresolved; granularity=country; uncertainty radius=None km
- Summary: The fused record concerns this reported incident: Fatal Peki-Tsame road crash claims 15 lives, 25 injured. The reported date is June 2, 2026, retained at day precision. Reports identify the location as Ghana — collection-country fallback; incident place unresolved; fusion retains it at country precision with 18% location confidence. The reconciled casualty assessment records 15 reported fatalities and 25 reported injuries. Identified vehicles or road users include truck. No explicit traffic congestion, delay, or obstruction was reported. The record combines 4 source record(s) representing 3 independent source group(s) and 20 cited evidence item(s). Important location limitation: Incident place unresolved. This marker represents only the source's collection-country metadata and is not a reported crash location. Representative decisive evidence: [ev_047d933ff60f3206] [ev_26b62a8548f29a80] [ev_457ef40a61c4f2ae].


## 14. Limitations of the Evaluation

- This is a small, manually verified evaluation subset, not a definitive global benchmark.
- Only supplied human labels are evaluated. Unknown/N/A values remain unevaluable.
- Text-only gold locations support semantic place-name agreement but not Haversine accuracy.
- Unresolved source-to-mention assignments are disclosed and never forced.
- The automatically collected global corpus is used only for descriptive and structural analysis.
- Recorded-provider results demonstrate reproducibility but are not evidence of live-model accuracy.
- The development fixture in `tests/fixtures/golden_pairs.json` is excluded from paper metrics.
- No threshold was tuned against these gold results.

## 15. Recommended Results for the Conference Paper

Report the field-specific gold metrics with their denominators and confidence intervals;
pair them with corpus-wide information-completeness, provenance, conflict-preservation,
geolocation-coverage, and efficiency results. Do not generalize this Bangladesh-only gold
subset into global accuracy claims. Refer to `results/paper_metrics.json` as the canonical
numeric source and `results/validation_report.json` before copying any number.
