from __future__ import annotations

import json
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
    assert scores["gold_articles"] == 1
    models = client.get("/api/x/public/scores/models").json()["models"][0]["metrics"]
    assert models["accident_flag"]["tp"] == 1 and models["scored_articles"] == 1
    assert models["fields_exact"]["fatalities"]["value"] == 1.0  # gold 6 (3-of-3 majority 2-of-3)
    assert models["fields_exact"]["date"]["value"] == 1.0  # day-level match
    assert models["evidence_quotes_verbatim"]["rate"] == 1.0
    sources = client.get("/api/x/public/sources").json()["sources"]
    assert sources[0] == "gold" and len(sources) == 2
    for source in sources:
        geo = client.get("/api/x/public/incidents.geojson", params={"source": source}).json()
        feature = geo["features"][0]
        assert feature["geometry"]["coordinates"] == [91.1, 22.88]  # [lon, lat]
        assert geo["meta"]["verified"] is (source == "gold")
        assert "SECRET-RAW" not in json.dumps(geo)
    assert client.get("/api/x/public/incidents.geojson", params={"source": "nope"}).status_code == 404
