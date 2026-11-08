from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from traffic_fusion.extraction.accounts import AccountStore, Role
from traffic_fusion.extraction.intake import build_articles

extract_app = typer.Typer(no_args_is_help=True, help="LLM extraction workspace.")

DEFAULT_ACCOUNTS: dict[str, list[Role]] = {
    "admin": ["admin", "reviewer"],
    "reviewer": ["reviewer"],
    "hamim": ["annotator"],
    "oishik": ["annotator"],
    "mubasshir": ["annotator"],
    "rubayet": ["annotator"],
}


def _root(value: Path | None) -> Path:
    return value or Path(os.getenv("MGEOAI_EXTRACTION_DIR", "extraction"))


@extract_app.command("intake")
def intake_command(
    pages: Path = typer.Option(Path("benchmark/pages")),
    scraps: Path = typer.Option(Path("benchmark/scraps")),
    root: Path | None = typer.Option(None, help="Extraction root (default ./extraction)"),
) -> None:
    """Build per-article folders (raw, model input, markdown, image candidates)."""
    report = build_articles(pages, scraps, _root(root))
    typer.echo(json.dumps({**report, "missing": len(report["missing"])}, indent=2))
    for row in report["missing"]:
        typer.echo(f"missing {row['id']} {row['url']} ({row['dropped'] or 'not fetched'})")


@extract_app.command("fetch-images")
def fetch_images_command(root: Path | None = typer.Option(None)) -> None:
    """Download article images politely (robots.txt, 3 s/host delay, 5 MB cap)."""
    from traffic_fusion.extraction.images import fetch_article_images, refresh_candidates

    base = _root(root)
    typer.echo("refresh " + json.dumps(refresh_candidates(base)))
    typer.echo(json.dumps(fetch_article_images(base), indent=2))


@extract_app.command("backup")
def backup_command(
    root: Path | None = typer.Option(None),
    bucket: str = typer.Option("hamimmahmud0/mgeoai-backup", help="Hugging Face bucket id"),
    state_dir: Path | None = typer.Option(None, help="Where the last-backup manifest is kept"),
) -> None:
    """Back up labels, model runs and news sources to the bucket (needs HF_TOKEN)."""
    from traffic_fusion.extraction.backup import run_backup

    if not os.getenv("HF_TOKEN"):
        raise typer.BadParameter("set HF_TOKEN in the environment")
    status = run_backup(_root(root), bucket, state_dir)
    typer.echo(json.dumps({k: status[k] for k in ("last_backup_utc", "history_entry", "files", "changed")}))


@extract_app.command("report")
def report_command(
    root: Path | None = typer.Option(None),
    output: Path = typer.Option(Path("model_vs_annotators.html")),
) -> None:
    """Write the model-vs-annotators comparison report (self-contained HTML)."""
    from traffic_fusion.extraction.report import build_report

    output.write_text(build_report(_root(root)), encoding="utf-8")
    typer.echo(f"wrote {output}")


@extract_app.command("init-accounts")
def init_accounts_command(root: Path | None = typer.Option(None)) -> None:
    """Create missing accounts. Passwords go to a private file; they are never printed."""
    base = _root(root)
    created = AccountStore(base).bootstrap(DEFAULT_ACCOUNTS)
    if not created:
        typer.echo("All default accounts already exist; nothing written.")
        return
    path = base / "initial_passwords.txt"
    base.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for name, password in created.items():
            handle.write(f"{name}\t{password}\n")
    path.chmod(0o600)
    typer.echo(f"Created {len(created)} account(s): {', '.join(created)}")
    typer.echo(f"Passwords written to {path} (mode 600). Hand them out, then delete the file.")
