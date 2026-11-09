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


@extract_app.command("run")
def run_command(
    provider: str = typer.Option("deepseek"),
    model: str = typer.Option(..., help="Model id, e.g. deepseek-flash"),
    input_set: str = typer.Option("markdown", help="markdown or raw"),
    with_images: bool = typer.Option(False),
    with_meta: bool = typer.Option(False, help="Send the page's publication date to the model"),
    reasoning: bool | None = typer.Option(None, "--reasoning/--no-reasoning", help="switch the model's own thinking on or off (deepseek, custom); default: the provider's own"),
    limit: int | None = typer.Option(None),
    only_failed: bool = typer.Option(False),
    concurrency: int | None = typer.Option(None, help="Override the control-panel concurrency"),
    root: Path | None = typer.Option(None),
) -> None:
    """Run extraction from the command line. The API key comes from the environment
    (DEEPSEEK_API_KEY, OPENROUTER_API_KEY...), never from an argument."""
    import time

    from traffic_fusion.extraction.control import ControlStore
    from traffic_fusion.extraction.runs import RunManager, RunSpec

    base = _root(root)
    manager = RunManager(base, ControlStore(base))
    spec = RunSpec(provider=provider, model=model, input_set=input_set, with_images=with_images,
                   with_meta=with_meta, reasoning=reasoning, limit=limit, only_failed=only_failed)
    try:
        manager.start(spec, concurrency)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"started {spec.config_id()}")
    while True:
        time.sleep(15)
        state = manager.status(spec.config_id()) or {}
        typer.echo(f"{state.get('status')} done={state.get('done')} failed={state.get('failed')} "
                   f"tokens={state.get('input_tokens')}/{state.get('output_tokens')} cost={state.get('cost_usd')}")
        if state.get("status") != "running":
            break


@extract_app.command("group-prepare")
def group_prepare_command(root: Path | None = typer.Option(None)) -> None:
    """Freeze the benchmark pair set (writes matching/pairs.json + sha256 + meta.json)."""
    from traffic_fusion.extraction.grouping import prepare

    typer.echo(json.dumps(prepare(_root(root)), indent=1))


@extract_app.command("group-run")
def group_run_command(
    method: str = typer.Option(..., help="pair-full | pair-fields | cluster-cards | cluster-full"),
    root: Path | None = typer.Option(None),
    limit: int | None = typer.Option(None, help="pilot: number of pairs (spread over strata)"),
    concurrency: int = typer.Option(20),
    token_limit: int = typer.Option(3_000_000, help="hard stop on total tokens for this call"),
    thinking: str = typer.Option("default", help="default | disabled"),
    variant: str = typer.Option("both", help="pair-fields only: both | human | model"),
    repeats: int = typer.Option(3, help="cluster methods: independent runs"),
    provider: str = typer.Option("deepseek", help="deepseek | openrouter (key from the environment)"),
    model: str = typer.Option("deepseek-flash", help="model id at that provider"),
    reasoning: bool = typer.Option(False, help="custom endpoints: switch the model's own thinking on"),
) -> None:
    """Run one grouping method (DEEPSEEK_API_KEY / OPENROUTER_API_KEY from the environment).

    A model other than the default writes to its own folders, e.g. matching/pair-full@openrouter-...
    """
    from traffic_fusion.extraction import grouping

    base = _root(root)
    engine = grouping.Engine(provider, model, reasoning)
    if method.startswith("pair-"):
        out = grouping.run_pair_jobs(base, method, limit, concurrency, token_limit, thinking, variant=variant, engine=engine)
    elif method in ("cluster-cards", "cluster-full"):
        out = grouping.run_cluster_jobs(base, method.split("-", 1)[1], repeats, token_limit, thinking, engine=engine)
    else:
        raise typer.BadParameter("unknown method")
    typer.echo(json.dumps(out))


@extract_app.command("group-benchmark")
def group_benchmark_command(
    root: Path | None = typer.Option(None),
    methods: str = typer.Option("all", help="comma list or 'all': pair-full,pair-fields-both,pair-fields-human,pair-fields-model,cluster-cards,cluster-full"),
    refresh_pairs: bool = typer.Option(False, help="rebuild (and re-freeze) the pair set; invalidates earlier results"),
    concurrency: int = typer.Option(25),
    repeats: int = typer.Option(3),
    token_limit: int = typer.Option(8_000_000, help="hard token stop per method"),
    skip_annotation_check: bool = typer.Option(False),
    yes: bool = typer.Option(False, help="spend tokens; without it only the projection is printed"),
) -> None:
    """Reproduce the whole same-accident grouping benchmark (needs DEEPSEEK_API_KEY)."""
    from traffic_fusion.extraction.grouping_pipeline import (
        METHODS,
        annotation_coverage,
        projection,
        run_benchmark,
    )

    base = _root(root)
    chosen = METHODS if methods == "all" else tuple(m.strip() for m in methods.split(","))
    unknown = [m for m in chosen if m not in METHODS]
    if unknown:
        raise typer.BadParameter(f"unknown method(s): {unknown}")
    pairs_file = base / "matching" / "pairs.json"
    n_pairs = len(json.loads(pairs_file.read_text("utf-8"))["pairs"]) if pairs_file.exists() else 973
    if not yes:
        done, total = annotation_coverage(base)
        typer.echo(f"annotation coverage {done}/{total}; projection: {json.dumps(projection(n_pairs, chosen, repeats))}")
        typer.echo("dry run only: add --yes to run")
        return
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise typer.BadParameter("set DEEPSEEK_API_KEY in the environment")
    run_benchmark(base, chosen, refresh_pairs, concurrency, repeats, token_limit, skip_annotation_check, typer.echo)


@extract_app.command("build-incidents")
def build_incidents_command(
    root: Path | None = typer.Option(None),
    concurrency: int = typer.Option(20),
    geocode: bool = typer.Option(True, help="look up places on OpenStreetMap (about 1 request per second)"),
) -> None:
    """Fuse each article group into one incident (DeepSeek) and place it on the map data (needs DEEPSEEK_API_KEY)."""
    from traffic_fusion.extraction.incidents import build_incidents

    if not os.getenv("DEEPSEEK_API_KEY"):
        raise typer.BadParameter("set DEEPSEEK_API_KEY in the environment")
    build_incidents(_root(root), concurrency, geocode=geocode, log=typer.echo)


@extract_app.command("group-eval")
def group_eval_command(
    root: Path | None = typer.Option(None),
    output: Path = typer.Option(Path("grouping_report.html")),
) -> None:
    """Score all grouping methods and write the HTML report (+ results.json next to it)."""
    from traffic_fusion.extraction.grouping_eval import evaluate, render

    base = _root(root)
    result = evaluate(base)
    (base / "matching" / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=float) + "\n", "utf-8")
    output.write_text(render(base, result), encoding="utf-8")
    typer.echo(f"wrote {output} and {base / 'matching' / 'results.json'}")


@extract_app.command("report")
def report_command(
    root: Path | None = typer.Option(None),
    output: Path = typer.Option(Path("model_vs_annotators.html")),
) -> None:
    """Write the model-vs-annotators comparison report (self-contained HTML)."""
    from traffic_fusion.extraction.report import build_report

    output.write_text(build_report(_root(root)), encoding="utf-8")
    typer.echo(f"wrote {output}")


@extract_app.command("export-dataset")
def export_dataset_command(
    root: Path | None = typer.Option(None),
    out: Path = typer.Option(..., help="Folder to write the dataset into (data/*.jsonl)."),
    repo_id: str = typer.Option("hamimmahmud0/mgeoai-road-accident-news"),
) -> None:
    """Write the public, text-free dataset (annotators pseudonymised, no article text or quotes)."""
    from traffic_fusion.extraction.dataset import export_dataset

    typer.echo(json.dumps(export_dataset(_root(root), out, repo_id), indent=1))


@extract_app.command("reproduce")
def reproduce_command(
    dataset: str = typer.Option(..., help="Hugging Face dataset slug (owner/name) or a local export folder."),
    output: Path = typer.Option(Path("reproduced"), help="Folder for the regenerated reports."),
) -> None:
    """Recreate the annotation, model, grouping, comparison and incident-map reports from the dataset alone."""
    from traffic_fusion.extraction.reproduce import reproduce

    typer.echo(json.dumps(reproduce(dataset, output), indent=1))


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
