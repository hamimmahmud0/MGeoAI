from traffic_fusion.evaluation import matching_metrics
from traffic_fusion.models import MatchDecision, MatchFeatures


def test_matching_metrics_exclude_ambiguous_pairs() -> None:
    features = MatchFeatures(
        time_score=1,
        location_score=1,
        entity_score=0,
        vehicle_score=0,
        lexical_score=1,
        total_score=1,
    )
    gold = [
        {"left": "a", "right": "b", "label": "same_incident"},
        {"left": "a", "right": "c", "label": "different_incident"},
        {"left": "x", "right": "y", "label": "ambiguous"},
    ]
    decisions = [
        MatchDecision(
            left_mention_id="a",
            right_mention_id="b",
            decision="same_incident",
            confidence=1,
            rationale="fixture",
            features=features,
        )
    ]
    metrics = matching_metrics(gold, decisions)
    assert metrics["precision"] == metrics["recall"] == metrics["f1"] == 1
    assert metrics["ambiguous_excluded"] == 1
