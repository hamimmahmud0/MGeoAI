from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

import typer

from traffic_fusion.annotation.stats import agreement_report, consensus
from traffic_fusion.annotation.store import USERNAME_RE, AnnotationItem, AnnotationStore
from traffic_fusion.utils import write_json

annotate_app = typer.Typer(no_args_is_help=True, help="Blind multi-annotator benchmark labelling.")
DIR_OPTION = typer.Option(Path("annotation"), "--dir", envvar="MGEOAI_ANNOTATION_DIR")
LABEL_TO_GOLD = {
    "same_incident": "same_incident",
    "related_distinct": "different",
    "different": "different",
    "cannot_tell": "ambiguous",
}


@annotate_app.command("init-users")
def init_users(
    names: list[str],
    directory: Path = DIR_OPTION,
    reset: bool = typer.Option(False, help="Re-issue passwords for names that already exist."),
) -> None:
    """Issue random passwords and PBKDF2 hashes for annotators (reviewer accounts).

    Writes `reviewers.json` (the value for MGEOAI_REVIEWERS_JSON) and
    `initial_passwords.txt`, both 0600; passwords are never printed.
    """
    from traffic_fusion.api.moderation import hash_reviewer_password

    lowered = [name.lower() for name in names]
    bad = [name for name in lowered if not USERNAME_RE.match(name)]
    if bad:
        typer.echo(f"error: invalid annotator name(s): {', '.join(bad)}", err=True)
        raise typer.Exit(1)
    directory.mkdir(parents=True, exist_ok=True)
    reviewers_path = directory / "reviewers.json"
    hashes: dict[str, str] = (
        json.loads(reviewers_path.read_text(encoding="utf-8")) if reviewers_path.exists() else {}
    )
    issued = [name for name in lowered if reset or name not in hashes]
    skipped = [name for name in lowered if name not in issued]
    passwords = []
    for name in issued:
        password = secrets.token_urlsafe(12)
        hashes[name] = hash_reviewer_password(password)
        passwords.append(f"{name}\t{password}\n")
    for filename, content, flags in (
        ("reviewers.json", json.dumps(hashes, indent=2) + "\n", os.O_TRUNC),
        ("initial_passwords.txt", "".join(passwords), os.O_APPEND),
    ):
        if not content.strip():
            continue
        path = directory / filename
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(path, 0o600)
    typer.echo(f"Issued {len(issued)} account(s) in {directory}")
    if skipped:
        typer.echo(f"Kept existing: {', '.join(skipped)} (use --reset to re-issue)")
    typer.echo(
        'Start the server with: export MGEOAI_REVIEWERS_JSON="$(cat annotation/reviewers.json)" '
        "MGEOAI_SESSION_SECRET=<32+ random characters>"
    )
    typer.echo("Hand out each person's own line from initial_passwords.txt, then delete it.")


@annotate_app.command("import-items")
def import_items(
    source: Path,
    directory: Path = DIR_OPTION,
    force: bool = typer.Option(False, help="Overwrite items even though labels already exist."),
) -> None:
    """Split a candidate file into annotator-visible items and admin-only metadata.

    Each source entry: item_id, left, right, plus optional category/selection (admin only).
    """
    if not force and any((directory / "labels").glob("*.jsonl")):
        typer.echo(
            "error: labels already exist; re-importing would orphan them (use --force)", err=True
        )
        raise typer.Exit(1)
    raw: list[dict[str, Any]] = json.loads(source.read_text(encoding="utf-8"))
    served, meta = [], {}
    for entry in raw:
        item = AnnotationItem.model_validate(
            {key: entry[key] for key in ("item_id", "left", "right")}
        )
        served.append(item.model_dump())
        meta[item.item_id] = {k: v for k, v in entry.items() if k not in ("left", "right")}
    if len({item["item_id"] for item in served}) != len(served):
        typer.echo("error: duplicate item_id", err=True)
        raise typer.Exit(1)
    write_json(directory / "items.json", served)
    write_json(directory / "admin_meta.json", meta)
    typer.echo(f"Imported {len(served)} items")


@annotate_app.command()
def status(directory: Path = DIR_OPTION) -> None:
    """Progress per annotator."""
    store = AnnotationStore(directory)
    total = len(store.items())
    for name, recs in store.all_latest().items():
        typer.echo(f"{name}: {len(recs)}/{total}")


@annotate_app.command()
def agreement(directory: Path = DIR_OPTION, output: Path | None = None) -> None:
    """Krippendorff's alpha and pairwise Cohen's kappa over latest labels."""
    report = agreement_report(AnnotationStore(directory).all_latest())
    if output:
        write_json(output, report)
    typer.echo(json.dumps(report, indent=2))


@annotate_app.command()
def export(
    output: Path = typer.Option(..., help="Gold file in golden_pairs.json shape."),
    directory: Path = DIR_OPTION,
    min_labels: int = typer.Option(3, help="Minimum labels before a consensus can be formed."),
) -> None:
    """Export strict-majority consensus; unresolved items are listed, not guessed."""
    store = AnnotationStore(directory)
    items = {item.item_id: item for item in store.items()}
    result = consensus(store.all_latest(), min_labels=min_labels)
    gold, unresolved = [], []
    for item_id, row in sorted(result.items()):
        item = items.get(item_id)
        if item is None:
            continue
        if row["label"] is None:
            unresolved.append({"item_id": item_id, "votes": row["votes"]})
            continue
        gold.append(
            {
                "left": item.left.id,
                "right": item.right.id,
                "label": LABEL_TO_GOLD[row["label"]],
                "annotation_label": row["label"],
                "item_id": item_id,
            }
        )
    write_json(output, gold)
    write_json(output.with_name(output.stem + ".unresolved.json"), unresolved)
    typer.echo(f"{len(gold)} resolved, {len(unresolved)} unresolved")
