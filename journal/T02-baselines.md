# T02 — Add baselines for matching comparison

Status: todo
Depends on: T01 (needs the larger benchmark for a meaningful comparison)

## Goal
Compare the full system against appropriate baselines, not only the
heuristic-only ablation.

## Done when
- [ ] Baselines chosen and justified (candidates: time+location rule only,
      TF-IDF/lexical similarity threshold, embedding similarity, LLM-only
      pairwise without deterministic guards).
- [ ] Each baseline implemented offline/reproducibly (live LLM runs need explicit
      credentials, model, pricing, timeout and cost limits per AGENTS.md).
- [ ] All systems evaluated on the same T01 benchmark with the same metrics and
      incident-level bootstrap CIs.
- [ ] Results table and short analysis ready for the manuscript.

## Notes
- Scoring lives in `src/traffic_fusion/matching.py`; ablation in `evaluation.py`.
- Live failures must stay failed; never silently fall back to recorded.

## Journal
