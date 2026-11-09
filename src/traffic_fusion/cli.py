from __future__ import annotations

from pathlib import Path

import typer

from traffic_fusion import __version__
from traffic_fusion.extraction.cli import extract_app

app = typer.Typer(
    no_args_is_help=True,
    help="MGeoAI: road-accident news extraction, annotation, grouping and the open dashboard.",
)
app.add_typer(extract_app, name="x")


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


@app.command()
def serve(
    extraction_dir: Path = typer.Option(Path("extraction"), envvar="MGEOAI_EXTRACTION_DIR", help="Data directory"),
    host: str = "127.0.0.1",
    port: int = 8000,
    data_dir: Path | None = typer.Option(None, hidden=True, help="Ignored; kept so old service files still start."),
) -> None:
    """Serve the dashboard API and the built frontend (web/dist)."""
    import uvicorn

    from traffic_fusion.api.app import create_app

    _ = data_dir
    uvicorn.run(create_app(extraction_dir), host=host, port=port)
