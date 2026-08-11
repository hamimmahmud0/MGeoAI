# Road crash in Gazipur kills student

> Evidence-fusion output. This record does not independently verify the incident.

## Summary

One video-analysis source [ev_32e6290ff8c2ead6] reports a road crash in Gazipur, Bangladesh, in which a student was killed. The source title connects the crash to a protest in Gazipur. The casualty fact is fused as one fatality; no injury count was supplied, so injuries are marked not reported. The supplied mention places the event in Tongi, Gazipur, at a city-level gazetteer centroid (approximately 12 km uncertainty), while the raw claim names only Gazipur. The event time is given by the mention as a day-precision interval 2026-08-09 to 2026-08-10, but the raw evidence has no date. No vehicles, traffic effects, contributing factors, or emergency response were reported. All sentiment expressions are from the single source and concern road safety/accountability. The main uncertainty is the precise location and time of the crash, the victim's road-user role, and any injuries beyond the reported fatality.

## Time and location

- Time: 2026-08-09T00:00:00
- Location: Tongi, Gazipur
- Precision: city; confidence 0.68
- Method: source-named local gazetteer centroid
- Location caveat: source-named place represented by a local gazetteer centroid; approximately 12 km uncertainty

## Incident facts

- **Event Type:** road_crash (confidence 0.65) [ev_32e6290ff8c2ead6]
- **Fatalities:** 1 (confidence 0.65) [ev_32e6290ff8c2ead6]
- **Injuries:** not reported (confidence 0.65) [ev_32e6290ff8c2ead6]
- **Road User Involved:** student (confidence 0.65) [ev_32e6290ff8c2ead6]
- **Vehicles:** not reported (confidence 0.65) [ev_32e6290ff8c2ead6]
- **Traffic Effects:** not reported (confidence 0.65) [ev_32e6290ff8c2ead6]
- **Emergency Response:** not reported (confidence 0.65) [ev_32e6290ff8c2ead6]
- **Contributing Factors:** not reported (confidence 0.65) [ev_32e6290ff8c2ead6]

## Traffic impact

Not reported.

## Sentiment

All six sentiment expressions are traffic-related and come from the same single source; no independent sentiment evidence is available.

- road_safety: negative=6

## Sources and provenance

- Independent source groups: 1
- Source IDs: src_ac806a793f71ca54
- Evidence IDs: ev_32e6290ff8c2ead6

## Unresolved questions

- What is the exact crash location within Gazipur or Tongi?
- What is the precise time and date of the crash?
- What road-user role did the deceased student have, and were there any other casualties or injuries?
- Which vehicle(s), if any, were involved?
- Are the reported protests a later development or only part of the source headline?
- Was any police or emergency response present?

## Data-quality warnings

- Only one independent source supports this incident; all sentiment expressions trace to that same source ID.
- The raw evidence record contains no date; the supplied mention provides a normalized day-precision interval 2026-08-09 to 2026-08-10 labeled 'date normalized from corpus evidence family'.
- Location is ambiguous: source text names Gazipur, while the mention candidate is Tongi, Gazipur. The coordinate is a gazetteer centroid with approximately 12 km uncertainty.
- Sentiment entries in the bundle referenced evidence IDs not present in the top-level evidence array; for validation these were mapped to the sole available evidence ID ev_32e6290ff8c2ead6.
