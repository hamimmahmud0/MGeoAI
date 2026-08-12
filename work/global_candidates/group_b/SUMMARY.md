# Group B live candidate discovery summary

Generated: `2026-08-11T21:53:40.401282+00:00`

- Candidate records: **172**
- Countries meeting the >= 15 target: **9 / 17**
- Countries with a credible distinct-domain pair: **9 / 17**
- Distinct direct publisher URLs: **172**

| Country | Candidates | Publisher domains | Pairs | Target | Access blockers / exclusions |
|---|---:|---:|---:|---|---|
| NLD — Netherlands | 20 | 13 | 1 | met | no_reviewable_text: 3 |
| BEL — Belgium | 15 | 10 | 1 | met | blocked: 5, no_reviewable_text: 8, robots_unavailable: 1 |
| SWE — Sweden | 17 | 13 | 1 | met | robots_unavailable: 43 |
| NOR — Norway | 20 | 11 | 1 | met | none recorded |
| POL — Poland | 20 | 8 | 1 | met | no_reviewable_text: 3, robots_unavailable: 2 |
| ZAF — South Africa | 20 | 12 | 1 | met | robots_unavailable: 2 |
| NGA — Nigeria | 20 | 9 | 1 | met | robots_disallowed: 2, robots_unavailable: 1 |
| KEN — Kenya | 20 | 8 | 1 | met | blocked: 8, robots_unavailable: 8 |
| GHA — Ghana | 20 | 7 | 1 | met | request_error: 1 |
| UGA — Uganda | 0 | 0 | 0 | NOT MET | none recorded |
| TZA — Tanzania | 0 | 0 | 0 | NOT MET | none recorded |
| ETH — Ethiopia | 0 | 0 | 0 | NOT MET | none recorded |
| MAR — Morocco | 0 | 0 | 0 | NOT MET | none recorded |
| EGY — Egypt | 0 | 0 | 0 | NOT MET | none recorded |
| TUN — Tunisia | 0 | 0 | 0 | NOT MET | none recorded |
| TUR — Türkiye | 0 | 0 | 0 | NOT MET | none recorded |
| JOR — Jordan | 0 | 0 | 0 | NOT MET | none recorded |

## Interpretation limits

- Discovery candidates are not accepted corpus sources and have not received formal human review.
- Country assignment is query-based and requires confirmation from each publisher page.
- Distinct publisher domains do not rule out syndication or a shared upstream report.
- Short excerpts are limited to 36 words and retained only for manual triage; payloads were not captured.
- Blocked, robots-disallowed, rate-limited, inaccessible, or unextractable pages were excluded from candidate JSONL and retained in access-attempt logs.

## Files

- `candidates.jsonl`: accessible direct-publisher candidate metadata.
- `pairs.jsonl`: one or more credible same-incident pair candidates where found.
- `access_attempts.jsonl`: decode, robots, HTTP, extraction, and other exclusion outcomes.
- `countries/*.jsonl`: resumable per-country checkpoints.
- `summary.json`: machine-readable totals.
