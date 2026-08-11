# International corpus

MGeoAI's international corpus is a reviewed collection of saved source artifacts,
not a truth database. A source record means that a publisher reported something;
acceptance does not independently verify the incident or establish fault.

The canonical corpus lives outside `assets/scraps`. It contains strict JSON source,
country, incident, review, and hash records. `CorpusStore` reads those records,
`validate_corpus` enforces collection requirements, and `materialize_corpus` emits a
derived directory compatible with the existing MGeoAI discovery and ingestion code.

Production validation defaults require at least 50 ISO alpha-3 countries, at least
10 accepted traffic-incident sources per country, and at least one explicitly reviewed
same-incident group per country supported by two original sources in distinct
dependency groups. Every review records whether it was human or automated. Automated
title/date/entity review satisfies the reproducible collection invariant but is not a
substitute for human confirmation in a publication-grade gold set. Every accepted
source needs an original HTTP(S) verification URL, an accepted review event with a
content-matching link check, and payload bytes matching the declared size and SHA-256.

Canonical source payloads use one HTML or video-analysis artifact. An optional
image-analysis artifact may accompany HTML. The materializer writes HTML bundles as
`html/<country>/<source>/content.html`, `SOURCE_INFO.md`, and optional
`image_01.json`; video analysis is written beneath a directory named `youtube`.
Generated `SOURCE_INFO.md` starts with machine-readable front matter for country,
ISO country code, BCP-47 languages, IANA timezone, publication time when known,
the traffic-incident flag, and source-language traffic keywords. Human-readable
publisher and verification-link lines follow that front matter.

Incident records are explicitly `curation_only`. Their IDs, source memberships,
labels, reviewer names, and notes are evaluation data and are not copied into the
materialized scraps or provider input. The materialization manifest contains only
corpus source IDs and generated paths.

Access failures belong in append-only `AccessAttempt` records. Blocked, unavailable,
rejected, pending, or duplicate candidates never satisfy country quotas. Collection
software must respect robots policy, authentication boundaries, paywalls, rate limits,
and regional restrictions; it must not persist credentials or cookies.

Large or redistribution-restricted payloads should use controlled, content-addressed
storage. Only appropriately licensed source material should be committed publicly.
Ordinary tests must use small offline fixtures and mocked network behavior.
