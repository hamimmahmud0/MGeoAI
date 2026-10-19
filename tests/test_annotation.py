from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from traffic_fusion.annotation.cli import annotate_app
from traffic_fusion.annotation.stats import (
    agreement_report,
    consensus,
    krippendorff_alpha_nominal,
)
from traffic_fusion.annotation.store import AnnotationStore
from traffic_fusion.api.app import create_app
from traffic_fusion.api.moderation import hash_reviewer_password

NAMES = ["hamim", "oishik", "mubasshir", "rubayet"]
SEED = Path(__file__).parent / "fixtures" / "annotation_seed_items.json"
FORBIDDEN = ("category", "selection", "pipeline", "decision", "score")


@pytest.fixture(scope="module")
def reviewers_json() -> str:
    # PBKDF2 is deliberately slow; hash once per module.
    hashes = {name: hash_reviewer_password(f"pw-{name}-0123456789") for name in NAMES}
    hashes["Not A Valid Name"] = hash_reviewer_password("pw-odd-0123456789")
    return json.dumps(hashes)


@pytest.fixture
def ann_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reviewers_json: str) -> Path:
    monkeypatch.setenv("MGEOAI_REVIEWERS_JSON", reviewers_json)
    monkeypatch.setenv("MGEOAI_SESSION_SECRET", "x" * 40)
    directory = tmp_path / "annotation"
    result = CliRunner().invoke(annotate_app, ["import-items", str(SEED), "--dir", str(directory)])
    assert result.exit_code == 0, result.output
    return directory


def make_client(ann_dir: Path, tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "data", annotation_dir=ann_dir))


@pytest.fixture
def client(ann_dir: Path, tmp_path: Path) -> TestClient:
    return make_client(ann_dir, tmp_path)


def login(client: TestClient, name: str, password: str | None = None) -> str:
    response = client.post(
        "/api/reviewer/login",
        json={"username": name, "password": password or f"pw-{name}-0123456789"},
    )
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def test_wrong_password_is_rejected(client: TestClient) -> None:
    bad = client.post("/api/reviewer/login", json={"username": "hamim", "password": "nope"})
    assert bad.status_code == 401


def test_items_and_submit_require_session(client: TestClient) -> None:
    assert client.get("/api/annotate/items").status_code == 401
    response = client.put("/api/annotate/labels/syn-001", json={"label": "same_incident"})
    assert response.status_code == 401


def test_submit_requires_csrf_token(client: TestClient) -> None:
    csrf = login(client, "hamim")
    body = {"label": "same_incident"}
    assert client.put("/api/annotate/labels/syn-001", json=body).status_code == 403
    ok = client.put("/api/annotate/labels/syn-001", json=body, headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200


def test_unsupported_annotator_name_is_refused(client: TestClient) -> None:
    login(client, "Not A Valid Name", "pw-odd-0123456789")
    assert client.get("/api/annotate/items").status_code == 403


def test_items_hide_selection_and_pipeline_data(client: TestClient) -> None:
    login(client, "hamim")
    body = client.get("/api/annotate/items").json()
    assert body["total"] == 4
    text = json.dumps(body).lower()
    assert not any(word in text for word in FORBIDDEN)


def test_annotators_cannot_see_each_others_labels(ann_dir: Path, tmp_path: Path) -> None:
    a, b = make_client(ann_dir, tmp_path), make_client(ann_dir, tmp_path)
    csrf_a = login(a, "hamim")
    login(b, "oishik")
    put = a.put(
        "/api/annotate/labels/syn-001",
        json={"label": "same_incident", "notes": "secret"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert put.status_code == 200
    rows = {r["item_id"]: r for r in b.get("/api/annotate/items").json()["items"]}
    assert rows["syn-001"]["my_label"] is None
    assert "secret" not in b.get("/api/annotate/items").text


def test_edit_appends_and_latest_wins(client: TestClient, ann_dir: Path) -> None:
    csrf = login(client, "hamim")
    headers = {"X-CSRF-Token": csrf}
    client.put("/api/annotate/labels/syn-002", json={"label": "different"}, headers=headers)
    second = client.put(
        "/api/annotate/labels/syn-002",
        json={"label": "related_distinct", "notes": "same junction"},
        headers=headers,
    ).json()
    assert second["revision"] == 2
    assert len((ann_dir / "labels" / "hamim.jsonl").read_text().splitlines()) == 2
    rows = {r["item_id"]: r for r in client.get("/api/annotate/items").json()["items"]}
    assert rows["syn-002"]["my_label"]["label"] == "related_distinct"


def test_unknown_item_is_404(client: TestClient) -> None:
    csrf = login(client, "hamim")
    response = client.put(
        "/api/annotate/labels/nope", json={"label": "different"}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 404


def test_order_and_sides_differ_per_annotator(ann_dir: Path, tmp_path: Path) -> None:
    orders = []
    for name in NAMES:
        c = make_client(ann_dir, tmp_path)
        login(c, name)
        orders.append(tuple(r["item_id"] for r in c.get("/api/annotate/items").json()["items"]))
    assert len(set(orders)) > 1


def test_init_users_writes_private_files_and_never_echoes_passwords(tmp_path: Path) -> None:
    directory = tmp_path / "annotation"
    result = CliRunner().invoke(annotate_app, ["init-users", *NAMES, "--dir", str(directory)])
    assert result.exit_code == 0, result.output
    passwords = (directory / "initial_passwords.txt").read_text().splitlines()
    assert len(passwords) == 4
    for path in (directory / "initial_passwords.txt", directory / "reviewers.json"):
        assert oct(path.stat().st_mode & 0o777) == "0o600"
    for line in passwords:
        assert line.split("\t")[1] not in result.output
    hashes = json.loads((directory / "reviewers.json").read_text())
    assert set(hashes) == set(NAMES)
    assert all(value.startswith("pbkdf2_sha256$") for value in hashes.values())


def test_agreement_and_consensus(ann_dir: Path) -> None:
    store = AnnotationStore(ann_dir)
    votes = {
        "syn-001": ["same_incident"] * 4,
        "syn-002": ["different", "different", "different", "related_distinct"],
        "syn-003": ["same_incident", "same_incident", "cannot_tell", "same_incident"],
        "syn-004": ["different", "related_distinct", "same_incident", "cannot_tell"],
    }
    for item, labels in votes.items():
        for name, label in zip(NAMES, labels, strict=True):
            store.append_label(name, item, label, "")  # type: ignore[arg-type]
    report = agreement_report(store.all_latest())
    assert report["krippendorff_alpha_nominal"] is not None
    assert len(report["pairwise_cohen_kappa"]) == 6
    result = consensus(store.all_latest())
    assert result["syn-001"]["label"] == "same_incident"
    assert result["syn-004"]["label"] is None
    out = ann_dir / "gold.json"
    cli = CliRunner().invoke(annotate_app, ["export", "--output", str(out), "--dir", str(ann_dir)])
    assert cli.exit_code == 0
    gold = json.loads(out.read_text())
    assert {row["label"] for row in gold} <= {"same_incident", "different", "ambiguous"}
    assert set(gold[0]) >= {"left", "right", "label"}


def test_krippendorff_known_value() -> None:
    assert krippendorff_alpha_nominal([["a", "a"], ["b", "b"], ["a", "a"]]) == pytest.approx(1.0)
    mixed = krippendorff_alpha_nominal([["a", "b"], ["a", "b"], ["a", "a"], ["b", "b"]])
    assert mixed is not None and mixed < 1.0


def test_import_refuses_after_labels_exist(ann_dir: Path) -> None:
    AnnotationStore(ann_dir).append_label("hamim", "syn-001", "different", "")
    args = ["import-items", str(SEED), "--dir", str(ann_dir)]
    blocked = CliRunner().invoke(annotate_app, args)
    assert blocked.exit_code == 1
    assert "orphan" in blocked.output
    assert CliRunner().invoke(annotate_app, [*args, "--force"]).exit_code == 0


def test_init_users_keeps_existing_accounts_unless_reset(tmp_path: Path) -> None:
    directory = tmp_path / "annotation"
    runner = CliRunner()
    assert runner.invoke(annotate_app, ["init-users", "hamim", "--dir", str(directory)]).exit_code == 0
    first = json.loads((directory / "reviewers.json").read_text())
    again = runner.invoke(annotate_app, ["init-users", "hamim", "oishik", "--dir", str(directory)])
    assert again.exit_code == 0 and "Kept existing: hamim" in again.output
    merged = json.loads((directory / "reviewers.json").read_text())
    assert merged["hamim"] == first["hamim"] and "oishik" in merged
    assert len((directory / "initial_passwords.txt").read_text().splitlines()) == 2
    runner.invoke(annotate_app, ["init-users", "hamim", "--reset", "--dir", str(directory)])
    assert json.loads((directory / "reviewers.json").read_text())["hamim"] != first["hamim"]
