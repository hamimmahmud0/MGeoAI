# mGeoAI paper discussion notes

These notes are derived from the generated metrics. They distinguish agreement with the
manually verified subset from descriptive analysis of the unlabeled corpus.

## Supported observations

- Gold casualty performance is field-specific: fatality exact agreement is
  66.7%
  (n=6 numeric predictions),
  while injury exact agreement is
  50.0%
  (n=2). Missing predictions
  remain explicit and are not zero-filled.
- Gold textual location agreement is
  83.3%
  (n=6). Spatial error cannot be
  assessed because reference coordinates were not supplied.
- Same-incident matching F1 is 93.6% over
  136 gold-derived pairs. Clustering B-cubed F1 is
  95.4% over
  17 resolved mentions.
- Multi-source fusion changed field availability by an average of
  0.6%
  of the material-field inventory relative to the best single mention. This result
  supports an information-completeness claim only.
- Provenance coverage is 100.0%
  across 211 canonical fused facts. It
  demonstrates traceability, not truth.
- The conflict incident rate is 0.4%;
  alternative preservation is 100.0%.
- Unknown/zero semantic validation found
  0 violation(s). A reported
  zero is distinct from unknown and not reported throughout these calculations.
- Source-named incident-location coordinates exist for
  0.9% of fused records;
  map-marker coverage is 100.0%
  because 437 records use
  explicit collection-country fallback markers. These markers and uncertainty circles
  must not be described as exact crash locations.
- The matching stage avoided provider calls for
  96.6%
  of persisted candidate decisions. The all-pairs denominator is separately reported.
- The most frequent observed gold discrepancies were: location_granularity_disagreement (4), geographic_disagreement (1), fatalities_underestimate (1), injuries_overestimate (1), fatalities_overestimate (1).

## Threats to validity

The gold subset is small, Bangladesh-only, and selectively labelled. Its confidence
intervals are therefore more informative than point estimates alone, but they do not
eliminate selection uncertainty. The global corpus has no exhaustive incident truth
labels; source diversity, coverage, agreement, and efficiency must not be described as
global model accuracy. Recorded-provider outputs are reproducible fixtures rather than
independent model evaluations. Source dependency metadata may also be incomplete, and
the field-completeness inventory weights each material field equally.

## Appropriate conference-paper framing

Use the gold subset to support narrowly scoped statements about casualty extraction,
textual geolocation, pair matching, and clustering. Use the full corpus to demonstrate
scalability, source/modal diversity, traceability, conflict retention, explicit unknown
semantics, uncertainty-aware spatial representation, and provider-call reduction.
Avoid claims about truthfulness, hallucination rate, or global accuracy.
