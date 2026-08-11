from __future__ import annotations

import io
import json
import time
import zipfile
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


def _wait_for_submission(
    client: TestClient, submission_id: str, expected_status: str, timeout: float = 10.0
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/submissions/{submission_id}/status")
        assert response.status_code == 200
        if response.json()["status"] == expected_status:
            queue = client.get(
                "/api/reviewer/submissions", params={"status": expected_status}
            )
            assert queue.status_code == 200
            return next(
                item
                for item in queue.json()["items"]
                if item["submission_id"] == submission_id
            )
        time.sleep(0.01)
    raise AssertionError(f"submission {submission_id} did not reach {expected_status}")


def _html_bundle(*, unsafe_path: str | None = None, raw_image: bool = False) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            unsafe_path or "incident/content.html",
            "<html><head><title>Runtime collision</title></head><body><article>"
            "<h1>Runtime collision</h1><p>A bus and motorcycle collision was reported "
            "on Runtime Road. One person was reported injured.</p>"
            "<script>alert('unsafe')</script></article></body></html>",
        )
        archive.writestr(
            "incident/SOURCE_INFO.md",
            "Source name: Runtime News\nNews link: https://example.com/runtime-report\n",
        )
        archive.writestr(
            "incident/image_01.json",
            json.dumps(
                {
                    "observations": [
                        {
                            "observation": "A damaged motorcycle is visible.",
                            "confidence": "medium",
                        }
                    ]
                }
            ),
        )
        if raw_image:
            archive.writestr("incident/photo.png", b"\x89PNG\r\n\x1a\n")
    return output.getvalue()


def _submit_html(client: TestClient) -> str:
    response = client.post(
        "/api/submissions",
        data={"submission_type": "html_bundle", "submitter_name": "Public contributor"},
        files={"package": ("incident.zip", _html_bundle(), "application/zip")},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["submission_id"])


def _video_json() -> bytes:
    return json.dumps(
        {
            "source": {
                "platform_or_publisher": "Runtime Video",
                "primary_topic": "Bus crash on Runtime Road",
                "source_languages": ["en"],
            },
            "traffic_incidents": [
                {
                    "description": "A bus crash was reported on Runtime Road.",
                    "location": "Runtime Road",
                    "injuries": 1,
                    "confidence": "high",
                }
            ],
            "locations": [{"description": "Runtime Road", "confidence": "medium"}],
        }
    ).encode()


def _submit_video(client: TestClient) -> str:
    response = client.post(
        "/api/submissions",
        data={"submission_type": "video_json", "submitter_name": "Video contributor"},
        files={"package": ("video.json", _video_json(), "application/json")},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["submission_id"])


def test_submission_queue_and_file_content_require_reviewer_login(
    moderated_app: tuple[TestClient, Path],
) -> None:
    client, _ = moderated_app
    submission_id = _submit_html(client)
    assert client.get("/api/reviewer/submissions").status_code == 401
    assert client.get(f"/api/reviewer/submissions/{submission_id}/download").status_code == 401
    status = client.get(f"/api/submissions/{submission_id}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "pending"


def test_multiple_reviewers_can_inspect_and_load_html_bundle(
    moderated_app: tuple[TestClient, Path],
) -> None:
    public_client, data = moderated_app
    submission_id = _submit_html(public_client)

    alice = TestClient(public_client.app)
    _login(alice, "alice", "alice-test-password")
    queue = alice.get("/api/reviewer/submissions", params={"status": "pending"})
    assert queue.status_code == 200
    queued = queue.json()["items"][0]
    assert queued["submission_type"] == "html_bundle"
    assert queued["original_filename"] == "incident.zip"
    assert {item["path"] for item in queued["files"]} == {
        "content.html",
        "SOURCE_INFO.md",
        "image_01.json",
    }
    html_file = next(item for item in queued["files"] if item["kind"] == "html")
    preview = alice.get(
        f"/api/reviewer/submissions/{submission_id}/files/{html_file['file_id']}"
    )
    assert preview.status_code == 200
    assert "<script>alert('unsafe')</script>" in preview.text
    assert preview.headers["content-type"].startswith("text/plain")
    assert preview.headers["x-content-type-options"] == "nosniff"
    download = alice.get(f"/api/reviewer/submissions/{submission_id}/download")
    assert download.status_code == 200
    assert download.content.startswith(b"PK")
    assert alice.post(
        f"/api/reviewer/submissions/{submission_id}/review",
        json={"decision": "approve"},
    ).status_code == 403

    bob = TestClient(public_client.app)
    bob_csrf = _login(bob, "bob", "bob-test-password")
    approved = bob.post(
        f"/api/reviewer/submissions/{submission_id}/review",
        headers={"X-CSRF-Token": bob_csrf},
        json={"decision": "approve", "note": "All packaged files reviewed."},
    )
    assert approved.status_code == 202, approved.text
    assert approved.json()["status"] == "processing"
    record = _wait_for_submission(bob, submission_id, "approved")
    assert record["status"] == "approved"
    assert record["reviewed_by"] == "bob"
    assert len(record["loaded_source_ids"]) == 2
    assert {event["actor"] for event in record["audit"]} >= {"Public contributor", "bob"}

    runtime = data / "runtime_scraps" / "html" / submission_id
    assert (runtime / "content.html").exists()
    assert (runtime / "image_01.json").exists()
    extracted = (data / "sources" / record["loaded_source_ids"][0] / "content.md")
    html_source_outputs = list((data / "sources").glob("*/content.md"))
    assert extracted.exists() or html_source_outputs
    assert all("alert('unsafe')" not in path.read_text() for path in html_source_outputs)
    assert json.loads((data / "run.json").read_text())["provider"] == "recorded"


def test_video_json_is_loaded_under_runtime_youtube(
    moderated_app: tuple[TestClient, Path],
) -> None:
    client, data = moderated_app
    submission_id = _submit_video(client)
    csrf = _login(client, "alice", "alice-test-password")
    approved = client.post(
        f"/api/reviewer/submissions/{submission_id}/review",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "approve", "note": "JSON contract reviewed."},
    )
    assert approved.status_code == 202, approved.text
    assert approved.json()["status"] == "processing"
    record = _wait_for_submission(client, submission_id, "approved")
    assert record["loaded_source_ids"]
    runtime = data / "runtime_scraps" / "youtube" / f"{submission_id}.json"
    assert runtime.read_bytes() == _video_json()


def test_reviewer_can_reject_with_audited_reason(
    moderated_app: tuple[TestClient, Path],
) -> None:
    client, _ = moderated_app
    submission_id = _submit_video(client)
    csrf = _login(client, "alice", "alice-test-password")
    rejected = client.post(
        f"/api/reviewer/submissions/{submission_id}/review",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "reject", "note": "Insufficient source context."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["audit"][-1]["action"] == "rejected"


@pytest.mark.parametrize(
    ("submission_type", "filename", "payload", "expected"),
    [
        ("video_json", "video.json", b"not json", "not valid UTF-8 JSON"),
        ("html_bundle", "incident.zip", _html_bundle(unsafe_path="../content.html"), "unsafe path"),
        ("html_bundle", "incident.zip", _html_bundle(raw_image=True), "photo.png"),
    ],
)
def test_invalid_source_packages_are_rejected(
    moderated_app: tuple[TestClient, Path],
    submission_type: str,
    filename: str,
    payload: bytes,
    expected: str,
) -> None:
    client, _ = moderated_app
    response = client.post(
        "/api/submissions",
        data={"submission_type": submission_type},
        files={"package": (filename, payload, "application/octet-stream")},
    )
    assert response.status_code == 422
    assert expected in response.json()["detail"]


def test_upload_limit_is_enforced_before_quarantine(
    moderated_app: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, data = moderated_app
    monkeypatch.setattr("traffic_fusion.api.app.MAX_UPLOAD_BYTES", 100)
    response = client.post(
        "/api/submissions",
        data={"submission_type": "video_json"},
        files={"package": ("video.json", b"{" + b"x" * 100, "application/json")},
    )
    assert response.status_code == 413
    assert not (data / "moderation" / "uploads").exists()


def test_invalid_and_plaintext_reviewer_credentials_are_rejected(
    moderated_app: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = moderated_app
    response = client.post(
        "/api/reviewer/login", json={"username": "alice", "password": "wrong"}
    )
    assert response.status_code == 401
    monkeypatch.setenv("MGEOAI_REVIEWERS_JSON", json.dumps({"alice": "plaintext"}))
    response = client.post(
        "/api/reviewer/login", json={"username": "alice", "password": "plaintext"}
    )
    assert response.status_code == 503


def test_pipeline_failure_remains_retryable_without_publishing_upload(
    moderated_app: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, data = moderated_app
    submission_id = _submit_html(client)
    csrf = _login(client, "alice", "alice-test-password")

    def fail_pipeline(*args: object, **kwargs: object) -> object:
        raise RuntimeError("configured provider unavailable")

    monkeypatch.setattr("traffic_fusion.api.app.run_pipeline", fail_pipeline)
    response = client.post(
        f"/api/reviewer/submissions/{submission_id}/review",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "approve", "note": "Retry provider later."},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    record = _wait_for_submission(client, submission_id, "ingest_failed")
    assert "configured provider unavailable" in record["ingest_error"]
    assert not (data / "run.json").exists()
    assert not (data / "runtime_scraps" / "html" / submission_id).exists()
    assert (data / "moderation" / "uploads" / submission_id / "original.zip").exists()


def test_failed_pipeline_summary_is_not_published(
    moderated_app: tuple[TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, data = moderated_app
    submission_id = _submit_video(client)
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
    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    _wait_for_submission(client, submission_id, "ingest_failed")
    assert not (data / "run.json").exists()
    assert not (data / "runtime_scraps" / "youtube" / f"{submission_id}.json").exists()
