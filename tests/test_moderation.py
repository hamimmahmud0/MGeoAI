from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from traffic_fusion.api.app import create_app
from traffic_fusion.api.moderation import hash_reviewer_password
from traffic_fusion.config import Settings


@pytest.fixture()
def moderated_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, Path]:
    monkeypatch.setenv(
        "MGEOAI_REVIEWERS_JSON",
        json.dumps(
            {
                "alice": hash_reviewer_password("alice-test-password"),
                "bob": hash_reviewer_password("bob-test-password"),
            }
        ),
    )
    monkeypatch.setenv("MGEOAI_SESSION_SECRET", "test-session-secret-that-is-at-least-32-characters")
    base = tmp_path / "base_scraps" / "html" / "01"
    base.mkdir(parents=True)
    (base / "content.html").write_text(
        "<html><head><title>Base crash report</title></head><body><article>"
        "<h1>Base road crash</h1><p>A bus crash was reported on Test Road.</p>"
        "</article></body></html>",
        encoding="utf-8",
    )
    (base / "SOURCE_INFO.md").write_text("Source name: Base News\n", encoding="utf-8")
    data = tmp_path / "data"
    app = create_app(
        data,
        settings=Settings(provider="recorded"),
        base_scraps_dir=tmp_path / "base_scraps",
    )
    return TestClient(app), data


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/reviewer/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def _submit(client: TestClient, title: str = "Runtime collision report") -> str:
    response = client.post(
        "/api/submissions",
        json={
            "source_kind": "news",
            "title": title,
            "publisher": "Runtime News",
            "source_uri": "https://example.com/runtime-report",
            "submitter_name": "Public contributor",
            "content": (
                "A bus and motorcycle collision was reported on Runtime Road.\n"
                "One person was reported injured. <script>alert('unsafe')</script>"
            ),
        },
    )
    assert response.status_code == 201
    return str(response.json()["submission_id"])


def test_submission_queue_requires_reviewer_login(moderated_app: tuple[TestClient, Path]) -> None:
    client, _ = moderated_app
    submission_id = _submit(client)
    assert client.get("/api/reviewer/submissions").status_code == 401
    status = client.get(f"/api/submissions/{submission_id}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "pending"


def test_multiple_reviewers_can_review_and_approved_text_is_loaded(
    moderated_app: tuple[TestClient, Path],
) -> None:
    public_client, data = moderated_app
    submission_id = _submit(public_client)

    alice = TestClient(public_client.app)
    _login(alice, "alice", "alice-test-password")
    queue = alice.get("/api/reviewer/submissions", params={"status": "pending"})
    assert queue.status_code == 200
    assert queue.json()["items"][0]["content"].startswith("A bus and motorcycle")
    assert alice.post(
        f"/api/reviewer/submissions/{submission_id}/review",
        json={"decision": "approve"},
    ).status_code == 403

    bob = TestClient(public_client.app)
    bob_csrf = _login(bob, "bob", "bob-test-password")
    approved = bob.post(
        f"/api/reviewer/submissions/{submission_id}/review",
        headers={"X-CSRF-Token": bob_csrf},
        json={"decision": "approve", "note": "Source text and link reviewed."},
    )
    assert approved.status_code == 200
    record = approved.json()
    assert record["status"] == "approved"
    assert record["reviewed_by"] == "bob"
    assert record["loaded_source_ids"]
    assert {event["actor"] for event in record["audit"]} >= {
        "Public contributor",
        "bob",
    }

    safe_html = data / "runtime_scraps" / "html" / submission_id / "content.html"
    assert safe_html.exists()
    assert "<script>" not in safe_html.read_text(encoding="utf-8")
    assert "&lt;script&gt;" in safe_html.read_text(encoding="utf-8")
    assert json.loads((data / "run.json").read_text())["provider"] == "recorded"
    assert bob.post(
        f"/api/reviewer/submissions/{submission_id}/review",
        headers={"X-CSRF-Token": bob_csrf},
        json={"decision": "approve"},
    ).status_code == 409


def test_reviewer_can_reject_with_audited_reason(
    moderated_app: tuple[TestClient, Path],
) -> None:
    client, _ = moderated_app
    submission_id = _submit(client, "Unverifiable runtime report")
    csrf = _login(client, "alice", "alice-test-password")
    rejected = client.post(
        f"/api/reviewer/submissions/{submission_id}/review",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "reject", "note": "Missing enough source context."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["reviewed_by"] == "alice"
    assert rejected.json()["audit"][-1]["action"] == "rejected"


def test_invalid_reviewer_credentials_are_rejected(
    moderated_app: tuple[TestClient, Path],
) -> None:
    client, _ = moderated_app
    response = client.post(
        "/api/reviewer/login", json={"username": "alice", "password": "wrong"}
    )
    assert response.status_code == 401


def test_plaintext_reviewer_configuration_is_rejected(
    moderated_app: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = moderated_app
    monkeypatch.setenv("MGEOAI_REVIEWERS_JSON", json.dumps({"alice": "plaintext"}))
    response = client.post(
        "/api/reviewer/login", json={"username": "alice", "password": "plaintext"}
    )
    assert response.status_code == 503


def test_pipeline_failure_remains_retryable_without_provider_fallback(
    moderated_app: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, data = moderated_app
    submission_id = _submit(client, "Provider failure report")
    csrf = _login(client, "alice", "alice-test-password")

    def fail_pipeline(*args: object, **kwargs: object) -> object:
        raise RuntimeError("configured provider unavailable")

    monkeypatch.setattr("traffic_fusion.api.app.run_pipeline", fail_pipeline)
    response = client.post(
        f"/api/reviewer/submissions/{submission_id}/review",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "approve", "note": "Reviewed; retry provider later."},
    )
    assert response.status_code == 502

    queue = client.get("/api/reviewer/submissions", params={"status": "ingest_failed"})
    assert queue.status_code == 200
    record = queue.json()["items"][0]
    assert record["submission_id"] == submission_id
    assert record["status"] == "ingest_failed"
    assert "configured provider unavailable" in record["ingest_error"]
    assert record["audit"][-1]["action"] == "ingest_failed"
    assert not (data / "run.json").exists()
    assert not (data / "runtime_scraps" / "html" / submission_id).exists()


def test_failed_pipeline_summary_is_not_published(
    moderated_app: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, data = moderated_app
    submission_id = _submit(client, "Failed fusion summary")
    csrf = _login(client, "bob", "bob-test-password")
    monkeypatch.setattr(
        "traffic_fusion.api.app.run_pipeline",
        lambda *args, **kwargs: SimpleNamespace(status="failed", run_id="run_failed"),
    )

    response = client.post(
        f"/api/reviewer/submissions/{submission_id}/review",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "approve"},
    )
    assert response.status_code == 502
    assert not (data / "run.json").exists()
    assert not (data / "runtime_scraps" / "html" / submission_id).exists()
