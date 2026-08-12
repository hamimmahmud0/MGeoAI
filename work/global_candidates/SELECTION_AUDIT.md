# Global candidate selection audit

Generated for the `mgeoai-global-v1` seed corpus on 12 August 2026.

## Result

- 51 collection-country groups selected.
- Exactly 10 accepted source records per group (510 total).
- At least one same-event candidate pair on distinct publisher domains per group.
- 53 qualifying multi-source groups were retained after deterministic selection.
- Every accepted record has a direct publisher URL in
  `corpus/global-v1/reports/source_links.csv`.
- The full recorded pipeline completed with 510 sources, 2,887 evidence items,
  511 mentions, and 441 fused incident records.

## Checks performed

Candidate JSONL files were schema-validated, canonical URLs were deduplicated, access
statuses were checked against the accepted status allowlist, and pair candidates were
required to use two distinct domains. Group C's exact 170-row selection has a separate
row-level audit in `group_c/audit.jsonl`. Selected Group A and Group B titles were
reviewed for incident specificity; ten aggregate, policy, or opinion records were
marked `rejected_quality_audit` before the final build.

The initial Netherlands pair joined different crashes, and the initial Jordan pair
mistook West Jordan, Utah, for Jordan. Both were replaced with title/date/place/vehicle
matched pairs in `group_supplemental/candidates.jsonl`. Supplemental pair rationales
state where common upstream reporting has not been ruled out.

## Interpretation boundary

This is an automatically screened research seed, not a human-verified truth dataset.
Country is the collection/discovery bucket and is explicitly not a verified event
country or crash coordinate. Distinct domains do not prove editorial independence.
The original links are provided so qualified reviewers can confirm source eligibility,
event location, pair identity, source dependence, and reported details before using
the corpus for accuracy claims or substantive traffic-safety analysis.

Public Bluesky AppView metadata collected on a best-effort basis is retained in
`group_social/`. It is excluded from the accepted 510 until human review because a
post's text, account, and country mention do not by themselves establish event
location, authorship, or independence.
