from pathlib import Path

import pytest

from traffic_fusion import paper_evaluation
from traffic_fusion.paper_evaluation import RunArtifacts, generate_paper_evaluation

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "evaluation/gold/gold_incidents.json"


def test_gold_manifest_resolves_roundup_mentions_without_mutating_scraps() -> None:
    run = RunArtifacts(ROOT / "outputs/demo")
    gold = paper_evaluation._json(GOLD)
    resolved, issues = paper_evaluation.resolve_gold_mentions(gold, run)

    assert len(gold["incidents"]) == 6
    assert len(resolved["gold-001-purbachal"]) == 6
    assert len(resolved["gold-002-tongi"]) == 3
    assert len(resolved["gold-005-sylhet"]) == 1
    assert len(resolved["gold-006-bogura"]) == 2
    assert any(
        item["gold_id"] == "gold-005-sylhet"
        and item["path"] == "youtube/video_05.json"
        and item["reason"] == "no_matching_mention"
        for item in issues
    )


def test_paper_evaluation_generates_valid_separated_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        paper_evaluation,
        "_generate_figures",
        lambda *_args, **_kwargs: [],
    )
    result = generate_paper_evaluation(
        ROOT / "outputs/demo",
        GOLD,
        tmp_path,
        ROOT / "outputs/global-v1",
        42,
    )

    assert result["status"] == "complete"
    assert result["gold_incidents"] == 6
    validation = paper_evaluation._json(tmp_path / "results/validation_report.json")
    assert validation["status"] == "valid"
    metrics = paper_evaluation._json(tmp_path / "results/paper_metrics.json")
    assert metrics["fatality_exact_match"]["metric_type"] == "gold_accuracy"
    assert metrics["provenance_coverage"]["metric_type"] == "structural"
    assert "accuracy" not in metrics["provenance_coverage"]["description"].casefold()
    assert metrics["map_marker_coverage"]["value"] == 1.0
    assert metrics["geolocation_coverage"]["value"] < 0.02
    assert metrics["provenance_coverage"]["n"] == 211


def test_incident_two_clarification_preserves_unknown_injuries() -> None:
    gold = paper_evaluation._json(GOLD)
    incident = next(item for item in gold["incidents"] if item["gold_id"] == "gold-002-tongi")

    assert incident["fatalities"] == 1
    assert incident["injuries"] is None
