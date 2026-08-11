# Road crash death of student sparks three-hour Dhaka-Mymensingh Highway blockade in Tongi

> Evidence-fusion output. This record does not independently verify the incident.

## Summary

Reports describe a road accident in Tongi, Gazipur, in which a madrasa student, Yasin Ali, died, prompting students to block the Dhaka-Mymensingh Highway around 11am at the Asia Pump and Gazipur bus stand area [ev_25f22aa562f7533f][ev_9012296fa587ace1]. The posts and The Daily Star agree on one fatality, but give the victim's age differently: 15 in the Bengali post and 17 in The Daily Star [ev_33738fa816ada880][ev_9012296fa587ace1]. No injury count is reported. The blockade lasted about three hours and caused roughly 15 km of severe congestion, affecting thousands of passengers [ev_25f22aa562f7533f]. Police from Tongi East and Tongi West police stations were deployed and tried to persuade students to leave [ev_68d7f18f8fe461ea]; The Daily Star reports students ended the blockade around 3pm after police assured them their demand for foot overbridges would be met [ev_4be9adbfb1ccf9b1]. Location precision is limited to a road-segment centroid near Asia Pump in Tongi, with about 1 km uncertainty. The two independent sources are corroborating but not fully identical in metadata; one is a single Bengali post with no publisher metadata. The exact crash time, vehicle(s) involved, and circumstances of the accident remain unreported.

## Time and location

- Time: 2026-08-09T00:00:00
- Location: Asia Pump area, Tongi, Gazipur
- Precision: road_segment; confidence 0.75
- Method: source-named local gazetteer centroid
- Location caveat: source-named place represented by a local gazetteer centroid; approximately 1 km uncertainty

## Incident facts

- **Fatalities:** 1 (confidence 0.90) [ev_9012296fa587ace1] [ev_25f22aa562f7533f] [ev_33738fa816ada880]
- **Injuries:** not reported (confidence 0.80)

## Traffic impact

About 15 km of severe congestion along the highway was caused by the blockade; thousands of passengers suffered [ev_25f22aa562f7533f][ev_33738fa816ada880].

## Sentiment

Seven supplied traffic-related sentiment expressions, all negative, express frustration over congestion/delay and concern over road safety and incident accountability. No mixed or positive traffic sentiment was supplied.

- congestion_delay: negative=5
- road_safety: negative=2

## Sources and provenance

- Independent source groups: 2
- Source IDs: src_96c9878e5c29c473, src_064d6b3f7a7be59c
- Evidence IDs: ev_25f22aa562f7533f, ev_33738fa816ada880, ev_4be9adbfb1ccf9b1, ev_68d7f18f8fe461ea, ev_9012296fa587ace1, ev_d9abeb718696a746

## Unresolved questions

- What was the exact time, mechanism, and vehicle(s) involved in the crash that killed Yasin?
- What are the victim's correct age and full identity (15 or 17; Yasin Ali vs Yasin)?
- Was anyone injured in the road accident?
- Were any official findings or charges announced after the police response?

## Data-quality warnings

- Victim age conflict: Bengali post reports Yasin Ali, 15; The Daily Star reports Yasin, 17. The fused facts preserve one fatality but not a single age.
- Source src_96c9878e5c29c473 has no publisher metadata, publication time, or source URI; source independence is flagged unknown.
- Mention extraction labeled 'bus' as a vehicle, but the supplied text only names Gazipur bus stand; no vehicle involvement is supported, so vehicles is empty.
- Time precision is day for the crash from corpus normalization; the 11am and 3pm times in sources refer to the blockade, not the crash time.
