# Annotator guidelines: same incident or not?

For the four annotators (hamim, oishik, mubasshir, rubayet). Read once before you start.
The administrator's runbook is [ANNOTATION.md](ANNOTATION.md).

## Your task
You see two news reports, **Report A** and **Report B**. Decide whether they describe the
**same real-world road crash**. There are 230 pairs, in English and Bangla, from Bangladesh
and other countries. You label every pair, independently of the other three annotators.

Your labels measure how well an automated matcher agrees with careful human readers, so
honest, independent judgement matters more than speed or agreement with colleagues.

## The four labels

| Label | Use it when | Typical signs |
|---|---|---|
| **Same incident** | Both reports are about one and the same crash. | Same place and day, same vehicles or people, even if numbers, times or wording differ. |
| **Related, distinct** | Two different crashes that share context. | Same road, junction or district; same day; same vehicle type; a later, separate crash at the same black spot; a similar casualty count. |
| **Different** | The reports are about unrelated events. | Different place and time, nothing shared beyond "a road crash happened". |
| **Cannot tell** | After careful reading you cannot decide. | Text too short, cut off, missing the place or time, or genuinely contradictory. Use sparingly and add a note. |

### Decision procedure
1. Find the **anchors** in each report: *where* (place, road, junction), *when* (date, time
   of day), *who/what* (vehicle types, people, organisations).
2. If the anchors agree well enough that a reasonable editor would say "that is the same
   crash", choose **Same incident**, even when the details differ (see below).
3. If the anchors point to two separate events but share a place, road, day, vehicle type or
   cause, choose **Related, distinct**.
4. If they share nothing meaningful, choose **Different**.
5. Only if steps 2 to 4 cannot be settled from the text, choose **Cannot tell**.

### These differences do NOT make it a different incident
- An **updated casualty count** (an early report says 3 dead, a later one says 8).
- Different **times** that are close (about 11:00 vs 12:00), or "morning" vs a clock time.
- A place named at **different precision** (the highway vs the nearest town, upazila or
  district; a landmark vs an area).
- A **different language** or a different headline framing.
- **Publication on different days** when one is a follow-up of the same crash.
- Different details being mentioned (one report names the victims, the other the vehicle).

### These differences DO matter
- Different **dates** of the event (not just the publication date).
- Clearly different **places** (another district, town or highway).
- Incompatible **vehicles or circumstances** (a bus and a truck in one report, a motorbike
  and a pedestrian in the other).
- A casualty count that is the **same by coincidence** while everything else differs.

## Worked examples (synthetic)

| Report A | Report B | Label | Why |
|---|---|---|---|
| Bus and truck collide near Mile 12, Highway 7, at dawn; two injured. | Two hurt as bus, truck collide near Mile 12 on Highway 7, early morning. | Same incident | Same place, time, vehicles and count. |
| A ferry capsized; officials say several are missing. | The death toll from the capsized ferry rose to five. | Same incident | A later update of the same event. |
| Motorbike rider dies at Central Junction on Monday evening. | Pedestrian struck at Central Junction on Monday evening. | Related, distinct | Same junction and time, but different vehicles and victims. |
| Car overturns on the ring road on Tuesday; driver unhurt. | Truck overturns on the ring road on Thursday, blocking traffic. | Related, distinct | Same road, different vehicle and day. |
| Bus plunges into a ravine in the north. | Truck crash on a coastal road in the south. | Different | Nothing shared. |
| A crash on "the highway" last week. | A crash on a highway. | Cannot tell | No anchors to compare. |

## Rules of independence
- **Do not discuss** pairs, labels or doubts with the other annotators until all four of you
  have finished, and the administrator has computed agreement.
- **Do not look at the pipeline results** (Overview map, incident list, Sources page, any
  generated reports) and do not ask an AI assistant. They would reveal what an automated
  system thinks.
- **Do not search for outside information** about the incidents. The text shown, and the
  "Open original" link if the text looks incomplete or ends abruptly, are your evidence.
- Judge the **text**, not the headline, and not which outlet published it.
- Take each pair on its own. Do not try to keep your label counts balanced or to find
  patterns in the order of pairs; the order and the left/right placement are shuffled
  differently for each annotator.
- You may **edit a label** later. Every save is recorded as a new revision and the latest
  one counts. Do not change labels after reading colleagues' views.

## Notes field
Optional, but useful for **Cannot tell**, and for borderline **Related, distinct** versus
**Same incident**. Write one short factual sentence (for example "Place matches, but one
report says motorbike, the other bus"). Do not copy long passages, and do not include
personal details about victims.

## Practical points
- **Time:** expect 1 to 3 minutes per pair, about 5 to 8 hours in total. Spread it over
  several sessions; fatigue lowers label quality.
- **Content:** the reports describe deaths and injuries. Pause, or ask the administrator to
  reassign pairs, if this becomes distressing.
- **Text quirks:** long articles are cut at about 6,000 characters, and a few pages end with
  site footer lines (for example a contact line). Ignore footer text.
- **Progress:** the page shows "x/230 labelled" and your own label for each pair. You can
  move with Previous and Next; you must press **Submit label** (or **Update label**) to save.
- **Sign-in:** username in lowercase, with the password the administrator gave you. Sign
  out on shared computers.
- **Problems:** a pair that looks broken (empty text, wrong language, same article twice)
  should be labelled **Cannot tell** with a note describing the problem.

## Optional calibration round
Before the real work, the four of you can independently label the six synthetic examples
above on paper, then compare reasoning. Stop at agreeing how to read the rules; do **not**
discuss real benchmark pairs.
