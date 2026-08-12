# Group A live candidate discovery

"
        "This directory is a resumable metadata-only candidate ledger for 17 countries. "
        "`collect.py` queries country-localized Google News RSS over a bounded 90-day window, "
        "resolves aggregator links to publisher URLs, and makes a range-limited GET only to "
        "classify publisher access. It does not save article bodies.

"
        "- `raw/<ISO2>.json`: parsed RSS metadata cache (not article content).
"
        "- `state.json`: resolved-link and access-check cache for resumption.
"
        "- `candidates.jsonl`: accessible direct publisher candidates.
"
        "- `same_incident_pairs.jsonl`: cross-domain suggestions requiring manual verification.
"
        "- `access_failures.jsonl`: blocked, unavailable, or unresolved discoveries.
"
        "- `summary.json`: counts, deficits, methods, and blockers.

"
        "Pair suggestions are not truth assertions. They require two domains, at least two "
        "distinctive shared title tokens, close publication timestamps, and a similarity threshold.

"
        "Run `python work/global_candidates/group_a/collect.py`; add `--refresh-feeds` only to "
        "replace cached feed metadata.
"
