from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Protocol

from traffic_fusion.config import Settings
from traffic_fusion.models import IncidentMention, MatchDecision, MatchFeatures


class MatchAdjudicator(Protocol):
    def adjudicate(
        self, left: IncidentMention, right: IncidentMention, features: MatchFeatures
    ) -> MatchDecision: ...


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def score_pair(left: IncidentMention, right: IncidentMention, settings: Settings) -> MatchFeatures:
    hard_guard = None
    time_score = 0.25
    if left.event_time.start and right.event_time.start:
        days = abs((left.event_time.start - right.event_time.start).total_seconds()) / 86400
        time_score = max(0.0, 1 - days / max(settings.max_days_apart, 1))
        if (
            days > settings.max_days_apart
            and left.relation_type == right.relation_type == "primary"
        ):
            hard_guard = f"event dates differ by {days:.1f} days"
    # Country fallback markers exist only to keep unresolved records visible on
    # the map. They are not incident-location evidence and must never create a
    # matching edge between otherwise unrelated reports from the same country.
    left_locations = {
        item.hierarchy.get("anchor", item.normalized_name)
        for item in left.locations
        if item.granularity != "country"
    }
    right_locations = {
        item.hierarchy.get("anchor", item.normalized_name)
        for item in right.locations
        if item.granularity != "country"
    }
    location_score = _jaccard(left_locations, right_locations)
    if left_locations and right_locations and not left_locations & right_locations:
        if left.relation_type == right.relation_type == "primary":
            hard_guard = "specific normalized locations conflict"
    entity_score = _jaccard(
        set(left.people + left.organizations), set(right.people + right.organizations)
    )
    vehicle_score = _jaccard(set(left.vehicles), set(right.vehicles))
    left_countries = {
        item for item in left.lexical_features if item.startswith("country:")
    }
    right_countries = {
        item for item in right.lexical_features if item.startswith("country:")
    }
    if left_countries and right_countries and left_countries != right_countries:
        hard_guard = "source-assigned incident countries conflict"
    # Exclude generic and country-control terms from lexical contribution.
    generic = {"road", "accident", "road_crash", "crash", "fatal", "incident", "unknown"}
    left_lexical = {
        item for item in left.lexical_features if item not in generic and not item.startswith("country:")
    }
    right_lexical = {
        item for item in right.lexical_features if item not in generic and not item.startswith("country:")
    }
    lexical_score = _jaccard(left_lexical, right_lexical)
    total = (
        0.30 * time_score
        + 0.35 * location_score
        + 0.15 * entity_score
        + 0.05 * vehicle_score
        + 0.15 * lexical_score
    )
    if location_score == 1 and lexical_score > 0:
        total = max(total, 0.74)
    if lexical_score >= 0.5 or left_lexical & right_lexical:
        total = max(total, 0.62)
    return MatchFeatures(
        time_score=time_score,
        location_score=location_score,
        entity_score=entity_score,
        vehicle_score=vehicle_score,
        lexical_score=lexical_score,
        total_score=0 if hard_guard else min(total, 1),
        hard_guard=hard_guard,
    )


def candidate_pairs(
    mentions: list[IncidentMention], settings: Settings
) -> list[tuple[IncidentMention, IncidentMention, MatchFeatures]]:
    pairs: list[tuple[IncidentMention, IncidentMention, MatchFeatures]] = []
    for left, right in combinations(mentions, 2):
        if left.source_id == right.source_id:
            continue
        left_countries = {
            item for item in left.lexical_features if item.startswith("country:")
        }
        right_countries = {
            item for item in right.lexical_features if item.startswith("country:")
        }
        # A missing edge already keeps clusters separate. Persisting a rejected
        # decision for every cross-country pair grows quadratically while adding
        # no information to matching or fusion.
        if left_countries and right_countries and left_countries != right_countries:
            continue
        features = score_pair(left, right, settings)
        if features.hard_guard or features.total_score >= settings.possible_match_threshold:
            pairs.append((left, right, features))
    return pairs


def decide_pairs(
    mentions: list[IncidentMention], provider: MatchAdjudicator, settings: Settings
) -> list[MatchDecision]:
    decisions: list[MatchDecision] = []
    overrides_must = {frozenset(pair) for pair in settings.must_link}
    overrides_cannot = {frozenset(pair) for pair in settings.cannot_link}
    for left, right, features in candidate_pairs(mentions, settings):
        pair_key = frozenset((left.mention_id, right.mention_id))
        if pair_key in overrides_must:
            decisions.append(
                MatchDecision(
                    left_mention_id=left.mention_id,
                    right_mention_id=right.mention_id,
                    decision="same_incident",
                    confidence=1,
                    rationale="Manual must-link override",
                    decisive_evidence_ids=left.evidence_ids[:1] + right.evidence_ids[:1],
                    features=features,
                )
            )
        elif pair_key in overrides_cannot or features.hard_guard:
            decisions.append(
                MatchDecision(
                    left_mention_id=left.mention_id,
                    right_mention_id=right.mention_id,
                    decision="different_incident",
                    confidence=1 if pair_key in overrides_cannot else 0.95,
                    rationale="Manual cannot-link override"
                    if pair_key in overrides_cannot
                    else features.hard_guard or "hard guard",
                    contradictions=[features.hard_guard] if features.hard_guard else [],
                    features=features,
                )
            )
        else:
            decisions.append(provider.adjudicate(left, right, features))
    return decisions


def build_clusters(
    mentions: list[IncidentMention], decisions: list[MatchDecision]
) -> list[list[str]]:
    parent = {mention.mention_id: mention.mention_id for mention in mentions}
    cannot = {
        frozenset((decision.left_mention_id, decision.right_mention_id))
        for decision in decisions
        if decision.decision in {"different_incident", "related_but_distinct"}
    }

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def members(root: str) -> set[str]:
        return {key for key in parent if find(key) == root}

    for decision in sorted(decisions, key=lambda item: item.confidence, reverse=True):
        if decision.decision != "same_incident":
            continue
        left_root, right_root = find(decision.left_mention_id), find(decision.right_mention_id)
        if left_root == right_root:
            continue
        if any(
            frozenset((a, b)) in cannot for a in members(left_root) for b in members(right_root)
        ):
            continue
        parent[right_root] = left_root

    grouped: dict[str, list[str]] = defaultdict(list)
    for mention in mentions:
        grouped[find(mention.mention_id)].append(mention.mention_id)
    return [sorted(group) for group in grouped.values()]
