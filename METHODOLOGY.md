# Methodology: Global Multimodal Traffic-Incident News Corpus and Evidence-Fusion Pipeline

## Document status and scope

This document specifies a research protocol for constructing and evaluating a
51-country traffic-incident news corpus with MGeoAI. It also describes the parts of
the protocol that the repository currently implements. The distinction matters:

- **Implemented** means that a data model, validator, pipeline stage, audit record,
  or offline test exists in the repository.
- **Human-governed** means that software records or constrains a decision, but a
  qualified reviewer must make or confirm it.
- **Study-stage** means that the procedure is required for a defensible global study
  but is not, by itself, evidence that the procedure has been completed.

The repository implements strict corpus contracts, integrity validation,
provenance-preserving ingestion, incident matching and fusion, a reviewer workflow,
and offline fixtures. It now contains a reproducible **automatically screened seed
corpus** with 51 collection-country groups, 510 accepted source records, and 53
automatically proposed multi-source incident groups. It does **not** contain a fully
human-audited global corpus, a fully global geocoder, or human-verified global
performance results. Collection country describes the discovery/source bucket and
must not be interpreted as a verified crash location; this is explicit in the source
link report and coverage GeoJSON. The default corpus validator requires at least 50
countries, and this release freezes 51 in its versioned corpus manifest.
The corpus records what publishers and other captured sources reported. It is not a
truth database and does not independently establish that an event happened, who was
at fault, or what its final consequences were.

## Abstract

Traffic incidents are reported through heterogeneous news pages, social posts, and
prior image or video analyses. These reports vary by language, accessibility,
publication practice, location precision, casualty definitions, and dependence on
other reporting. MGeoAI treats each report as attributed evidence rather than as an
unqualified fact. The proposed study uses a purposive, diversity-aware sample of 51
countries, with at least 10 accepted traffic-incident sources in each country and at
least one manually reviewed incident represented by two independent original-source
groups per country. The current seed release meets the numeric source and paired-report
quotas through automated checks and distinct publisher domains, but its pair labels,
country assignments, and upstream independence still require qualified human review.
Captured payloads are immutable and content-addressed; source, block, and JSON-path
provenance is retained through normalization and fusion.

The computational pipeline parses saved HTML and structured multimodal-analysis
JSON, generates canonical evidence and incident mentions, proposes cross-source
matches, clusters mentions under contradiction guards, and produces fused incident
records with field-level support, alternatives, uncertainty, and provider-run
metadata. Human review remains necessary for source eligibility, content-to-link
verification, source dependence, shared-incident reference labels, difficult
geolocation, material casualty conflicts, and publication decisions. Evaluation is
specified at the source, evidence, pair, cluster, field, location, country, language,
and modality levels. Statistical reporting must separate coverage from correctness,
account for source dependence, and quantify variation across countries rather than
presenting a single pooled score as global validity.

## 1. Research purpose and questions

The study concerns the faithful transformation of reported traffic-incident evidence
into inspectable incident records. It is descriptive and methodological. It is not a
causal study of crash risk, a population surveillance system, or a substitute for
police, hospital, civil-registration, or road-authority data.

The primary research questions are:

1. **RQ1 — Corpus coverage:** Can a reproducible collection protocol obtain a
   sufficiently diverse, reviewable set of traffic-incident reports across 51
   countries without bypassing access controls or conflating unavailable reporting
   with the absence of incidents?
2. **RQ2 — Extraction and provenance:** How accurately does the pipeline recover
   event time, reported place, road users, vehicles, traffic effects, casualties, and
   attribution while retaining a resolvable source locator for each claim?
3. **RQ3 — Incident matching:** How accurately does the system determine whether two
   reports concern the same incident, a related development, or different incidents,
   especially when reports are syndicated, incomplete, or multilingual?
4. **RQ4 — Fusion under disagreement:** Does fusion preserve unknown values,
   assertion status, source dependence, and conflicting claims rather than silently
   averaging or selecting unsupported facts?
5. **RQ5 — Geographic uncertainty:** How well do reported-place representations and
   their stated granularity correspond to human-reviewed references, and how often
   would a point marker imply more precision than the source supports?
6. **RQ6 — Equity and transfer:** How do collection yield and pipeline performance
   vary by country, language, script, source type, access condition, and urban/rural
   context?
7. **RQ7 — Operational utility and harm:** Do evidence links, uncertainty displays,
   and review controls help analysts inspect reports without encouraging unsupported
   conclusions about truth, blame, sentiment, or population-level risk?

## 2. Study objects and units of analysis

The protocol separates objects that are often incorrectly collapsed:

- A **candidate** is a discovered URL or supplied artifact that has not passed
  eligibility review.
- A **source** is one captured publisher item or structured multimodal-analysis item.
  Multiple sources may repeat the same reporting.
- An **artifact** is an immutable HTML, video-analysis JSON, or image-analysis JSON
  payload associated with a source.
- A **block** is a headline, byline, article paragraph, post, caption, comment, link,
  or structured JSON element with a source-specific locator.
- An **evidence item** is an attributed normalized claim derived from a block. It
  retains modality, assertion type, original claim text, confidence, and provenance.
- An **incident mention** is a source-local event representation. It is not yet a
  cross-source incident identity.
- A **match decision** classifies a pair of mentions as the same incident, related
  but distinct, different, or uncertain.
- A **cluster** is a set of mentions joined as one reported incident under the
  matching rules.
- A **fused incident** is a derived summary of that cluster. Every material fact must
  point back to supporting evidence, and contradictions remain representable.
- A **curation incident** is a human-created reference grouping used only for corpus
  validation or evaluation. Its identifier and membership are withheld from model
  input.

The source is the unit of collection; the evidence item is the unit of provenance;
the mention pair and incident cluster are units of matching evaluation; and the fused
field is the unit of extraction/fusion evaluation. Sources are not assumed to be
statistically independent merely because their URLs or publishers differ.

## 3. Sampling frame and 51-country coverage

### 3.1 Country selection

Before collection, the study team must register exactly 51 assigned ISO 3166-1
alpha-3 country codes in `corpus.json`. Country codes follow
[ISO 3166-1](https://www.iso.org/standard/72482.html). The repository validates that
manifest codes are uppercase, assigned, unique, and matched by one country record.
It does not choose the 51 countries.

Country selection should be purposive and stratified, not described as a random
sample of the world. The frozen selection should seek variation in:

- UN geographic region and subregion;
- income and road-transport context;
- commonly published languages and scripts;
- urban and non-urban reporting environments;
- press-system and internet-access conditions;
- source formats, including saved news HTML and eligible multimodal analyses; and
- expected availability of local reviewers with relevant language and geographic
  knowledge.

The preregistration or release note must publish the final country list, rationale,
collection window, search languages, target source classes, and any replacements. A
country must not be silently replaced because its sources are difficult to access;
access difficulty is an outcome that may itself reveal coverage bias.

### 3.2 Per-country allocation

The canonical country record defaults to a target of 12 sources, while production
validation requires at least 10 accepted traffic-incident sources per country. For
each country, at least one human-reviewed same-incident group must contain accepted
original sources from at least two distinct dependency groups. This supplies a small
but essential cross-source matching stratum; it does not make 10 sources nationally
representative.

The study should use the same prospective time window and source-allocation rules
across countries where practicable. If differing windows, quotas, or media strata are
necessary, they must be declared before analysis and included in country-level
reporting. Discovery should continue until the target is met or the predeclared
stopping rule is reached. The denominator must include rejected, duplicated,
unavailable, and blocked candidates, not only successful captures.

### 3.3 Sampling and reporting flow

For each country, report a flow table with candidates discovered, access attempts,
payloads captured, records deduplicated, records excluded by reason, records pending
review, and sources accepted. Accepted sources alone satisfy the quota. A source
counts only when it is marked as a traffic incident and has a matching accepted
review event with a successful content check against a configured verification URL.

Because prominent crashes attract more coverage than routine incidents, neither the
source sample nor fused clusters estimate incident prevalence. Counts of reports,
sources, or clusters must not be interpreted as road-safety rates without an
independent denominator and surveillance design.

### 3.4 Datasource inventory for the global-v1 snapshot

The frozen `global-v1` release contains 510 accepted metadata-only news records,
allocated as 10 sources in each of 51 collection-country groups. It contains 311
distinct publisher labels, 300 declared domain/dependency groups, and 26 declared
language tags. All 510 records include publication timestamps. These figures describe
the corpus inventory, not 510 verified incidents: reports may cover the same event,
may have been assigned through a publisher-country query, and may still require
event-country correction.

The release uses several datasource layers that must not be conflated:

| Datasource layer | Snapshot contribution | Stored role | Principal limitation |
| --- | --- | --- | --- |
| Publisher pages | 510 canonical article URLs from 311 publisher labels | Original verification target and publisher/domain identity | Availability and page content can change; a link is not proof that every claim is true. |
| Bing News discovery | 256 retained discovery-record links | Candidate provenance and manual rediscovery route | Search ranking and indexing are proprietary and time-varying. |
| Google News discovery | 250 retained discovery-record links | Candidate provenance and manual rediscovery route | The RSS interface is opportunistic discovery metadata, not the canonical article. |
| Google web discovery | 4 retained discovery-record links | Candidate provenance for otherwise selected reports | Search results are unstable and may be personalized or removed. |
| Committed metadata/excerpt payloads | 510 generated HTML records | Title, publisher, canonical URL, publication time, and a maximum 25-word public-feed excerpt | These are not complete archived articles and cannot support claims absent from the excerpt. |
| Automated review records | 510 accepted link/content-match decisions | Eligibility and audit trail for this seed release | Automated acceptance is not qualified human verification of relevance, country, independence, or truth. |
| Curation incident groups | 53 automatically proposed distinct-domain groups | Matching/evaluation candidates withheld from model input | Same-incident membership and upstream editorial independence remain human-review requirements. |
| Derived MGeoAI outputs | 510 sources, 2,887 evidence items, 511 mentions, and 441 recorded-provider incidents | Reproducible extraction, clustering, fusion, GeoJSON, and dashboard artifacts | Recorded-provider output demonstrates pipeline behavior, not live-model accuracy or factual verification. |

Every accepted row is listed in [`NEWS_SOURCES.md`](NEWS_SOURCES.md), grouped by
collection country with source ID, publication date, publisher, direct article link,
and discovery-record link. The machine-readable counterpart is
`corpus/global-v1/reports/source_links.csv`. The catalog is generated from canonical
corpus records with `mgeoai corpus-source-catalog`; it should not be edited as an
independent source of truth. Link rot should be recorded in a subsequent review event
rather than silently replacing the frozen URL or payload.

## 4. Discovery, capture, and eligibility

### 4.1 Discovery protocol

Study-stage discovery uses documented query templates translated or adapted by a
competent speaker. Search terms should combine locally appropriate traffic-event
terms with road-user, place, and temporal terms. The team should record the query,
language, search service or publisher index, retrieval time, result rank when
available, and candidate URL. Researchers should supplement major national outlets
with regional or local publishers under a predeclared allocation to reduce capital-
city bias.

MGeoAI's current corpus contracts begin at the captured candidate and do not yet
implement a globally standardized search engine. Consequently, discovery logs and
sampling decisions remain a human-governed study responsibility.

### 4.2 Access and capture

The canonical corpus accepts exactly one primary payload per source: saved HTML or
video-analysis JSON. Image-analysis JSON may accompany HTML. The image/video JSON is
an analysis artifact, not the original audiovisual file, and its claims retain their
modality and JSON-path provenance. Raw HTML is treated as untrusted data: scripts,
styles, templates, and other executable content are not executed or sent directly to
the fusion model.

Each artifact record declares a safe relative path, byte size, UTF-8 encoding, and
SHA-256 digest. Capture method is one of HTTP retrieval, manual browser save, manual
upload, or archive retrieval. The original or verification URL is stored separately
from the payload. Captured bytes should never be silently refreshed in place; a new
capture requires a new source version or auditable replacement decision.

The append-only access-attempt record distinguishes successful capture from robots
exclusion, HTTP 403, paywall, rate limiting, timeout, TLS failure, geoblocking,
removal, unsupported media, oversize content, and other failure. Retryability and a
retry-after time can be recorded. These states support analysis of access bias and
must not be converted into evidence that no incident occurred.

### 4.3 Inclusion and exclusion

An accepted source must:

1. be assigned to a frozen study country and collection window;
2. report a discrete road-traffic incident or a clearly attributable development of
   one, rather than only general policy or aggregate statistics;
3. provide one valid primary artifact in the supported shape;
4. identify publisher, canonical URL, language, timezone, capture time, source
   dependence, and redistribution status;
5. include at least one source-language traffic keyword when marked as a traffic
   incident;
6. pass hash, size, encoding, path, and schema checks; and
7. receive an accepted human review whose configured link check confirms that the
   captured content matches the reviewed page.

Records are excluded or retained as non-accepted candidates when they are unrelated
to traffic incidents, out of scope, an unresolved duplicate, inaccessible, lacking a
reviewable artifact, mismatched to the verification page, or prohibited by the
study's access and rights policy. Ambiguous cases remain pending or need changes;
they should not be forced into an accepted/rejected binary merely to meet a quota.

Acceptance confirms eligibility and content correspondence. It does not verify that
all source claims are true.

## 5. Accessibility, robots policy, and copyright

Automated retrieval must implement the
[Robots Exclusion Protocol (RFC 9309)](https://www.rfc-editor.org/rfc/rfc9309.html),
respect authentication boundaries, paywalls, rate limits, regional restrictions,
and publisher terms, and avoid persisting credentials or cookies. Robots rules are a
crawler-control protocol, not a grant of copyright permission or proof that capture
is lawful. Manual browser capture is permitted only when the researcher has lawful
access; it is not a means to evade a technical control.

Every source declares whether redistribution is `redistributable`,
`internal_research_only`, or `metadata_only`. Public releases should contain source
payloads only when the study has an appropriate license or other documented legal
basis. Restricted payloads should remain in access-controlled, content-addressed
storage; a public metadata record may instead contain identifiers, hashes, limited
descriptive fields, and lawful links. Quotation and reproduction decisions require
jurisdiction-specific review. The international baseline is the
[Berne Convention](https://www.wipo.int/treaties/en/ip/berne/), but this protocol is
not legal advice and does not replace local law or contractual obligations.

Accessibility is both an ethical and measurement issue. Review and publication
interfaces should be evaluated against
[WCAG 2.2](https://www.w3.org/TR/WCAG22/), including keyboard operation, visible
focus, text alternatives, color-independent status cues, sufficient contrast, and
screen-reader labels. A publisher's inaccessible design should be recorded as a
collection limitation rather than used as evidence of low relevance. Where an
accessible alternative or archive is used, reviewers must confirm content
correspondence and retain both links.

## 6. Provenance and data integrity

MGeoAI uses provenance at three linked levels:

1. **Corpus provenance:** source ID, publisher, canonical and verification links,
   capture method and time, artifact path, byte size, SHA-256, review event, and
   dependence group.
2. **Extraction provenance:** source ID plus an HTML selector, JSON path, video
   timestamp, image region, or source-level locator; block ID and original text may
   accompany the locator.
3. **Fusion provenance:** every fused fact lists supporting evidence IDs; the fused
   incident lists all contributing source and evidence IDs; each model operation has
   a provider-run record.

This structure is conceptually aligned with the
[W3C PROV-O Recommendation](https://www.w3.org/TR/prov-o/): captured sources and
derived records are entities, parsing/fusion are activities, and publishers,
reviewers, and providers are agents. The repository uses its own strict Pydantic/JSON
contracts rather than claiming full PROV-O serialization.

The corpus lock inventories relative paths, sizes, and hashes. Validation rejects
missing or symlinked artifacts, unsafe paths, size/hash mismatches, invalid encoding,
duplicate identifiers, unknown references, review mismatches, and quota failures.
Operational discovery manifests may contain environment-specific paths and therefore
belong in controlled run storage; public metadata and source metadata should use
repository- or input-relative paths and must not reveal home directories, credentials,
cookies, API keys, or hidden model reasoning.

Human reference groupings are marked `curation_only`. Materialization exposes only
accepted traffic sources and checks that curation incident IDs and source-group gold
labels do not enter provider input. This reduces direct label leakage, although
indirect leakage through distinctive text remains a general evaluation risk.

## 7. Multilingual processing

Source metadata records one or more language tags and an IANA timezone. Language tags
should follow [BCP 47 (RFC 5646)](https://www.rfc-editor.org/rfc/rfc5646.html), and
timezone identifiers should come from the
[IANA Time Zone Database](https://www.iana.org/time-zones). Country metadata uses ISO
alpha-3, while materialized source metadata can preserve an uppercase alpha-2 or
alpha-3 source code. Publication time is stored with an explicit offset or interpreted
under the declared IANA timezone; analysts must not assume the capture machine's
timezone.

The original-language text is authoritative evidence. Normalization may add canonical
forms, but it must retain the original claim and locator. Traffic-incident detection
can use an explicit reviewed metadata flag and a configurable list of source-language
keywords. A keyword hit is a discovery/extraction signal, not proof that the page is
in scope. Conversely, a missing keyword must not automatically exclude languages for
which the list is incomplete.

The current normalizer contains useful language-specific extraction logic and accepts
international metadata, but it is not a universal multilingual parser or translator.
A 51-country study must therefore:

- create and version per-language traffic and casualty lexicons with native-speaker
  review;
- test Unicode normalization, script-specific punctuation, number words, digit
  systems, dates, honorifics, and place-name variants;
- preserve transliterations as alternatives rather than replacing local-script names;
- record any machine translation as a derived artifact with tool/model/version and
  source-text alignment; and
- evaluate results separately by language and script, including low-resource strata.

Automatic translation is not currently a required pipeline stage. If introduced, it
must be treated as a fallible transformation and never erase the original evidence.

## 8. Computational pipeline

For a frozen configuration, the implemented dataflow is:

1. **Discover files:** enumerate supported artifacts, reject oversized files, and
   record hashes and warnings.
2. **Ingest:** parse saved HTML into typed blocks; parse video/image analysis JSON
   through modality adapters; attach source and fine-grained locators.
3. **Normalize:** create evidence items, assertion types, entities, casualty
   quantities, time and location mentions, traffic effects, assumptions, and
   extraction warnings.
4. **Form mentions:** create source-local incident mentions. A source may contain
   more than one incident or a later development.
5. **Generate candidate pairs:** compare mentions from different sources using time,
   normalized place, named entities, vehicles, and distinctive lexical features.
6. **Adjudicate pairs:** apply manual must-link/cannot-link constraints and hard
   guards; submit remaining candidates to the configured provider.
7. **Build clusters:** process same-incident decisions in confidence order using a
   union-find structure, while refusing a merge that would cross an explicit
   different/related-but-distinct constraint.
8. **Fuse:** generate a schema-constrained incident record from bounded canonical
   evidence; validate evidence references and retry eligible failures.
9. **Report:** emit canonical JSON, evidence and source views, GeoJSON, run metadata,
   and the operations interface.

DeepSeek is the live default. A live failure remains failed or retryable and must not
silently switch to the recorded provider. The recorded provider is an offline,
deterministic demonstration/test fixture; output produced by it must be labeled
recorded demo data and is not evidence of live-model performance.

Raw HTML is not model input. The provider receives bounded structured evidence and a
versioned prompt/JSON schema. A provider run records provider, model, endpoint mode,
prompt version/hash, request hash, time, latency, token counts when available,
estimated cost, retries, finish and validation status, cache status, and sanitized
error information. API keys and hidden reasoning must never be logged or persisted.

## 9. Incident matching and clustering

The implemented heuristic score is a weighted combination of temporal similarity
(0.30), normalized-location similarity (0.35), named-entity similarity (0.15),
vehicle similarity (0.05), and distinctive lexical similarity (0.15). Generic terms
such as “road,” “accident,” and “crash” do not supply lexical evidence. The default
possible-match threshold is 0.45; the configuration also exposes a 0.72 match
threshold and a maximum primary-report separation of three days.

For two primary reports, a date difference beyond the configured maximum or a
conflict between specific normalized locations becomes a hard guard. Same-location
plus lexical agreement and strong distinctive lexical overlap can raise a candidate
score. These rules improve recall for sparse reports but are heuristics, not
probabilities.

Provider adjudication must return one of four explicit relations and cite decisive
evidence and contradictions. Manual must-link and cannot-link overrides are auditable
configuration, not hidden label edits. Clustering respects pairwise negative
constraints, but transitive closure can still amplify an incorrect positive edge.
Evaluation must therefore assess complete clusters as well as pairwise decisions,
and operational review should prioritize low-confidence bridge edges and clusters
that span many publishers, dates, or locations.

Publisher identity does not imply independence. Reviewers classify sources as
original, repost, syndicated, quoted, or unknown and assign a dependency group.
Independent-source counts use distinct original dependency groups, not raw URL
counts. Quoted or syndicated copies may add evidence about coverage but must not be
presented as independent corroboration.

## 10. Evidence fusion and assertion handling

Fusion summarizes attributed evidence; it does not vote reports into truth. Evidence
items distinguish observed material, reported statements, attributed claims,
opinions, inferences, and predictions. A fused field records a value, state,
supporting evidence IDs, conflicting alternatives, contradiction flag, confidence,
and selection rationale.

Valid field states are `known`, `unknown`, `not_reported`, `not_applicable`, and
`reported_zero`. They are not interchangeable. In particular, “no number was
reported” is not zero, and a source's explicit zero is different from absence of a
claim. The provider contract requires evidence-backed values and summaries; schema
and reference validation reject unsupported evidence IDs. Material uncertainty and
source disagreement belong in alternatives, unresolved questions, and data-quality
warnings rather than being edited out for readability.

The human-readable fused review should state what was reported, by whom, where
sources agree, where they differ, what remains unknown, the location precision, and
what later developments are attributable. It must avoid legal or causal conclusions
such as fault unless clearly presented as an attributed claim.

## 11. Geolocation and spatial uncertainty

Canonical coordinates use WGS 84 longitude/latitude order as specified by
[GeoJSON RFC 7946](https://www.rfc-editor.org/rfc/rfc7946.html). A location includes
a display name, administrative hierarchy, optional coordinates, granularity,
method, alternatives, supporting evidence, confidence, ambiguity reason, and an
uncertainty radius.

Permitted granularities are point, intersection, road segment, area, city, district,
country, and unknown. Coordinates for a road, area, city, or district normally represent a
reported-place centroid, not a crash point. The implementation assigns default
uncertainty radii of 0.75 km for an intersection, 1 km for a road segment, 3 km for
an area, 12 km for a city, and 35 km for a district when no radius is supplied. These
are interface defaults, not empirical confidence intervals; the study must calibrate
or replace them against country-appropriate reference geometry before statistical
interpretation.

Geocoding should proceed from the most specific source-supported place hierarchy and
retain plausible alternatives when names are duplicated. A nearby photograph,
hospital, police station, court, publisher address, rescue destination, or map-search
result must not replace the incident location merely because it yields convenient
coordinates. Road links and region boundaries are contextual aids; they do not
increase the precision of the source claim.

The implemented derivation path is: parsed source block; evidence item with its exact
selector or JSON path; normalized place mention; specificity-ranked offline-gazetteer
candidate; source-local incident mention; cluster reconciliation; fused geolocation;
and GeoJSON in `[longitude, latitude]` order. A candidate carries the supporting
evidence IDs, display hierarchy, granularity, confidence, representative coordinate,
and reason. Fusion may select only coordinates supplied by those candidates and
prefers a source-named candidate over a country fallback.

For the 51-country seed corpus, a source whose place name is not yet in the offline
gazetteer receives a low-confidence `country` marker derived from collection metadata.
Its method is `collection_country_fallback`, its evidence list is empty, and both the
record and map state that it is not a reported crash location. Matching ignores this
marker, so it cannot make unrelated reports look co-located. This rule makes unresolved
records visible for review; it does not constitute incident-country inference or
successful place geocoding.

The bundled source-named place anchors are not a complete global gazetteer. A 51-country analysis
requires versioned country-specific gazetteers or a documented external geocoder,
multilingual aliases, administrative-boundary dates, and human review of ambiguous
cases. For evaluation, use a reference point only where reviewers can establish one;
otherwise score administrative/linear-feature containment and granularity agreement
rather than inventing an exact point.

## 12. Casualties, injury severity, and conflicting counts

Fatality and injury values are report-time claims. The pipeline normalizes common
field aliases to `fatalities` and `injuries`, retains supporting evidence, and can
store competing values with a contradiction flag. Counts must not be averaged.
Where sources report different totals, the fused record should either select a
clearly justified value (for example, a later attributable update) while retaining
earlier alternatives, or leave the fact unresolved.

Headline counts are evidence and must not be discarded merely because the article
body is sparse. Equally, a headline and body can reflect different update times or
categories and should not be automatically added together. “Killed,” “died later,”
“injured,” “critically injured,” missing, explicit zero, and an unparseable vague
quantity require distinct handling. Named people are not a safe substitute for a
count, and a count must not be inferred from photographs.

For public-health use, source-reported fatalities should not be assumed to match a
harmonized surveillance definition or follow-up window. The corpus does not currently
reconcile hospital outcomes, police registries, or the internationally used
post-crash follow-up conventions. Researchers should align any downstream comparison
with the definitions and quality principles in the
[WHO road-traffic data-systems manual](https://www.who.int/publications/i/item/9789241598965)
and report the publication-time cutoff. Missing counts remain missing and must not be
treated as zero in rates or severity models.

## 13. Sentiment and public-response analysis

Sentiment extraction is limited to explicit, traffic-related expression. Each item
identifies holder, holder type, target, aspect, polarity, optional emotion, intensity,
sarcasm uncertainty, source, evidence, and confidence. The summary reports sample
size and traffic-relevant count. Reaction totals do not reveal polarity; grief or
anger about a death is not automatically sentiment about congestion, infrastructure,
enforcement, or policy.

Visible comments are a platform- and moderation-selected sample, not public opinion.
Accounts may be inauthentic; irony, code-switching, politeness, local idiom, and
translation can reverse or obscure meaning. Cross-country sentiment comparisons
therefore require validated language-specific annotation, disclosure of the comment
sampling mechanism, and measurement-invariance analysis. MGeoAI sentiment should be
reported as attributable examples and aspect counts within the captured material,
not population percentages.

## 14. Human review and adjudication

Human review is a constitutive part of this methodology, not a cosmetic final step.
The implemented corpus records reviewer identity, timestamp, decision, link checks,
and notes; the reviewer application supports authenticated, multi-reviewer source
approval. Software validation confirms that an accepted source has an accepted review
and a matching link check. It does not determine whether the reviewer is qualified or
whether two reviewers agree.

For the formal study, reviewers should receive a codebook and examples, complete a
calibration round, and declare relevant language/geographic competence and conflicts
of interest. The evaluation subset should be labeled independently by two reviewers,
with a third adjudicator or documented consensus process for disagreement. At minimum,
review should cover source eligibility, content-link match, source dependence,
incident grouping, event date, reported location and granularity, casualties,
assertion status, and material conflicts. Reviewer names may be pseudonymous in a
public release, while accountability records remain controlled.

Reviewers must be able to inspect source content and the exact evidence behind a
fused claim, not only an evidence ID. Approval should load the captured source through
the configured ingestion path; rejection should preserve an audit event rather than
delete the submission. High-impact operational use requires a human publication gate,
a correction/takedown procedure, and re-review when a source materially changes.

## 15. Validation and evaluation plan

### 15.1 Corpus validation

Before analysis, run structural validation and produce a signed or archived report.
The implemented validator checks country/manifest agreement, country and source
quotas, identifier uniqueness, source-country consistency, artifact integrity,
accepted-review linkage, content-matching verification, incident memberships, and
the required independent-source shared incident in each country. A content lock
should be generated after validation. Any validation issue makes that corpus version
ineligible for the headline study.

### 15.2 Reference annotation and split design

Create a human-adjudicated reference set that is stratified by country, language,
modality, source dependence, place granularity, casualty presence/conflict, and
matching difficulty. Freeze train/development/test partitions by incident and
dependency group so that syndicated copies and reports of the same event cannot
cross partitions. Hold curation-only IDs and labels out of provider input. Prompt,
lexicon, gazetteer, and threshold development must stop before the test set is
unsealed.

### 15.3 Metrics

Report at least:

- **Collection:** candidate-to-capture and capture-to-acceptance yield, failure reason,
  review time, and rights/access status by country.
- **Extraction:** field-level precision, recall, F1, and exact/partial agreement for
  time, location text, road users, vehicles, fatalities, injuries, traffic effects,
  and assertion type. Report coverage separately from accuracy.
- **Provenance:** proportion of extracted and fused material facts with a resolvable
  locator, valid evidence ID, and matching source content.
- **Matching:** pairwise precision, recall, F1, and confusion among same, related,
  different, and uncertain. The repository currently implements binary pairwise
  precision/recall/F1 while excluding ambiguous gold pairs; the study should add
  cluster-level B-cubed or equivalent measures and bridge-error analysis.
- **Fusion:** exact agreement or adjudicated semantic agreement by field, conflict
  detection/retention, unsupported-claim rate, unknown-versus-zero errors, and summary
  citation completeness.
- **Geolocation:** great-circle error for justified point references, containment in
  reviewed area/road geometry, granularity agreement, ambiguity retention, and
  confidence calibration. Do not compute point error against invented centroids.
- **Casualties:** exact count agreement, explicit-zero handling, reported-later
  update handling, conflict recall, and rate of missing values incorrectly converted
  to zero.
- **Sentiment:** aspect/target/holder/polarity agreement, traffic-relevance precision,
  sarcasm error, and coverage; no population inference.
- **Human factors:** reviewer agreement, review time, correction rate, and a structured
  usability assessment of evidence and uncertainty inspection.

### 15.4 Statistical analysis

Publish micro-averaged results for workload impact and macro-averaged country and
language results for transfer equity. Report medians and distributions, not only
means. Uncertainty intervals should use resampling or hierarchical models that cluster
by incident and country; treating repeated or syndicated sources as independent will
understate uncertainty. Predefine handling of uncertain labels. For human annotation,
use a statistic suitable to the task and number of raters (for example, Cohen's kappa
for two-rater nominal labels or Krippendorff's alpha for multiple raters/missingness),
alongside raw agreement and disagreement categories.

Avoid significance-only reporting. Provide effect sizes, uncertainty intervals,
sample sizes and missingness for every stratum. Country ranking is inappropriate when
test sets are small or composition differs. If model, prompt, geocoder, or corpus
changes after evaluation, treat the result as a new version rather than overwriting
the original analysis.

The repository's `extraction_coverage` function measures whether selected fields are
present; it does not measure whether those fields are correct. Recorded-provider demo
output and offline regression fixtures are software tests, not research evaluation.

### 15.5 Implemented paper-evaluation framework

The normalized human reference is `evaluation/gold/gold_incidents.json`. Its labels
point to immutable artifacts under `assets/scraps` instead of generated source IDs.
The reference unit is an incident, while source membership is resolved to run-specific
mentions during evaluation. The current subset contains six manually verified
incidents represented by curated HTML and YouTube-analysis inputs. The roundup in HTML
source 12 is explicitly split by location selector into Sylhet and Bogura incidents.
Paired image analyses are supporting modalities, not independently labelled sources.

Only annotator-supplied fields are scored. Fatalities and injuries retain numeric,
unknown, not-reported, and reported-zero states; a null reference is excluded from that
field's accuracy denominator. Textual places use normalized exact and required-term
agreement. Haversine distance is computed only when a trusted reference coordinate is
present; textual place names are never geocoded to manufacture reference points. No
incident-type or temporal score is emitted when those labels are absent.

Gold source grouping yields same-incident pair and cluster labels. The evaluator
reports confusion-matrix metrics, specificity, pairwise clustering, and B-cubed
precision/recall/F1. A source member that does not resolve to exactly one mention is
disclosed and excluded rather than force-matched. Major proportions and MAE use 2,000
deterministic bootstrap resamples (default seed 42). Thresholds are not tuned on this
small subset.

Unlabelled global data are evaluated separately using composition, source diversity,
modality support, information-completeness gain, provenance traceability, conflict
prevalence/preservation, unknown-versus-zero integrity, spatial representation,
provider usage, and matching efficiency. These are not accuracy metrics. The global
map distinguishes source-named incident locations from collection-country fallback
markers: a fallback makes a record visible but does not resolve the event location and
is excluded from incident-location coverage.

`mgeoai paper-evaluate` generates a canonical metric manifest, per-record CSVs,
researcher-facing Markdown, LaTeX tables/prose, discussion notes, raster/vector
figures, representative cases, and a validity report. The validity checker enforces
confusion-matrix arithmetic, percentage bounds, unknown/zero semantics, gold-file
provenance for every accuracy metric, and separation of source coverage from incident
geolocation. A major violation terminates the command with a nonzero exit.

## 16. Biases and threats to validity

The principal threats are:

- **Discovery and availability bias:** searchable and accessible publishers are not a
  census of reporting; paywalls, blocking, deletion, connectivity, and search ranking
  differ by country.
- **Newsworthiness bias:** fatalities, unusual vehicles, prominent victims, urban
  roads, and severe disruption are more likely to receive coverage.
- **Language/resource bias:** parsers, lexicons, models, and reviewers tend to perform
  better for high-resource languages and familiar scripts.
- **Publisher and dependence bias:** multiple URLs may derive from one agency report;
  apparent corroboration can be duplication.
- **Temporal bias:** early reports are incomplete, casualty totals change, pages are
  updated without clear version history, and publication time differs from event time.
- **Spatial bias:** place names are ambiguous, administrative boundaries change, road
  names are reused, and centroids create false visual precision.
- **Label bias:** reviewers can share assumptions, use inconsistent definitions, or
  infer from later knowledge unavailable in the original report.
- **Model and prompt drift:** hosted model behavior can change even under a stable
  model name; stochastic output and provider outages affect reproducibility.
- **Modality bias:** image/video analysis is a prior interpretation and may omit
  off-camera context, audio, metadata, or uncertainty.
- **Rights and safety filtering bias:** ethical exclusion of restricted or sensitive
  content changes the observable sample and must be disclosed.
- **Construct validity:** a fused news report is not the ground truth incident; source
  sentiment is not public opinion; report counts are not crash incidence.

Mitigations include prospective rules, transparent flow counts, dependency groups,
native-language review, controlled gold labels, stratified metrics, uncertainty-aware
maps, version locks, audit logs, correction procedures, and comparison with
independent authoritative data where lawful and methodologically compatible. These
steps reduce but do not eliminate bias.

## 17. Ethics, privacy, law, and governance

Traffic reports may name deceased or injured people, children, relatives, drivers,
commenters, and witnesses. Public availability does not remove the risk of harassment,
misidentification, or renewed harm. Collect only fields necessary for the registered
research questions; redact or pseudonymize unnecessary commenter identities; avoid
publishing precise home, hospital, or victim locations; and apply role-based access to
restricted payloads and review notes. The principles of purpose limitation and data
minimization in the
[EU General Data Protection Regulation](https://eur-lex.europa.eu/eli/reg/2016/679/2016-05-04)
are useful governance baselines even where another legal regime applies.

The study must document its institutional review/ethics determination, lawful basis,
data-retention period, security controls, access roles, breach response, correction
and takedown channel, cross-border transfer analysis, and rules for sensitive cases.
Local legal review is required; neither a robots allowance nor research intent alone
settles copyright, privacy, database-right, defamation, or data-protection questions.

The dashboard and exports must consistently state that MGeoAI fuses attributed
reports and does not establish truth or fault. Model output must not be used as an
automated determination of criminal liability, insurance responsibility, individual
risk, or entitlement. Risk management should be documented across governance,
mapping, measurement, and management, consistent with the
[NIST AI Risk Management Framework](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10).

## 18. Reproducibility and release procedure

A reproducible study release should archive:

- the corpus manifest, country/source/review/incident records, access-attempt log, and
  generated corpus lock;
- lawful payloads, plus hashes and controlled-access instructions for restricted
  payloads;
- source and output schema versions;
- code commit and release tag;
- the exact fusion prompt and hash;
- configuration, manual match overrides, multilingual lexicons, gazetteer/boundary
  versions, and materialization manifest;
- Python and frontend dependency locks and runtime versions;
- provider, exact model identifier, endpoint mode, generation parameters, timeout,
  retry, token, and cost limits;
- sanitized provider-run records and failed/retryable run status;
- reference-label codebook, split assignments, adjudication protocol, and analysis
  scripts; and
- corpus validation, backend tests, static analysis, frontend tests, accessibility
  checks, and production-build results.

Secrets belong only in untracked environment configuration. Raw provider responses
and prompts containing restricted evidence should be stored only when permitted and
with the same or stronger access controls as the input. Hosted-model runs may not be
bit-for-bit reproducible; request hashes, model identifiers, timestamps, and cached
validated responses make the remaining uncertainty auditable.

A minimal offline software check is:

```bash
python -m pip install -e '.[dev]'
pytest
ruff check src tests
mypy src/traffic_fusion
cd web && npm test && npm run lint && npm run build
```

The recorded provider can reproduce demonstration output without a network request,
but its results must not be substituted for a live-model evaluation. Live smoke tests
require explicit credentials, model, current pricing, timeout, token, and cost limits
and should use a small authorized test fixture.

## 19. Compact data dictionary

| Object | Primary role | Selected fields and interpretation |
|---|---|---|
| `CorpusManifest` | Freezes corpus identity and scope | Corpus ID/title, creation time, unique country codes, minimum-country/source/independence policy. |
| `CorpusCountry` | Defines a country stratum | ISO alpha-3 code, name, languages, IANA timezones, target source count. |
| `CorpusSource` | Governs one candidate/captured source | Status, traffic flag, publisher, URLs, artifacts, languages, keywords, timezone/times, capture method, independence/dependency group, redistribution status, latest review. |
| `PayloadArtifact` | Makes captured content verifiable | Role, safe relative path, SHA-256, byte size, UTF-8 encoding. |
| `AccessAttempt` | Preserves collection denominator | Candidate URL, attempt/time, explicit outcome, HTTP status, retryability and retry time. |
| `ReviewEvent` | Records a human source decision | Reviewer/time, accepted/rejected/needs-changes decision, per-link content check, note. |
| `CorpusIncident` | Holds protected reference grouping | Curation-only ID, country, source membership, reviewed/candidate/rejected label, reviewers/time. Never provider input. |
| `SourceRecord` | Canonical ingested-source metadata | Source type/ID, publisher/author/URI, relative local path, hash, times/timezone, languages/country, title, warnings, dependence. |
| `ParsedBlock` | Preserves document structure | Block kind/text/author/link/reactions and source locator. |
| `ProvenanceLocator` | Resolves a claim to source content | Source path, selector/JSON path/timestamp/image region, block ID, optional original text. |
| `EvidenceItem` | Represents one attributed claim | Modality/kind, assertion type, claim text, normalized claim, claimant, entities, casualties, places/times, confidence, assumptions/warnings, locator. |
| `IncidentMention` | Represents one source-local event | Event type/time, candidate locations, parties, vehicles, casualty claims, effects/response, uncertainty, completeness, primary/development relation. |
| `MatchDecision` | Records pair adjudication | Pair IDs, four-way relation, confidence, decisive evidence, contradictions, rationale, component scores, provider run. |
| `FusedFact` | Represents an evidence-backed field | Canonical field, value/state, supporting evidence, alternatives, contradiction, confidence, rationale. |
| `Geolocation` | Represents place and uncertainty | Name/hierarchy, WGS 84 coordinates, granularity, method, alternatives, evidence, confidence, ambiguity and radius. |
| `FusedIncident` | Publishes the derived incident record | Title/type/status, time/place/facts, parties/vehicles/effects/response, source/evidence IDs, independence, sentiment, unresolved questions, warnings, attributed summary. |
| `ProviderRun` | Audits model-assisted operations | Provider/model/prompt/request hashes, timing, tokens/cost, retries, finish/validation/cache/error status. |

Fields named `confidence` are system- or provider-level assessments unless a calibration
study says otherwise. They must not be interpreted as probabilities of real-world
truth. `independent_source_count` means distinct reviewed source-dependency support,
not a count of witnesses or confirmations. `generated_at` is derivation time, not event
or publication time.

## 20. Current implementation boundary and limitations

The following are currently implemented: strict corpus and pipeline models;
content-addressed artifacts and lock generation; quota, integrity, and review-link
validation; accepted-source materialization with gold-label separation; saved-HTML and
structured JSON ingestion; fine-grained provenance; international source metadata;
configurable traffic detection; heuristic/provider-assisted matching; constraint-aware
clustering; schema-constrained fusion; explicit unknown/conflict states; geographic
granularity and uncertainty fields; provider-run accounting; authenticated source
review; and offline backend/frontend tests.

The following remain human-governed: lawful access, source eligibility and content
verification, language adequacy, dependence classification, reviewed incident groups,
ambiguous geolocation, casualty-conflict adjudication, redistribution decisions,
ethics/legal review, corrections, and release approval.

The frozen 51-country collection list, 10-source-per-country quota, direct-link report,
and at least one automated distinct-domain multi-source candidate per country are now
implemented dataset artifacts. They are coverage and workflow results, not accuracy or
truth findings. The following remain study-stage requirements: qualified human review
of source eligibility, event-country assignment, pair identity, and source dependence;
balanced discovery across media systems; globally validated language lexicons; a
global gazetteer and historical boundaries; dual-coded reference annotations;
calibrated uncertainty; country/language/modal performance estimates; accessibility
audit; and analysis of downstream user effects. Until these are completed, no claim of
representative global coverage, globally reliable
geolocation, verified casualty surveillance, or cross-cultural sentiment validity is
warranted.

## 21. Reporting guidance

The final paper should follow an observational-study reporting checklist such as
[STROBE](https://www.equator-network.org/reporting-guidelines/strobe/) where applicable
and include a country-by-country appendix. Report the collection flow, exclusions,
missingness, source dependence, review process, corpus and code versions, prompt/model
details, all predefined metrics, subgroup distributions, corrections, and deviations
from this protocol. Examples should show both successful fusion and consequential
failure cases. Any factual statement derived from the corpus should be phrased as a
source-attributed report unless independently verified by a separately documented
method.
