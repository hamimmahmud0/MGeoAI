# Task: collect candidate road-crash news reports for a matching benchmark

## Purpose
We are building an evaluation set for deciding whether two news reports describe
the SAME real-world road-traffic incident. You find the reports; human annotators
decide the labels later. Use web search and open every page you list.

Attach `candidates.schema.json`. Return ONE JSON object that validates against it.
Output JSON only: no commentary, no code fences.

## Parameters (edit before each batch)
- Batch id: `b01`  (next: b02, b03, ...)
- Next group id: `g001`  (continue the numbering from the previous batch)
- Date window for incidents: 2025-01-01 to 2026-06-30
- Already collected (do NOT reuse any of these URLs or incidents; paste the list
  of URLs and one-line incident descriptions from earlier batches here, or write
  "none" for the first batch):
  `<<ALREADY_COLLECTED>>`

## Quota for this batch: 20 groups
| Region | Language | same_incident groups | decoy_cluster groups |
|---|---|---|---|
| Bangladesh | English and Bangla (mix; at least 3 groups containing a Bangla article) | 6 | 4 |
| International (any country outside Bangladesh) | English only | 6 | 4 |
| **Total** | | **12** | **8** |

Inside that quota:
- At least 6 of the 20 groups must be `difficulty: "hard"` (see below), at least 3
  of them in each region.
- International groups: at least 4 different countries in the batch, no more than
  3 groups from any one country, and include at least 2 countries outside
  Asia. Do not use only the biggest English-language outlets.
- Spread incident dates over the window: no more than 6 groups from any single month.
- No outlet may supply more than 5 articles in the batch.
If you cannot reach a quota, return fewer groups and say which quota is short in
`batch_report`. Never pad with weak or unopened pages to hit a number.

## What to find

### A. `same_incident` groups (12 per batch)
One real incident reported by 2 to 4 articles from DIFFERENT outlets, ideally 3.
- At least 2 of the articles must be original reports by different publishers.
- Reposts and wire copies may be listed (set `syndicated_copy_of`) but do not
  count toward the 2-outlet minimum.
- `difficulty: "easy"`: reports agree on place, date, vehicles and casualty numbers.
- `difficulty: "hard"`: the same incident but the reports differ, for example in
  language (Bangla vs English), in casualty counts (early report vs updated toll),
  in how the location is named, in headline framing, or in which details they
  mention. Set `confusable_by` to the reason (`update_with_changed_numbers`,
  `different_language`, `different_headline_framing`).

### B. `decoy_cluster` groups (8 per batch)
1 to 3 articles about DIFFERENT incidents that could be mistaken for a
same_incident group. Set `decoy_for` to that group's `group_id` (it may be from this
batch or an earlier one) and list the shared features in `confusable_by`:
same place, same road, same day, same vehicle type, similar casualty count, same
cause, or an update with changed numbers about a different crash.
- A decoy incident must be a genuinely different event from the group it is a
  decoy for. If you are unsure that it is different, do not use it.
- Make decoys hard: they should share at least one concrete feature (same road,
  same junction, same day, same vehicle type). Random unrelated crashes are not useful.
- Set `difficulty: "hard"` for decoys that share two or more features.

## Duplicate rules (strict)
1. Every URL appears once in the whole batch and never appears in
   `<<ALREADY_COLLECTED>>`. Compare URLs after removing tracking parameters
   (`utm_*`, `fbclid`, `gclid`, etc.), fragments and trailing slashes; also treat
   `amp` and mobile versions as the same page.
2. One real incident belongs to one group only. A `same_incident` group's incident
   must not appear in any other group, and a decoy's incident must differ from every
   same_incident incident you return. Check this before you finish.
3. Do not list two articles from the same outlet in one same_incident group unless
   a third outlet is also present, and never count them as independent.
4. Two pages with identical text under different URLs are reposts: keep one, mark the
   other with `syndicated_copy_of`, or skip it with reason `duplicate_url` or `repost_only`.
5. Do not return the same incident in two languages as two separate groups: put the
   Bangla and English reports of one incident in the same group.

## Verification rules
- Open every URL. Set `url_opened: true` only if the page loaded and you read the
  article text. Do not guess or reconstruct URLs, dates, places or titles.
- Use null when a value is not stated. Copy `event_date_stated` and
  `location_stated` as the article states them; do not infer them from other sources.
- `published_date` is the article's own date (YYYY-MM-DD). Skip pages with no date
  and no way to place them in the window.
- Include only road-traffic crashes (collisions, overturns, pedestrian or cyclist
  strikes, vehicle fires after a crash). Skip rail, air, water and non-crash events.
- Public pages only. Do not log in, bypass a paywall, or use archive or cache sites.
  If a page is paywalled, set `paywalled: true` and prefer to skip it.
- Group incidents by the articles' own stated facts (place, time, vehicles, people
  involved). Your grouping is a claim for annotators to check, not ground truth.
  If you are unsure, still return the group and say so in `agent_note`.

## Content rules
- No fault, blame, cause speculation or sentiment from you. `agent_note` is one short
  factual sentence about why the articles are grouped or why a decoy is confusable.
- Do not copy article text into the output, only the fields in the schema.
- Skip pages whose main content is graphic imagery, and do not describe victims
  beyond what the headline states.

## Final self-check (do this before answering)
- Group counts per region and kind match the quota, or the shortfall is explained.
- No duplicate URL, no incident in two groups, no decoy that is actually the same incident.
- Every listed article has `url_opened: true` (otherwise it belongs in `skipped`).
- `batch_report.counts` matches the groups you returned; every excluded page you
  considered is in `skipped` with a reason.
