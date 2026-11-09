from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from traffic_fusion.api.app import create_app
from traffic_fusion.extraction.accounts import AccountStore
from traffic_fusion.extraction.prepare import html_to_markdown, image_candidates
from traffic_fusion.extraction.schema import AccidentRecord, lonlat_from_string

PW = "correct-horse-battery"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Path]:
    from traffic_fusion.api import x_auth

    x_auth._FAILS.clear()  # the sign-in lockout counter is process-wide
    root = tmp_path / "extraction"
    monkeypatch.setenv("MGEOAI_EXTRACTION_DIR", str(root))
    monkeypatch.setenv("MGEOAI_SESSION_SECRET", "s" * 40)
    store = AccountStore(root)
    store.upsert("boss", ["admin", "reviewer"], PW)
    store.upsert("ann_one", ["annotator"], PW)
    art = root / "articles" / "abc123"
    art.mkdir(parents=True)
    (art / "article.md").write_text("Six killed near Kabirhat.\n")
    (art / "meta.json").write_text(
        json.dumps(
            {
                "id": "abc123",
                "url": "https://x.test/a",
                "publisher": "P",
                "title": "T",
                "published_at": "2025-11-04",
                "language": "en",
                "images": [{"url": "https://x.test/i.jpg", "source": "og:image", "alt": ""}],
                "admin": {"group_id": "g001", "agent_claim": "SECRET-CLAIM"},
            }
        )
    )
    return TestClient(create_app()), root


def login(client: TestClient, user: str) -> str:
    response = client.post("/api/x/login", json={"username": user, "password": PW})
    assert response.status_code == 200, response.text
    return str(response.json()["csrf_token"])


def test_schema_wire_keys_and_coordinate_order() -> None:
    record = AccidentRecord.model_validate(
        {"accident": True, "fatalities": 6, "longitude and latitude": "23.8103,90.4125"}
    )
    assert list(record.wire())[-2:] == ["longitude and latitude", "evidences"]
    assert lonlat_from_string("23.8103,90.4125") == (90.4125, 23.8103)  # GeoJSON [lon, lat]
    assert lonlat_from_string("123,90") is None
    with pytest.raises(ValueError):
        AccidentRecord.model_validate({"accident": True, "date": "last night"})
    with pytest.raises(ValueError):
        AccidentRecord.model_validate({"accident": True, "vehicles": ["spaceship"]})


def test_markdown_drops_scripts_and_chrome() -> None:
    html = (
        b"<html><head><script>evil()</script><meta property='og:image' content='/o.jpg'></head>"
        b"<body><nav>MENU</nav><article><h1>Crash</h1><p>Six died.</p>"
        b"<img src='/a.jpg' alt='bus'></article><footer>FOOT</footer></body></html>"
    )
    markdown = html_to_markdown(html)
    assert "Six died." in markdown and "MENU" not in markdown and "evil" not in markdown
    urls = [item["url"] for item in image_candidates(html, "https://x.test/p")]
    assert urls == ["https://x.test/o.jpg", "https://x.test/a.jpg"]


def test_annotation_is_blind_and_role_gated(env: tuple[TestClient, Path]) -> None:
    client, root = env
    assert client.get("/api/x/articles").status_code == 401
    login(client, "boss")
    assert client.get("/api/x/articles").status_code == 403  # admin is not an annotator
    client.post("/api/x/logout", headers={"X-CSRF-Token": "x"})
    client.cookies.clear()
    csrf = login(client, "ann_one")
    detail = client.get("/api/x/articles/abc123")
    assert detail.status_code == 200
    assert "SECRET-CLAIM" not in detail.text and "g001" not in detail.text
    assert client.get("/api/x/admin/accounts").status_code == 403
    body = {"accidents": [{"accident": True, "fatalities": 6}], "images": []}
    assert client.put("/api/x/labels/abc123", json=body).status_code == 403  # no CSRF
    ok = client.put("/api/x/labels/abc123", json=body, headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200 and ok.json()["revision"] == 1
    again = client.put("/api/x/labels/abc123", json=body, headers={"X-CSRF-Token": csrf})
    assert again.json()["revision"] == 2
    assert client.get("/api/x/articles").json()["labeled"] == 1
    assert (root / "labels" / "ann_one.jsonl").read_text().count("\n") == 2


def test_admin_keys_are_write_only_and_in_memory(env: tuple[TestClient, Path]) -> None:
    client, root = env
    csrf = login(client, "boss")
    secret = "sk-test-very-secret-123"
    response = client.put(
        "/api/x/admin/keys/openai", json={"key": secret}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200 and secret not in response.text
    assert client.get("/api/x/admin/control").json()["keys"]["openai"]["configured"] is True
    assert secret not in client.get("/api/x/admin/control").text
    for path in root.rglob("*"):
        if path.is_file():
            assert secret not in path.read_text(errors="ignore")
    created = client.put(
        "/api/x/admin/accounts/new_user",
        json={"roles": ["annotator"], "password": PW},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 200 and "password" not in created.text
    last = client.put(
        "/api/x/admin/accounts/boss",
        json={"roles": ["reviewer"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert last.status_code == 422  # cannot remove the last admin


def test_login_lockout(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    for _ in range(5):
        assert client.post("/api/x/login", json={"username": "ann_one", "password": "x"}).status_code == 401
    assert client.post("/api/x/login", json={"username": "ann_one", "password": PW}).status_code == 429


# --- provider + run tests (offline: httpx.post is mocked) -----------------------------
import time  # noqa: E402

import httpx  # noqa: E402

from traffic_fusion.extraction import providers  # noqa: E402
from traffic_fusion.extraction.control import ControlStore  # noqa: E402
from traffic_fusion.extraction.runs import RunManager, RunSpec, check_quotes, parse_output  # noqa: E402

GOOD = json.dumps({"accidents": [{"accident": True, "casualities": 6, "fatalities": 6,
    "vehicles": ["truck"], "date": "2025-11-04", "country": "Bangladesh",
    "location": "Kabirhat, Noakhali", "longitude and latitude": None,
    "evidences": [{"field": "fatalities", "quote": "Six killed"}, {"field": "date", "quote": "made up"}]}],
    "images": []})


def _reply(status: int = 200, content: str = GOOD, usage: tuple[int, int] = (1000, 200)) -> httpx.Response:
    body = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "model": "m", "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}}
    if status != 200:
        body = {"error": {"message": "boom"}}
    return httpx.Response(status, json=body, headers={"Retry-After": "0"},
                          request=httpx.Request("POST", "https://x"))


def _setup(tmp_path: Path, n: int = 3) -> tuple[RunManager, ControlStore]:
    root = tmp_path / "x"
    for i in range(n):
        art = root / "articles" / f"a{i}"
        art.mkdir(parents=True)
        (art / "article.md").write_text("Six killed near Kabirhat.")
        (art / "model_raw.html").write_text("<p>Six killed near Kabirhat.</p>")
        (art / "meta.json").write_text(json.dumps({"id": f"a{i}", "images": []}))
    control = ControlStore(root)
    control.set_key("deepseek", "k-test")
    control.set_key("openrouter", "k-test")
    return RunManager(root, control), control


def _wait(manager: RunManager, config_id: str) -> dict[str, object]:
    for _ in range(100):
        state = manager.status(config_id)
        if state and state["status"] != "running":
            return state
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_parse_and_quote_check() -> None:
    accidents, images = parse_output("```json\n" + GOOD + "\n```")
    assert accidents[0].fatalities == 6 and images == []
    assert parse_output(json.dumps([{"accident": False}]))[0][0].accident is False
    assert check_quotes(accidents, "Six  killed near x") == {"quotes": 2, "verbatim": 1}


def test_run_without_prices_records_tokens_not_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: _reply())
    manager, control = _setup(tmp_path)
    spec = RunSpec(provider="deepseek", model="deepseek-flash", input_set="markdown")
    assert control.price("deepseek", "deepseek-flash") is None
    manager.start(spec)
    state = _wait(manager, spec.config_id())
    assert state["done"] == 3 and state["failed"] == 0
    assert state["input_tokens"] == 3000 and state["cost_usd"] is None and not state["cost_known"]
    result = json.loads((manager.runs_dir / spec.config_id() / "a0.json").read_text())
    assert result["quality"] == {"quotes": 2, "verbatim": 1}
    assert "k-test" not in json.dumps(result)


def test_openrouter_free_model_costs_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: _reply())
    manager, control = _setup(tmp_path, 1)
    assert control.price("openrouter", "meta-llama/x:free").input_per_million_usd == 0  # type: ignore[union-attr]
    settings = control.settings()
    from traffic_fusion.extraction.control import ModelPrice

    settings.pricing["deepseek/deepseek-flash"] = ModelPrice(
        input_per_million_usd=1, output_per_million_usd=2)
    control.save(settings)
    spec = RunSpec(provider="deepseek", model="deepseek-flash", input_set="raw")
    manager.start(spec)
    state = _wait(manager, spec.config_id())
    assert state["cost_usd"] == round((1000 * 1 + 200 * 2) / 1e6, 6)


def test_failure_stays_failed_and_never_switches_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        calls.append(url)
        return _reply(429)

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    manager, _ = _setup(tmp_path, 1)
    spec = RunSpec(provider="openrouter", model="m:free", input_set="markdown")
    manager.start(spec)
    state = _wait(manager, spec.config_id())
    assert state["failed"] == 1 and state["done"] == 0
    assert len(calls) == 3 and all("openrouter.ai" in url for url in calls)  # 1 try + 2 retries
    saved = json.loads((manager.runs_dir / spec.config_id() / "a0.json").read_text())
    assert saved["status"] == "failed" and saved["retryable"] is True


def test_token_limit_stops_run_and_resume_skips_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: _reply(usage=(900, 200)))
    manager, control = _setup(tmp_path, 4)
    settings = control.settings()
    settings.run_token_limit = 2000
    settings.concurrency = 1
    control.save(settings)
    spec = RunSpec(provider="deepseek", model="deepseek-flash", input_set="markdown")
    manager.start(spec)
    state = _wait(manager, spec.config_id())
    assert state["status"] == "stopped" and state["stop_reason"] == "token_limit"
    assert state["done"] == 2
    estimate = manager.estimate(spec)
    assert estimate["articles_todo"] == 2 and estimate["cost_known"] is False


def test_unimplemented_provider_and_missing_key(tmp_path: Path) -> None:
    manager, control = _setup(tmp_path, 1)
    with pytest.raises(ValueError, match="not implemented"):
        manager.start(RunSpec(provider="anthropic", model="x", input_set="raw"))
    control.set_key("deepseek", None)
    with pytest.raises(ValueError, match="no API key"):
        manager.start(RunSpec(provider="deepseek", model="x", input_set="raw"))


def test_image_filters_and_refresh(tmp_path: Path) -> None:
    import io

    from PIL import Image

    from traffic_fusion.extraction.images import good_image, refresh_candidates

    def png(size: tuple[int, int]) -> bytes:
        buffer = io.BytesIO()
        Image.effect_noise(size, 80).convert("RGB").save(buffer, "PNG")
        return buffer.getvalue()

    assert good_image(png((400, 300))) and not good_image(png((40, 40))) and not good_image(b"<html>")
    html = (
        b"<html><head><meta property='og:image' content='https://x.test/hero.jpg'></head><body><article>"
        b"<img src='/img/logo.png'><img src='data:image/gif;base64,AAAA' data-src='/p/photo.jpg'>"
        b"<img srcset='/s/a-320.jpg 320w, /s/a-1200.jpg 1200w' src='/s/a-320.jpg'>"
        b"<img src='page_files/x.jpg'><img src='/i/icon.svg'></article></body></html>"
    )
    folder = tmp_path / "articles" / "a1"
    (folder / "images").mkdir(parents=True)
    (folder / "raw.html").write_bytes(html)
    (folder / "images" / "1.png").write_bytes(png((30, 30)))  # saved earlier, now too small
    (folder / "meta.json").write_text(json.dumps({"url": "https://x.test/a", "images": [
        {"url": "https://x.test/hero.jpg", "source": "og:image", "alt": "", "file": "1.png",
         "content_type": "image/png", "bytes": 9000}]}))
    counts = refresh_candidates(tmp_path)
    meta = json.loads((folder / "meta.json").read_text())
    urls = [item["url"] for item in meta["images"]]
    assert urls == ["https://x.test/hero.jpg", "https://x.test/p/photo.jpg", "https://x.test/s/a-1200.jpg"]
    assert counts["removed"] == 1 and meta["images"][0]["status"] == "too_small"
    assert not (folder / "images" / "1.png").exists()


def test_retry_failed_only_and_estimate_counts_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies = iter([_reply(), _reply(401), _reply()])
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: next(replies))
    manager, control = _setup(tmp_path, 3)
    settings = control.settings()
    settings.concurrency = 1
    control.save(settings)
    spec = RunSpec(provider="deepseek", model="deepseek-flash", input_set="markdown")
    manager.start(spec)
    state = _wait(manager, spec.config_id())
    assert (state["done"], state["failed"]) == (2, 1)
    assert manager.estimate(spec)["articles_todo"] == 1  # the failed one is still to do
    retry = spec.model_copy(update={"only_failed": True})
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: _reply())
    manager.start(retry)
    state = _wait(manager, spec.config_id())
    assert state["attempt"]["done"] == 1  # only the failed article was re-run
    assert state["done"] == 3 and state["failed"] == 0  # cumulative totals
    assert manager.estimate(retry)["articles_todo"] == 0


# --- open dashboard: lock + scoring -------------------------------------------------------
def _seed_scored(root: Path) -> None:
    """3 annotators label a1 (accident, 6 dead); a model run got it right; a2 unlabelled."""
    from traffic_fusion.extraction.annotation_store import ArticleStore
    from traffic_fusion.extraction.schema import AccidentRecord

    store = ArticleStore(root)
    for name in ("ann_a", "ann_b", "ann_c"):
        deaths = 7 if name == "ann_c" else 6  # one dissent: majority still 6
        store.append(name, "abc123", [AccidentRecord.model_validate({
            "accident": True, "fatalities": deaths, "casualities": deaths, "vehicles": ["truck"],
            "date": "2025-11-04", "country": "Bangladesh", "location": "Kabirhat, Noakhali",
            "longitude and latitude": "22.88,91.1"})], [], False, "")
    run = root / "runs" / "deepseek__deepseek-flash__markdown__txt"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({
        "config_id": run.name, "spec": {"provider": "deepseek", "model": "deepseek-flash",
        "input_set": "markdown", "with_images": False}, "status": "finished",
        "started_at": "x", "finished_at": "y", "done": 1, "failed": 0, "input_tokens": 10,
        "output_tokens": 5, "cost_usd": None, "cost_known": False, "stop_reason": None}))
    (run / "abc123.json").write_text(json.dumps({
        "article_id": "abc123", "status": "ok", "input_tokens": 10, "output_tokens": 5,
        "latency_ms": 100, "quality": {"quotes": 2, "verbatim": 2},
        "raw_text": "SECRET-RAW", "accidents": [{
            "accident": True, "fatalities": 6, "casualities": 6, "vehicles": ["truck"],
            "date": "2025-11-04T14:15:00+06:00", "country": "bangladesh",
            "location": "Kabirhat, Noakhali", "longitude and latitude": "22.88,91.1", "evidences": []}]}))


PRIVATE = ("fatalities", "SECRET-RAW", "SECRET-CLAIM", "g001", "ann_a", "initial_passwords")


def test_open_dashboard_is_locked_while_labelling_is_open(env: tuple[TestClient, Path]) -> None:
    client, root = env
    _seed_scored(root)
    for path in ("/api/x/public/sources", "/api/x/public/incidents.geojson",
                 "/api/x/public/scores/annotation", "/api/x/public/scores/models"):
        body = client.get(path)  # no login at all
        assert body.status_code == 200 and body.json()["locked"] is True, path
        assert not any(word in body.text for word in PRIVATE), path
    overview = client.get("/api/x/public/overview").json()
    assert overview["articles"] == 1 and overview["labelling_open"] is True
    assert overview["labelling"]["articles_with_3plus_labels"] == 1  # counts only
    assert not any(word in json.dumps(overview) for word in PRIVATE)
    assert "abc123" not in client.get("/api/x/public/coverage.geojson").text
    # article text, images and admin data stay behind login even when unlocked
    assert client.get("/api/x/articles/abc123").status_code == 401
    assert client.get("/api/x/articles/abc123/images/1").status_code == 401


def test_unlocked_dashboard_shows_scores_and_map(env: tuple[TestClient, Path]) -> None:
    client, root = env
    _seed_scored(root)
    csrf = login(client, "boss")
    settings = client.get("/api/x/admin/control").json()["settings"]
    settings["labelling_open"] = False
    assert client.put("/api/x/admin/control", json=settings, headers={"X-CSRF-Token": csrf}).status_code == 200
    client.cookies.clear()  # anonymous visitor from here on
    scores = client.get("/api/x/public/scores/annotation").json()
    assert scores["locked"] is False and scores["articles_with_3plus_labels"] == 1
    assert "gold_articles" not in scores and "min_labels_for_gold" not in scores  # one annotation per article is enough
    models = client.get("/api/x/public/scores/models").json()["models"][0]["metrics"]
    assert models["accident_flag"]["tp"] == 1 and models["scored_articles"] == 1
    assert models["fields_exact"]["fatalities"]["value"] == 1.0  # reference = ann_a (ties by name): 6 dead
    assert models["fields_exact"]["date"]["value"] == 1.0  # day-level match
    assert models["evidence_quotes_verbatim"]["rate"] == 1.0
    sources = client.get("/api/x/public/sources").json()["sources"]
    assert sources == ["deepseek__deepseek-flash__markdown__txt"]  # no "gold" source any more
    for source in sources:
        geo = client.get("/api/x/public/incidents.geojson", params={"source": source}).json()
        feature = geo["features"][0]
        assert feature["geometry"]["coordinates"] == [91.1, 22.88]  # [lon, lat]
        assert geo["meta"]["verified"] is False
        assert "SECRET-RAW" not in json.dumps(geo)
    assert client.get("/api/x/public/incidents.geojson", params={"source": "nope"}).status_code == 404


def test_coverage_map_includes_countries_missing_from_profiles(env: tuple[TestClient, Path]) -> None:
    client, root = env
    meta_path = root / "articles" / "abc123" / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["admin"]["country"] = "Guatemala"
    meta_path.write_text(json.dumps(meta))
    feature = client.get("/api/x/public/coverage.geojson").json()["features"][0]
    assert feature["properties"]["country"] == "Guatemala" and feature["properties"]["articles"] == 1
    assert feature["properties"]["is_incident_location"] is False
    assert feature["properties"]["items"][0]["id"] == "abc123"
    assert feature["geometry"]["coordinates"] == [-90.23, 15.78]  # [lon, lat]


def test_admin_password_change_works_and_ends_old_sessions(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    admin_csrf = login(client, "boss")
    other = TestClient(client.app)
    login(other, "ann_one")
    assert other.get("/api/x/me").status_code == 200
    short = client.put("/api/x/admin/accounts/ann_one", json={"roles": ["annotator"], "password": "short"},
                       headers={"X-CSRF-Token": admin_csrf})
    assert short.status_code == 422
    time.sleep(1.1)  # session issue time has one-second resolution
    changed = client.put("/api/x/admin/accounts/ann_one",
                         json={"roles": ["annotator"], "password": "a-brand-new-password"},
                         headers={"X-CSRF-Token": admin_csrf})
    assert changed.status_code == 200 and "password" not in changed.text and "hash" not in changed.text
    assert other.get("/api/x/me").status_code == 401  # old session rejected
    assert TestClient(client.app).post("/api/x/login", json={"username": "ann_one", "password": PW}).status_code == 401
    fresh = TestClient(client.app)
    assert fresh.post("/api/x/login", json={"username": "ann_one", "password": "a-brand-new-password"}).status_code == 200
    assert client.get("/api/x/me").status_code == 200  # the admin's own session is unaffected


def test_orphaned_running_run_is_interrupted_and_clear_archives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: _reply())
    manager, control = _setup(tmp_path, 2)
    spec = RunSpec(provider="deepseek", model="deepseek-flash", input_set="markdown")
    manager.start(spec)
    _wait(manager, spec.config_id())
    # simulate a service restart in the middle of a run: state says running, no live thread
    path = manager.runs_dir / spec.config_id() / "run.json"
    state = json.loads(path.read_text())
    state["status"] = "running"
    path.write_text(json.dumps(state))
    restarted = RunManager(manager.root, control)
    assert restarted.status(spec.config_id())["status"] == "interrupted"  # type: ignore[index]
    target = restarted.archive(spec.config_id())
    assert restarted.list() == [] and (target / "a0.json").exists()  # moved, not deleted
    with pytest.raises(ValueError, match="not found"):
        restarted.archive(spec.config_id())
    with pytest.raises(ValueError, match="invalid"):
        restarted.archive("../x")


def test_deepseek_thinking_switch_and_truncation_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bodies: list[dict[str, object]] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        bodies.append(kwargs["json"])  # type: ignore[arg-type]
        return _reply()

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    providers.call_chat("deepseek", api_key="k", model="m", system="s", user_parts=[],
                        thinking="disabled")
    providers.call_chat("deepseek", api_key="k", model="m", system="s", user_parts=[])
    providers.call_chat("openrouter", api_key="k", model="m", system="s", user_parts=[],
                        thinking="disabled")
    assert bodies[0]["thinking"] == {"type": "disabled"}
    assert "thinking" not in bodies[1] and "thinking" not in bodies[2]  # default = model's own mode
    # an empty truncated answer explains itself
    manager, control = _setup(tmp_path, 1)
    deepseek = control.settings().providers["deepseek"]
    assert deepseek.thinking == "default" and deepseek.max_output_tokens == 393216  # on, documented max
    assert control.settings().providers["openrouter"].max_output_tokens == 4000
    settings = control.settings()
    settings.providers["deepseek"].max_output_tokens = 4000
    settings.providers["deepseek"].thinking = "disabled"
    control.save(settings)  # pin the old behaviour for the truncation scenario below
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: httpx.Response(
        200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}],
                   "usage": {"prompt_tokens": 5, "completion_tokens": 4000}},
        request=httpx.Request("POST", "https://x")))
    spec = RunSpec(provider="deepseek", model="deepseek-flash", input_set="markdown")
    manager.start(spec)
    _wait(manager, spec.config_id())
    saved = json.loads((manager.runs_dir / spec.config_id() / "a0.json").read_text())
    assert saved["status"] == "failed" and "hidden reasoning" in saved["error"]


def test_concurrency_limit_is_fifty(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    csrf = login(client, "boss")
    settings = client.get("/api/x/admin/control").json()["settings"]
    for value, expected in ((50, 200), (51, 422), (0, 422)):
        settings["concurrency"] = value
        response = client.put("/api/x/admin/control", json=settings, headers={"X-CSRF-Token": csrf})
        assert response.status_code == expected, value
    assert client.get("/api/x/admin/control").json()["settings"]["concurrency"] == 50


def test_article_pages_open_text_but_lock_annotations_and_models(env: tuple[TestClient, Path]) -> None:
    client, root = env
    _seed_scored(root)
    listing = client.get("/api/x/public/articles").json()
    assert listing["locked"] is True and listing["articles"][0]["id"] == "abc123"
    assert "models_with_result" not in listing["articles"][0]
    detail = client.get("/api/x/public/articles/abc123").json()
    assert detail["locked"] is True and detail["url"] == "https://x.test/a"
    assert "Six killed near Kabirhat" in detail["markdown"]
    assert "annotators" not in detail and "models" not in detail and "gold" not in json.dumps(detail).lower()
    assert not any(word in json.dumps(detail) for word in ("SECRET-RAW", "ann_a", "SECRET-CLAIM", "g001"))
    assert client.get("/api/x/public/articles/nope").status_code == 404

    csrf = login(client, "boss")
    settings = client.get("/api/x/admin/control").json()["settings"]
    settings["labelling_open"] = False
    client.put("/api/x/admin/control", json=settings, headers={"X-CSRF-Token": csrf})
    client.cookies.clear()
    listing = client.get("/api/x/public/articles").json()
    assert listing["locked"] is False and listing["articles"][0]["annotations"] == 3 and "gold_accident" not in listing["articles"][0]
    assert listing["articles"][0]["models_with_result"] == 1
    detail = client.get("/api/x/public/articles/abc123").json()
    assert [a["annotator"] for a in detail["annotators"]] == ["Annotator A", "Annotator B", "Annotator C"]
    assert "gold" not in detail
    assert detail["models"][0]["raw_text"] == "SECRET-RAW" and detail["models"][0]["spec"]["provider"] == "deepseek"
    flat = json.dumps(detail)
    assert not any(word in flat for word in ("ann_a", "ann_b", "ann_c", "SECRET-CLAIM", "g001", "agent_claim"))


def test_output_token_cap_accepts_large_model_maximums(env: tuple[TestClient, Path]) -> None:
    client, _ = env
    csrf = login(client, "boss")
    settings = client.get("/api/x/admin/control").json()["settings"]
    for value, expected in ((524288, 200), (1048576, 200), (1048577, 422)):
        settings["providers"]["openrouter"]["max_output_tokens"] = value
        response = client.put("/api/x/admin/control", json=settings, headers={"X-CSRF-Token": csrf})
        assert response.status_code == expected, value


# --- bucket backup (offline: tests/fake_hf.py mirrors the bucket into a directory) -------------
def test_backup_mirrors_keeps_history_and_never_copies_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from traffic_fusion.extraction.backup import run_backup

    root = tmp_path / "extraction"
    art = root / "articles" / "a1"
    (art / "images").mkdir(parents=True)
    (art / "meta.json").write_text(json.dumps({"id": "a1", "publisher": "P", "title": "T",
                                               "url": "https://x.test", "images": [{"file": "1.jpg"}]}))
    (art / "article.md").write_text("text")
    (art / "images" / "1.jpg").write_bytes(b"jpg")
    (root / "labels").mkdir()
    label = {"article_id": "a1", "annotator": "u"}
    (root / "labels" / "oishik.jsonl").write_text(json.dumps(label) + "\n")
    (root / "runs" / "cfg").mkdir(parents=True)
    (root / "runs" / "cfg" / "a1.json").write_text('{"status":"ok"}')
    (root / "accounts.json").write_text('{"secret":"hash"}')
    (root / "initial_passwords.txt").write_text("admin\tpw")
    bucket = tmp_path / "bucket"
    monkeypatch.setenv("FAKE_BUCKET_DIR", str(bucket))
    fake = str(Path(__file__).parent / "fake_hf.py")
    state = tmp_path / "state"

    def backup(minute: int) -> dict[str, object]:
        from datetime import UTC, datetime
        return run_backup(root, "u/b", state, fake, now=datetime(2026, 11, 8, 12, minute, tzinfo=UTC))

    first = backup(0)
    assert first["history_entry"] == "history/20261108T120000Z"
    assert (bucket / "latest" / "labels" / "oishik.jsonl").exists()
    assert (bucket / "latest" / "articles" / "a1" / "images" / "1.jpg").read_bytes() == b"jpg"
    assert (bucket / "latest" / "sources.csv").read_text().count("a1") == 1
    assert (bucket / "history" / "20261108T120000Z" / "CHANGES.json").exists()
    assert (bucket / "manifest" / "status.json").exists()
    leaked = [p.name for p in bucket.rglob("*") if p.is_file() and p.name in ("accounts.json", "initial_passwords.txt")]
    assert leaked == []

    quiet = backup(10)  # nothing changed: no new history entry
    assert quiet["history_entry"] is None and quiet["changed"] == {"added": 0, "modified": 0, "removed": 0}

    with (root / "labels" / "oishik.jsonl").open("a") as handle:
        handle.write(json.dumps({"article_id": "a2", "annotator": "u"}) + "\n")
    changed = backup(20)  # a new label: history entry with before/after counts
    assert changed["history_entry"] == "history/20261108T122000Z"
    changes = json.loads((bucket / "history" / "20261108T122000Z" / "CHANGES.json").read_text())
    assert changes["label_stats"]["oishik"]["label_lines"] == 2
    assert changes["label_stats_before"]["oishik"]["label_lines"] == 1
    assert changes["changed_live_files"] == ["labels/oishik.jsonl"]
    old = (bucket / "history" / "20261108T120000Z" / "labels" / "oishik.jsonl").read_text()
    assert old.count("\n") == 1  # the earlier snapshot is preserved

    (root / "labels" / "oishik.jsonl").write_text("")  # a label file that lost its content
    (root / "labels" / "oishik.jsonl").write_text(json.dumps(label) + "\n")
    shrunk = backup(30)
    warned = json.loads((bucket / str(shrunk["history_entry"]) / "CHANGES.json").read_text())
    assert warned["warnings"] == ["label file shrank for oishik"]

    empty = tmp_path / "empty"
    (empty / "articles").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="empty tree"):
        run_backup(empty, "u/b", tmp_path / "s2", fake)


def test_publication_date_is_sent_only_with_meta_and_has_its_own_run_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        body = kwargs["json"]
        sent.append(body["messages"][1]["content"][0]["text"])  # type: ignore[index]
        return _reply()

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    manager, control = _setup(tmp_path, 2)
    meta_path = manager.root / "articles" / "a0" / "meta.json"
    meta_path.write_text(json.dumps({"id": "a0", "images": [], "published_at": "2025-09-06"}))
    plain = RunSpec(provider="deepseek", model="deepseek-flash", input_set="markdown")
    meta = plain.model_copy(update={"with_meta": True})
    assert plain.config_id() != meta.config_id() and meta.config_id().endswith("__meta")
    manager.start(plain)
    _wait(manager, plain.config_id())
    assert not any("PAGE_METADATA" in text for text in sent)
    sent.clear()
    manager.start(meta)
    _wait(manager, meta.config_id())
    with_date = [t for t in sent if "published: 2025-09-06" in t]
    assert len(with_date) == 1 and with_date[0].index("PAGE_METADATA") < with_date[0].index("<ARTICLE_SOURCE>")
    assert "not the accident date" in with_date[0]
    assert sum("PAGE_METADATA" in t for t in sent) == 1  # a1 has no date: no block at all
    assert sorted(p.name for p in manager.runs_dir.iterdir()) == sorted([plain.config_id(), meta.config_id()])
    # a CLI-started run (another process) is not shown as interrupted while its pid lives
    path = manager.runs_dir / meta.config_id() / "run.json"
    state = json.loads(path.read_text())
    state.update(status="running", pid=os.getppid())
    path.write_text(json.dumps(state))
    assert RunManager(manager.root, control).status(meta.config_id())["status"] == "running"  # type: ignore[index]
    state["pid"] = 2**22 + 12345
    path.write_text(json.dumps(state))
    assert RunManager(manager.root, control).status(meta.config_id())["status"] == "interrupted"  # type: ignore[index]


def test_extra_keys_from_the_model_are_dropped_and_reported_but_bad_values_still_fail() -> None:
    ignored: list[dict[str, object]] = []
    text = json.dumps({"accidents": [{"accident": True, "fatalities": 2, "date": None,
                                      "date_note": "only 'on Friday'", "evidences": []}], "images": []})
    accidents, _ = parse_output(text, ignored)
    assert accidents[0].fatalities == 2 and ignored == [{"date_note": "only 'on Friday'"}]
    bad = json.dumps({"accidents": [{"accident": True, "vehicles": ["battery_autorrickshaw"]}]})
    with pytest.raises(ValueError):
        parse_output(bad)


def test_custom_openai_compatible_provider_url_extra_body_and_image_shrinking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    from PIL import Image

    sent: list[tuple[str, dict[str, object]]] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        sent.append((url, kwargs["json"]))  # type: ignore[arg-type]
        return _reply(content="<think>maybe</think>" + GOOD)

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    with pytest.raises(providers.ProviderError, match="needs a base URL"):
        providers.call_chat("custom", api_key="k", model="m", system="s", user_parts=[])
    providers.call_chat("custom", api_key="k", model="m", system="s", user_parts=[],
                        base_url="https://host.example/v1/", extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    url, body = sent[-1]
    assert url == "https://host.example/v1/chat/completions"
    assert body["chat_template_kwargs"] == {"enable_thinking": False} and "thinking" not in body
    buffer = io.BytesIO()
    Image.effect_noise((2400, 1200), 80).convert("RGB").save(buffer, "PNG")
    kind, data = providers.shrink_image("image/png", buffer.getvalue(), 1024)
    assert kind == "image/jpeg" and max(Image.open(io.BytesIO(data)).size) == 1024
    assert providers.shrink_image("image/png", b"not an image", 1024) == ("image/png", b"not an image")
    assert providers.shrink_image("image/png", buffer.getvalue(), None)[1] == buffer.getvalue()
    accidents, _ = parse_output("<think>reasoning…</think>" + GOOD)
    assert accidents[0].fatalities == 6

    manager, control = _setup(tmp_path, 1)
    config = control.settings().providers["custom"]
    assert config.supports_images and config.max_image_side == 1024
    assert config.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert (config.max_output_tokens, config.timeout_seconds) == (8192, 900)
    control.set_key("custom", "k-test")
    monkeypatch.setenv("CUSTOM_BASE_URL", "https://host.example/v1")
    spec = RunSpec(provider="custom", model="Qwen3.8-27B", input_set="markdown", with_meta=True)
    manager.start(spec)
    _wait(manager, spec.config_id())
    assert sent[-1][0] == "https://host.example/v1/chat/completions"
    assert spec.config_id() == "custom__qwen3-8-27b__markdown__txt__meta"


# --- same-accident grouping benchmark ---------------------------------------------------------------
def _grouping_root(tmp_path: Path) -> Path:
    root = tmp_path / "g"
    spec = [("a1", "g1", "Bangladesh", "2025-05-01"), ("a2", "g1", "Bangladesh", "2025-05-01"),
            ("a3", "g2", "Bangladesh", "2025-05-02"), ("a4", "g2", "Bangladesh", "2025-05-02"),
            ("a5", "g3", "Kenya", "2025-07-09"), ("a6", "g4", "Peru", "2025-08-01")]
    for aid, grp, country, day in spec:
        folder = root / "articles" / aid
        folder.mkdir(parents=True)
        (folder / "article.md").write_text(f"Bus crash {grp} killed people near {country} town {grp}.")
        (folder / "meta.json").write_text(json.dumps({"id": aid, "publisher": "P" + aid, "title": f"Crash {grp}", "language": "en",
            "published_at": day, "images": [], "admin": {"group_id": grp, "country": country}}))
    (root / "labels").mkdir()
    return root


def test_grouping_metrics_and_cluster_bootstrap(tmp_path: Path) -> None:
    import numpy as np

    from traffic_fusion.extraction import grouping_eval as ge
    from traffic_fusion.extraction.grouping import Corpus

    corpus = Corpus(_grouping_root(tmp_path))
    assert corpus.ids == ["a1", "a2", "a3", "a4", "a5", "a6"]
    perfect = {a: corpus.group[a] for a in corpus.ids}
    m = ge.cluster_metrics(corpus, perfect)
    assert m["pairwise_all"]["f1"] == 1.0 and m["ari"] == pytest.approx(1.0) and m["groups_recovered_exactly"] == 4
    merged = {**perfect, "a3": "g1", "a4": "g1"}  # groups g1 and g2 wrongly merged
    mm = ge.cluster_metrics(corpus, merged)
    assert mm["predicted_clusters_merging_groups"] == 1 and mm["true_groups_split"] == 0 and mm["pairwise_all"]["precision"] < 1
    # consensus: together in 2 of 3 runs -> together
    runs = [{"a1": "x", "a2": "x", "a3": "y"}, {"a1": "x", "a2": "x", "a3": "z"}, {"a1": "p", "a2": "q", "a3": "z"}]
    cons = ge.consensus(runs, ["a1", "a2", "a3"])
    assert cons["a1"] == cons["a2"] and cons["a3"] != cons["a1"]
    # re-weighted estimates: one positive found, one missed, 1 of 2 sampled easy negatives wrongly called SAME
    pairs = [{"pair_id": "p1", "label": "same", "stratum": "positive", "group_a": "g1", "group_b": "g1", "cross_language": False, "toll_differs": False, "same_publisher": False},
             {"pair_id": "p2", "label": "same", "stratum": "positive", "group_a": "g2", "group_b": "g2", "cross_language": True, "toll_differs": False, "same_publisher": False},
             {"pair_id": "n1", "label": "different", "stratum": "easy", "group_a": "g1", "group_b": "g3", "cross_language": False, "toll_differs": False, "same_publisher": False},
             {"pair_id": "n2", "label": "different", "stratum": "easy", "group_a": "g2", "group_b": "g4", "cross_language": False, "toll_differs": False, "same_publisher": False}]
    w = ge.weights(pairs, {"positive": 2, "easy": 100})
    assert list(w) == [1.0, 1.0, 50.0, 50.0]
    boot = ge.cluster_bootstrap_weights(pairs)
    assert boot.shape == (ge.RESAMPLES, 4)
    score = ge.score_method(pairs, {"p1": True, "p2": False, "n1": True, "n2": False}, w, boot)
    assert score["estimated"]["recall"] == pytest.approx(0.5)
    assert score["estimated"]["precision"] == pytest.approx(1 / 51)  # 1 TP vs 50 estimated false positives
    assert score["by_stratum"]["easy"]["rate"] == 0.5 and score["positive_subsets"]["cross_language"]["recall"] == 0.0
    missing = ge.score_method(pairs, {"p1": True, "p2": None, "n1": False, "n2": False}, w, boot)
    assert missing["pairs_missing"] == 1 and missing["pairs_scored"] == 3
    assert not np.isnan(score["ci95"]["f1"]).any()


def test_grouping_pair_set_is_frozen_and_judge_rule_needs_both_orders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from traffic_fusion.extraction import grouping
    from traffic_fusion.extraction import grouping_eval as ge

    root = _grouping_root(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "benchmark" / "scraps").mkdir(parents=True)
    (tmp_path / "benchmark" / "scraps" / "candidates_b01.json").write_text(json.dumps({"groups": [
        {"group_id": "g1", "kind": "same_incident"}, {"group_id": "g2", "kind": "decoy_cluster", "decoy_for": "g1", "agent_note": "x"},
        {"group_id": "g3", "kind": "same_incident"}, {"group_id": "g4", "kind": "same_incident"}]}))
    meta = grouping.prepare(root)
    doc = json.loads((root / "matching" / "pairs.json").read_text())
    assert meta["pairs_sha256"] == (root / "matching" / "pairs.sha256").read_text().strip()
    assert meta["positive_pairs"] == 2 and sum(doc["population"].values()) == 15
    strata = {p["pair_id"]: p["stratum"] for p in doc["pairs"]}
    decoy = [p for p in doc["pairs"] if p["stratum"] == "hard_decoy"]
    assert len(decoy) == 4 and all({p["group_a"], p["group_b"]} == {"g1", "g2"} for p in decoy)
    assert grouping.prepare(root)["pairs_sha256"] == meta["pairs_sha256"]  # deterministic
    assert strata and "SAME only if" in doc["decision_rule"]
    # judge rule: both orders must say same_incident
    folder = root / "matching" / "pair-full"
    folder.mkdir(parents=True)
    pid = doc["pairs"][0]["pair_id"]
    for order, decision in (("AB", "same_incident"), ("BA", "different_incident")):
        (folder / f"{pid}__{order}.json").write_text(json.dumps({"status": "ok", "decision": decision, "confidence": 0.9, "input_tokens": 1, "output_tokens": 1}))
    result = ge.pair_predictions(root, "pair-full", doc["pairs"])
    assert result[pid]["pred"] is False and result[pid]["consistent"] is False
    assert result[doc["pairs"][1]["pair_id"]]["pred"] is None  # no call made: reported as missing, not as "different"
    ids, text = grouping.parse_clusters('{"clusters": [{"ids": ["A001", "A002", "A002", "Z9"]}]}', {"A001", "A002", "A003"})
    assert ids == [["A001", "A002"], ["A003"]] and text == {"missing": 1, "duplicates": 1, "unknown_ids": 1}


def test_group_benchmark_pipeline_is_repeatable_and_public_summary_has_no_identifiers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from traffic_fusion.extraction.grouping_pipeline import projection, run_benchmark

    root = _grouping_root(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "benchmark" / "scraps").mkdir(parents=True)
    (tmp_path / "benchmark" / "scraps" / "candidates_b01.json").write_text(json.dumps({"groups": [
        {"group_id": g, "kind": "same_incident"} for g in ("g1", "g2", "g3", "g4")]}))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k-test")
    calls: list[str] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        user = kwargs["json"]["messages"][1]["content"][0]["text"]  # type: ignore[index]
        calls.append(user[:20])
        if "<ARTICLES>" in user:  # clustering: group the cards by the tag in their titles
            by: dict[str, list[str]] = {}
            for card_id, tag in re.findall(r"\[(A\d+)\].*?title: Crash (g\d)", user):
                by.setdefault(tag, []).append(card_id)
            payload: dict[str, object] = {"clusters": [{"ids": ids} for ids in by.values()]}
        else:
            tags = re.findall(r"Bus crash (g\d)", user)
            same = len(tags) == 2 and tags[0] == tags[1]
            payload = {"decision": "same_incident" if same else "different_incident", "confidence": 0.9,
                       "evidence": [], "rationale": "tags"}
        return _reply(content=json.dumps(payload))

    import re

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    # coverage gate: unlabelled articles stop the run before any call
    with pytest.raises(RuntimeError, match="no annotation"):
        run_benchmark(root, log=lambda *_: None)
    assert calls == []
    (root / "labels" / "u.jsonl").write_text("".join(json.dumps({"article_id": f"a{i}"}) + "\n" for i in range(1, 7)))
    out = run_benchmark(root, repeats=3, concurrency=2, log=lambda *_: None)
    matching = root / "matching"
    for name in ("pairs.json", "pairs.sha256", "meta.json", "results.json", "report.html", "public_summary.json", "run_manifest.json"):
        assert (matching / name).exists(), name
    summary = json.loads((matching / "public_summary.json").read_text())
    by_method = {m["method"]: m for m in summary["methods"]}
    assert by_method["pair-full"]["f1"] == pytest.approx(1.0) and by_method["cluster-cards consensus"]["f1"] == pytest.approx(1.0)
    assert summary["design"]["articles"] == 6 and "checked by people" in summary["reading_note"]
    flat = json.dumps(summary)
    for forbidden in ("Crash g", "publisher", "pair_id", "group_id", "article_id"):
        assert forbidden not in flat, forbidden
    manifest = out["manifest"]
    assert manifest["pairs_sha256"] == (matching / "pairs.sha256").read_text().strip() and manifest["seeds"]["pairs"] == 20261109
    first_calls = len(calls)
    run_benchmark(root, repeats=3, concurrency=2, log=lambda *_: None)  # rerun: everything resumes from disk
    assert len(calls) == first_calls
    (matching / "pairs.json").write_text((matching / "pairs.json").read_text().replace('"label": "same"', '"label": "SAME"', 1))
    with pytest.raises(RuntimeError, match="frozen pair set was modified"):
        run_benchmark(root, log=lambda *_: None)
    assert projection(973, ("pair-full",), 3)["usd_high"] > projection(973, ("pair-full",), 3)["usd_low"] > 0


def test_public_grouping_summary_route(env: tuple[TestClient, Path]) -> None:
    client, root = env
    assert client.get("/api/x/public/grouping").json() == {"available": False}
    (root / "matching").mkdir()
    (root / "matching" / "public_summary.json").write_text(json.dumps({"title": "T", "methods": []}))
    (root / "matching" / "pairs.json").write_text('{"pairs": [{"pair_id": "SECRET"}]}')
    body = client.get("/api/x/public/grouping")  # anonymous
    assert body.status_code == 200 and body.json() == {"title": "T", "methods": []} and "SECRET" not in body.text


def test_grouped_incident_map_is_staff_visible_while_labelling_is_open_and_hides_admin_data(
    env: tuple[TestClient, Path]
) -> None:
    client, root = env
    (root / "matching").mkdir()
    (root / "matching" / "incidents.json").write_text(json.dumps({"source": "cluster-cards consensus", "model": "deepseek-flash", "incidents": [
        {"incident_id": "i1", "articles": ["abc123"], "tokens": {"in": 1, "out": 1},
         "fusion": {"headline": "Six killed near Kabirhat", "summary": "A truck hit an autorickshaw.", "when": "2025-11-04", "place_query": "Kabirhat, Noakhali, Bangladesh",
                    "killed": 6, "injured": None, "casualty_note": None, "vehicles": ["truck"], "source_disagreements": ["Tolls differ"]},
         "geo": {"latitude": 22.88, "longitude": 91.1, "granularity": "area", "uncertainty_radius_km": 5.0, "bbox_radius_km": 1.0, "display_name": "x", "query_used": "q", "fallback_level": 1, "method": "nominatim"}},
        {"incident_id": "i2", "articles": ["abc123"], "tokens": {"in": 1, "out": 1}, "fusion": {"headline": "No place", "summary": "s"}, "geo": None}]}))
    anon = client.get("/api/x/public/incidents.geojson", params={"source": "grouped"}).json()
    assert anon["locked"] is True and "Kabirhat" not in json.dumps(anon)
    csrf_admin = login(client, "boss")  # admin + reviewer, not an annotator: allowed while labelling is open
    staff = client.get("/api/x/public/incidents.geojson", params={"source": "grouped"}).json()
    assert staff["locked"] is False and staff["meta"] == {"source": "grouped", "records": 2, "mapped": 1, "verified": False}
    feature = staff["features"][0]
    assert feature["geometry"]["coordinates"] == [91.1, 22.88]  # [lon, lat]
    props = feature["properties"]
    assert props["headline"] == "Six killed near Kabirhat" and props["n_articles"] == 1 and props["articles"][0]["url"] == "https://x.test/a"
    assert props["uncertainty_radius_km"] == 5.0 and "not a crash coordinate" in props["location_method"] and props["verified"] is False
    assert "SECRET-CLAIM" not in json.dumps(staff) and "g001" not in json.dumps(staff)
    assert "grouped" in client.get("/api/x/public/sources").json()["sources"]
    client.cookies.clear()
    from traffic_fusion.extraction.accounts import AccountStore

    AccountStore(root).upsert("both", ["admin", "annotator"], PW)  # an annotator-admin stays locked out
    login(client, "both")
    assert client.get("/api/x/public/incidents.geojson", params={"source": "grouped"}).json()["locked"] is True
    client.cookies.clear()
    login(client, "ann_one")
    assert client.get("/api/x/public/incidents.geojson", params={"source": "grouped"}).json()["locked"] is True
    client.cookies.clear()
    csrf = login(client, "boss")
    settings = client.get("/api/x/admin/control").json()["settings"]
    settings["labelling_open"] = False
    client.put("/api/x/admin/control", json=settings, headers={"X-CSRF-Token": csrf})
    client.cookies.clear()
    assert client.get("/api/x/public/incidents.geojson", params={"source": "grouped"}).json()["locked"] is False
    assert csrf_admin


def test_reference_is_one_annotation_per_article_from_the_primary_annotator(tmp_path: Path) -> None:
    from traffic_fusion.extraction.annotation_store import ArticleStore
    from traffic_fusion.extraction.schema import AccidentRecord
    from traffic_fusion.extraction.scoring import build_reference

    store = ArticleStore(tmp_path)

    def acc(deaths: int | None, flag: bool = True) -> AccidentRecord:
        return AccidentRecord.model_validate({"accident": flag, "fatalities": deaths, "date": "2025-01-02", "country": "Peru"})

    # busy labels 3 articles, light labels 2: busy is primary wherever both labelled
    for a, deaths in (("a1", 5), ("a2", 6), ("a3", 7)):
        store.append("busy", a, [acc(deaths)], [], False, "")
    store.append("light", "a1", [acc(9)], [], False, "")
    store.append("light", "a4", [acc(2), acc(3)], [], False, "")  # two accidents: counted, fields not scored
    store.append("light", "a5", [acc(None, False)], [], True, "")  # marked not a usable article
    reference = build_reference(store.all_latest())
    assert set(reference) == {"a1", "a2", "a3", "a4", "a5"}
    assert reference["a1"]["fields"]["fatalities"] == 5 and reference["a1"]["annotators"] == 1  # busy wins over light
    assert reference["a4"]["accident_count"] == 2 and reference["a4"]["fields"] == {}
    assert reference["a5"] == {"usable": False, "annotators": 1}
    assert all("gold" not in json.dumps(row).lower() for row in reference.values())
