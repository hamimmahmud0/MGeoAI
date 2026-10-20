from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from traffic_fusion.api.moderation import SESSION_COOKIE, create_session
from traffic_fusion.api.x_auth import (
    check_lockout,
    clear_failures,
    current_user,
    record_failure,
)
from traffic_fusion.extraction.accounts import Account, AccountStore, Role
from traffic_fusion.extraction.annotation_store import ArticleLabel, ArticleStore
from traffic_fusion.extraction.control import ControlSettings, ControlStore, ModelPrice
from traffic_fusion.extraction.runs import RunManager, RunSpec
from traffic_fusion.extraction.schema import AccidentRecord, ImageLabel
from traffic_fusion.utils import stable_hash


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class LabelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accidents: list[AccidentRecord] = Field(min_length=1, max_length=20)
    images: list[ImageLabel] = Field(default_factory=list, max_length=20)
    unusable: bool = False
    notes: str = Field(default="", max_length=2000)


class AccountBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: list[Role] = Field(min_length=1)
    password: str | None = Field(default=None, max_length=256)
    disabled: bool | None = None


class PricingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pricing: dict[str, ModelPrice] = Field(max_length=200)


class SecretBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str | None = Field(default=None, max_length=500)


def _public(account: Account) -> dict[str, Any]:
    return {"username": account.username, "roles": account.roles, "disabled": account.disabled}


def _view(store: ArticleStore, article_id: str, mine: ArticleLabel | None) -> dict[str, Any]:
    """Annotator-visible article. Never includes admin metadata or model output."""
    meta = store.meta(article_id)
    images: list[dict[str, str]] = list(meta.get("images") or [])  # type: ignore[call-overload]
    return {
        "id": article_id,
        **{k: meta.get(k) for k in ("url", "publisher", "title", "published_at", "language")},
        "markdown": store.markdown(article_id),
        # Only locally saved copies (what a model is sent) are shown, never hot-linked.
        "images": [
            {
                "image_id": f"{article_id}-{i + 1}",
                "url": f"/api/x/articles/{article_id}/images/{i + 1}",
                "alt": img.get("alt", ""),
            }
            for i, img in enumerate(images)
            if img.get("file")
        ],
        "my_label": mine.model_dump(by_alias=True) if mine else None,
    }


def build_router(root: Path, secure_cookies: bool = False) -> APIRouter:
    accounts = AccountStore(root)
    control = ControlStore(root)
    runs = RunManager(root, control)
    articles = ArticleStore(root)
    router = APIRouter(prefix="/api/x", tags=["extraction"])

    def user(request: Request, *roles: str, csrf: bool = False) -> Account:
        return current_user(request, accounts, roles=roles or None, csrf=csrf)[0]

    # auth ------------------------------------------------------------------
    @router.post("/login")
    def login(body: LoginBody, request: Request, response: Response) -> dict[str, Any]:
        key = f"{body.username}|{request.client.host if request.client else '-'}"
        check_lockout(key)
        account = accounts.authenticate(body.username, body.password)
        if account is None:
            record_failure(key)
            raise HTTPException(status_code=401, detail="Invalid username or password")
        clear_failures(key)
        token, csrf = create_session(account.username)
        response.set_cookie(
            SESSION_COOKIE, token, httponly=True, samesite="lax",
            secure=secure_cookies, max_age=8 * 3600,
        )
        return {**_public(account), "csrf_token": csrf}

    @router.get("/me")
    def me(request: Request) -> dict[str, Any]:
        account, csrf = current_user(request, accounts)
        return {**_public(account), "csrf_token": csrf}

    @router.post("/logout")
    def logout(request: Request, response: Response) -> dict[str, bool]:
        current_user(request, accounts, csrf=True)
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

    # annotation (blind) ----------------------------------------------------
    @router.get("/articles")
    def list_articles(request: Request) -> dict[str, Any]:
        account = user(request, "annotator")
        mine = articles.latest(account.username)
        rng = random.Random(stable_hash(f"x-order|{account.username}"))
        ids = articles.article_ids()
        rng.shuffle(ids)
        rows = []
        for aid in ids:
            meta = articles.meta(aid)
            label = mine.get(aid)
            rows.append(
                {
                    "id": aid,
                    "title": meta.get("title"),
                    "publisher": meta.get("publisher"),
                    "done": label is not None,
                }
            )
        return {
            "annotator": account.username,
            "total": len(rows),
            "labeled": sum(r["done"] for r in rows),
            "articles": rows,
        }

    @router.get("/articles/{article_id}")
    def get_article(article_id: str, request: Request) -> dict[str, Any]:
        account = user(request, "annotator")
        if article_id not in set(articles.article_ids()):
            raise HTTPException(status_code=404, detail="Article not found")
        return _view(articles, article_id, articles.latest(account.username).get(article_id))

    @router.put("/labels/{article_id}")
    def put_label(article_id: str, body: LabelBody, request: Request) -> dict[str, Any]:
        account = user(request, "annotator", csrf=True)
        if article_id not in set(articles.article_ids()):
            raise HTTPException(status_code=404, detail="Article not found")
        if not body.accidents[0].accident and len(body.accidents) > 1:
            raise HTTPException(status_code=422, detail="accident=false allows one record only")
        record = articles.append(
            account.username, article_id, body.accidents, body.images, body.unusable, body.notes
        )
        return {"article_id": article_id, "revision": record.revision,
                "submitted_at": record.submitted_at}

    @router.get("/articles/{article_id}/images/{index}")
    def article_image(article_id: str, index: int, request: Request) -> FileResponse:
        user(request, "annotator", "admin", "reviewer")
        if article_id not in set(articles.article_ids()):
            raise HTTPException(status_code=404, detail="Not found")
        images = articles.meta(article_id).get("images") or []
        if not 1 <= index <= len(images):  # type: ignore[arg-type]
            raise HTTPException(status_code=404, detail="Not found")
        image = images[index - 1]  # type: ignore[index]
        name = str(image.get("file") or "")
        path = root / "articles" / article_id / "images" / name
        if not name or "/" in name or not path.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(path, media_type=str(image.get("content_type")),
                            headers={"X-Content-Type-Options": "nosniff"})

    # admin / control panel ---------------------------------------------------
    @router.get("/admin/accounts")
    def list_accounts(request: Request) -> list[dict[str, Any]]:
        user(request, "admin")
        return [_public(a) for a in accounts.all()]

    @router.put("/admin/accounts/{username}")
    def put_account(username: str, body: AccountBody, request: Request) -> dict[str, Any]:
        user(request, "admin", csrf=True)
        try:
            return _public(
                accounts.upsert(username, body.roles, body.password, body.disabled)
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/admin/control")
    def get_control(request: Request) -> dict[str, Any]:
        user(request, "admin")
        return {"settings": control.settings().model_dump(), "keys": control.key_status()}

    @router.put("/admin/control")
    def put_control(body: ControlSettings, request: Request) -> dict[str, Any]:
        user(request, "admin", csrf=True)
        control.save(body)
        return {"settings": body.model_dump(), "keys": control.key_status()}

    @router.put("/admin/keys/{provider}")
    def put_key(provider: str, body: SecretBody, request: Request) -> dict[str, Any]:
        user(request, "admin", csrf=True)
        try:
            control.set_key(provider, body.key)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"keys": control.key_status()}  # status only; never the key

    @router.put("/admin/pricing")
    def put_pricing(body: PricingBody, request: Request) -> dict[str, Any]:
        """Import/replace manual prices keyed "provider/model" ($ per 1M tokens)."""
        user(request, "admin", csrf=True)
        settings = control.settings()
        settings.pricing = body.pricing
        control.save(settings)
        return {"pricing": {k: v.model_dump() for k, v in body.pricing.items()}}

    @router.post("/admin/runs/estimate")
    def estimate_run(spec: RunSpec, request: Request) -> dict[str, Any]:
        user(request, "admin", csrf=True)
        return runs.estimate(spec)

    @router.post("/admin/runs")
    def start_run(spec: RunSpec, request: Request) -> dict[str, Any]:
        user(request, "admin", csrf=True)
        try:
            return runs.start(spec)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/admin/runs")
    def list_runs(request: Request) -> list[dict[str, Any]]:
        user(request, "admin")
        return runs.list()

    @router.post("/admin/runs/{config_id}/cancel")
    def cancel_run(config_id: str, request: Request) -> dict[str, bool]:
        user(request, "admin", csrf=True)
        return {"cancelled": runs.cancel(config_id)}

    return router
