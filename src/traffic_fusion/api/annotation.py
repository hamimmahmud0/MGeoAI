from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from traffic_fusion.annotation.store import USERNAME_RE, AnnotationItem, AnnotationStore, Label
from traffic_fusion.api.moderation import require_reviewer
from traffic_fusion.utils import stable_hash


class LabelBody(BaseModel):
    label: Label
    notes: str = Field(default="", max_length=2000)


def _order(username: str, items: list[AnnotationItem]) -> list[tuple[AnnotationItem, bool]]:
    """Per-annotator deterministic shuffle and left/right swap."""
    rng = random.Random(stable_hash(f"order|{username}"))
    shuffled = sorted(items, key=lambda item: item.item_id)
    rng.shuffle(shuffled)
    return [
        (item, int(stable_hash(f"swap|{username}|{item.item_id}"), 16) % 2 == 1)
        for item in shuffled
    ]


def build_router(annotation_dir: Path) -> APIRouter:
    """Blind pair labelling. Signed-in reviewers are the annotators."""
    store = AnnotationStore(annotation_dir)
    router = APIRouter(prefix="/api/annotate", tags=["annotation"])

    def annotator(request: Request, *, csrf: bool = False) -> str:
        username, _ = require_reviewer(request, csrf=csrf)
        if not USERNAME_RE.match(username):
            raise HTTPException(
                status_code=403,
                detail="Annotator names must be lowercase letters, digits or underscores",
            )
        return username

    @router.get("/items")
    def items(request: Request) -> dict[str, Any]:
        user = annotator(request)
        mine = store.latest(user)
        rows = []
        for item, swapped in _order(user, store.items()):
            left, right = (item.right, item.left) if swapped else (item.left, item.right)
            record = mine.get(item.item_id)
            rows.append(
                {
                    "item_id": item.item_id,
                    "left": left.model_dump(),
                    "right": right.model_dump(),
                    "my_label": {
                        "label": record.label,
                        "notes": record.notes,
                        "submitted_at": record.submitted_at,
                        "revision": record.revision,
                    }
                    if record
                    else None,
                }
            )
        return {
            "annotator": user,
            "total": len(rows),
            "labeled": sum(row["my_label"] is not None for row in rows),
            "items": rows,
        }

    @router.put("/labels/{item_id}")
    def put_label(item_id: str, body: LabelBody, request: Request) -> dict[str, Any]:
        user = annotator(request, csrf=True)
        if item_id not in {item.item_id for item in store.items()}:
            raise HTTPException(status_code=404, detail="Item not found")
        record = store.append_label(user, item_id, body.label, body.notes)
        return {
            "item_id": record.item_id,
            "label": record.label,
            "notes": record.notes,
            "submitted_at": record.submitted_at,
            "revision": record.revision,
        }

    return router
