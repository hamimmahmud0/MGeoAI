from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from traffic_fusion import __version__
from traffic_fusion.api.moderation import hash_reviewer_password
from traffic_fusion.config import Settings
from traffic_fusion.corpus.build import build_corpus, load_candidates
from traffic_fusion.corpus.discovery import load_country_profiles
from traffic_fusion.corpus.materialize import materialize_corpus
from traffic_fusion.corpus.reporting import render_validation_report
from traffic_fusion.corpus.store import CorpusStore
from traffic_fusion.corpus.validation import validate_corpus
from traffic_fusion.evaluation import extraction_coverage, matching_metrics
from traffic_fusion.ingest.discovery import write_manifest
from traffic_fusion.models import FusedIncident, MatchDecision
from traffic_fusion.pipeline import PipelineFailure, export_schemas, run_live_smoke, run_pipeline
from traffic_fusion.utils import write_json

app = typer.Typer(
    no_args_is_help=True,
    help="MGeoAI provenance-preserving traffic incident intelligence.",
)


@app.command("hash-reviewer-password")
def hash_reviewer_password_command() -> None:
    """Generate a PBKDF2 password value for MGEOAI_REVIEWERS_JSON."""
    password = typer.prompt("Reviewer password", hide_input=True, confirmation_prompt=True)
    typer.echo(hash_reviewer_password(password))


@app.command()
def doctor(provider: str = typer.Option("deepseek", help="Provider to validate.")) -> None:
    """Check runtime, configuration, prompts, and optional live credentials."""
    settings = Settings.load()
    checks = {
        "mgeoai_version": __version__,
        "python": sys.version.split()[0],
        "fusion_prompt": Path("assets/mllm_prompts/data_fusion_prompt.md").exists(),
        "provider": provider,
        "model": "recorded-fixture-v2"
        if provider == "recorded"
        else settings.deepseek_model or "unconfigured",
        "live_configuration_errors": [] if provider == "recorded" else settings.validate_live(),
    }
    typer.echo(json.dumps(checks, indent=2))
    if checks["live_configuration_errors"]:
        raise typer.Exit(1)


@app.command()
def ingest(input_dir: Path, output: Path = typer.Option(..., help="Manifest JSONL path.")) -> None:
    """Discover supported local artifacts and write an idempotent manifest."""
    rows = write_manifest(input_dir, output)
    typer.echo(f"Discovered {len(rows)} supported artifacts -> {output}")


@app.command("corpus-build")
def corpus_build_command(
    candidates: list[Path] = typer.Option(..., "--candidates", help="Collected JSONL file."),
    country_config: Path = typer.Option(Path("configs/global_countries.toml")),
    output_dir: Path = typer.Option(Path("corpus/global-v1")),
) -> None:
    """Build and validate the international metadata/excerpt corpus."""
    result = build_corpus(
        load_candidates(candidates),
        load_country_profiles(country_config),
        output_dir,
    )
    typer.echo(result.model_dump_json(indent=2))


@app.command("corpus-validate")
def corpus_validate_command(corpus_dir: Path = typer.Option(Path("corpus/global-v1"))) -> None:
    """Validate country/source quotas, hashes, reviews, and multi-source incidents."""
    report = validate_corpus(CorpusStore(corpus_dir))
    typer.echo(render_validation_report(report))
    if not report.valid:
        raise typer.Exit(1)


@app.command("corpus-materialize")
def corpus_materialize_command(
    corpus_dir: Path = typer.Option(Path("corpus/global-v1")),
    output_dir: Path = typer.Option(Path("build/global-scraps")),
) -> None:
    """Create pipeline-compatible scraps without leaking curation labels."""
    result = materialize_corpus(CorpusStore(corpus_dir), output_dir)
    typer.echo(result.model_dump_json(indent=2))


@app.command("export-schemas")
def export_schema_command(output_dir: Path = typer.Option(Path("schemas"))) -> None:
    """Export canonical versioned JSON Schemas."""
    export_schemas(output_dir)
    typer.echo(f"Schemas written to {output_dir}")


@app.command()
def run(
    input_dir: Path = typer.Option(Path("assets/scraps"), "--input"),
    provider: str = typer.Option("deepseek", help="deepseek or recorded"),
    output_dir: Path = typer.Option(Path("outputs/demo")),
) -> None:
    """Run discovery through validated fusion and reporting."""
    try:
        result = run_pipeline(input_dir, output_dir, provider, Settings.load())
    except (PipelineFailure, RuntimeError) as exc:
        typer.echo(f"Pipeline failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(result.model_dump_json(indent=2))


@app.command()
def serve(
    data_dir: Path = typer.Option(Path("outputs/demo")),
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Serve the API and production frontend build."""
    import uvicorn

    from traffic_fusion.api.app import create_app

    uvicorn.run(create_app(data_dir), host=host, port=port)


@app.command("smoke-live")
def smoke_live(
    data_dir: Path = typer.Option(Path("outputs/demo")),
    output_dir: Path = typer.Option(Path("outputs/live-smoke")),
) -> None:
    """Make one live match and one live fusion call over normalized demo data."""
    try:
        result = run_live_smoke(data_dir, output_dir, Settings.load())
    except (PipelineFailure, RuntimeError) as exc:
        typer.echo(f"Live smoke failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result, indent=2))


@app.command()
def evaluate(
    data_dir: Path = typer.Option(Path("outputs/demo")),
    golden_pairs: Path = typer.Option(Path("tests/fixtures/golden_pairs.json")),
    output: Path = typer.Option(Path("outputs/demo/evaluation.json")),
) -> None:
    """Report small-sample matching metrics and extraction coverage."""
    gold = json.loads(golden_pairs.read_text())
    decisions = [
        MatchDecision.model_validate(item)
        for item in json.loads((data_dir / "matches.json").read_text())
    ]
    incidents = [
        FusedIncident.model_validate(item)
        for item in json.loads((data_dir / "incidents.json").read_text())
    ]
    result = {
        "matching": matching_metrics(gold, decisions),
        "extraction": extraction_coverage(incidents),
        "warning": "Small development fixture; not a model-accuracy claim.",
    }
    write_json(output, result)
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
