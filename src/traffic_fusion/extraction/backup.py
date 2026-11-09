"""Back up annotations, model outputs and the news sources to a Hugging Face bucket.

Layout in the bucket (see docs/BUCKET_README.md, uploaded as README.md):
  latest/            mirror of everything worth keeping (never deletes remote files)
  history/<UTC>/     one entry per backup in which labels, runs or settings changed:
                     the full label files, the changed run results, and CHANGES.json
  manifest/latest.json   sha256 + size of every backed-up file at the last backup (authoritative)
  manifest/status.json   last run time and outcome (a liveness signal)

Never backed up: accounts.json, initial_passwords.txt, API keys, lock files.
Uploads go through the `hf` CLI (HF_TOKEN from the environment, never logged).
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BUCKET_DEFAULT = "hamimmahmud0/mgeoai-backup"
ARTICLE_FILES = ("meta.json", "article.md", "model_raw.html", "raw.html")
LIVE_PREFIXES = ("labels/", "runs/")  # changes here create a history entry
LIVE_FILES = ("control.json", "geocode_cache.json")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(root: Path) -> dict[str, dict[str, Any]]:
    """Relative path -> {sha256, bytes} for every file that is backed up."""
    files: list[Path] = []
    articles = root / "articles"
    if articles.is_dir():
        for folder in sorted(articles.iterdir()):
            files += [folder / name for name in ARTICLE_FILES if (folder / name).is_file()]
            if (folder / "images").is_dir():
                files += sorted(p for p in (folder / "images").iterdir() if p.is_file())
    for pattern in ("labels/*.jsonl", "runs/**/*.json"):
        files += sorted(root.glob(pattern))
    files += [root / name for name in LIVE_FILES if (root / name).is_file()]
    return {
        p.relative_to(root).as_posix(): {"sha256": _sha(p), "bytes": p.stat().st_size}
        for p in files
    }


def label_stats(root: Path) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for path in sorted((root / "labels").glob("*.jsonl")) if (root / "labels").is_dir() else []:
        articles: set[str] = set()
        lines = 0
        for line in path.read_text("utf-8").splitlines():
            if line.strip():
                lines += 1
                articles.add(json.loads(line)["article_id"])
        stats[path.stem] = {"label_lines": lines, "articles": len(articles)}
    return stats


def diff(old: dict[str, dict[str, Any]], new: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(new) - set(old)),
        "modified": sorted(k for k in new if k in old and new[k]["sha256"] != old[k]["sha256"]),
        "removed": sorted(set(old) - set(new)),
    }


def _link_tree(root: Path, files: list[str], target: Path) -> None:
    for rel in files:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(root / rel, dest)  # hardlink keeps mtimes and costs no space
        except OSError:
            shutil.copy2(root / rel, dest)


def _sources_csv(root: Path, target: Path) -> None:
    rows = []
    for meta_path in sorted((root / "articles").glob("*/meta.json")):
        m = json.loads(meta_path.read_text("utf-8"))
        rows.append({
            "article_id": m["id"], "publisher": m.get("publisher"), "title": m.get("title"),
            "url": m.get("url"), "published_at": m.get("published_at"), "language": m.get("language"),
            "source_variant": m.get("source_variant"), "markdown_chars": m.get("markdown_chars"),
            "images_saved": sum(1 for i in m.get("images", []) if i.get("file")),
        })
    with (target / "sources.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["article_id"])
        writer.writeheader()
        writer.writerows(rows)


def _schemas(target: Path) -> None:
    from traffic_fusion.extraction.annotation_store import ArticleLabel
    from traffic_fusion.extraction.schema import AccidentRecord

    folder = target / "schemas"
    folder.mkdir(parents=True, exist_ok=True)
    for name, model in (("article_label", ArticleLabel), ("accident_record", AccidentRecord)):
        (folder / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(by_alias=True), indent=1) + "\n", "utf-8")


class Hf:
    """Thin wrapper over the `hf` CLI; the token only travels in the environment."""

    def __init__(self, bucket: str, binary: str = "hf") -> None:
        self.bucket, self.binary = bucket, binary

    def _run(self, *args: str) -> str:
        result = subprocess.run([self.binary, *args], capture_output=True, text=True, check=False,
                                env=os.environ.copy(), timeout=3600)
        if result.returncode != 0:
            raise RuntimeError(f"hf {' '.join(args[:2])} failed: {result.stderr.strip()[:400]}")
        return result.stdout

    def sync_up(self, local: Path, prefix: str) -> None:
        self._run("buckets", "sync", str(local), f"hf://buckets/{self.bucket}/{prefix}", "--quiet")

    def put(self, local: Path, remote: str) -> None:
        self._run("buckets", "cp", str(local), f"hf://buckets/{self.bucket}/{remote}")

    def get(self, remote: str, local: Path) -> bool:
        try:
            self._run("buckets", "cp", f"hf://buckets/{self.bucket}/{remote}", str(local))
            return local.exists()
        except RuntimeError:
            return False


def run_backup(root: Path, bucket: str = BUCKET_DEFAULT, state_dir: Path | None = None,
               hf_binary: str = "hf", now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    state = state_dir or root.parent / "backup_state"
    state.mkdir(parents=True, exist_ok=True)
    hf = Hf(bucket, hf_binary)
    manifest = collect(root)
    if not any(k.startswith("labels/") for k in manifest):
        raise RuntimeError("no label files found; refusing to back up an empty tree")

    previous: dict[str, dict[str, Any]] = {}
    prev_stats: dict[str, dict[str, int]] = {}
    baseline = state / "manifest.json"
    with tempfile.TemporaryDirectory() as scratch:
        scratch_path = Path(scratch)
        prev_doc: dict[str, Any] = {}
        if baseline.exists():
            prev_doc = json.loads(baseline.read_text("utf-8"))
        elif hf.get("manifest/latest.json", scratch_path / "prev.json"):
            prev_doc = json.loads((scratch_path / "prev.json").read_text("utf-8"))
        previous = prev_doc.get("files", {})
        prev_stats = prev_doc.get("label_stats", {})
        changes = diff(previous, manifest)
        live_changed = [p for p in [*changes["added"], *changes["modified"], *changes["removed"]]
                        if p.startswith(LIVE_PREFIXES) or p in LIVE_FILES]
        first_run = not previous

        # 1. mirror to latest/ (adds and updates; never deletes remote files)
        stage_latest = scratch_path / "latest"
        _link_tree(root, list(manifest), stage_latest)
        _sources_csv(root, stage_latest)
        _schemas(stage_latest)
        hf.sync_up(stage_latest, "latest")

        # 2. history entry when annotations, runs or settings changed
        history_entry = None
        stats = label_stats(root)
        if live_changed or first_run:
            stage_hist = scratch_path / "history" / stamp
            labels = [p for p in manifest if p.startswith("labels/")]
            changed_runs = [p for p in live_changed if p.startswith(("runs/",)) and p in manifest]
            _link_tree(root, [*labels, *changed_runs, *(p for p in live_changed if p in LIVE_FILES and p in manifest)],
                       stage_hist)
            shrank = [u for u, s in stats.items()
                      if u in prev_stats and s["label_lines"] < prev_stats[u]["label_lines"]]
            (stage_hist / "CHANGES.json").write_text(json.dumps({
                "backup_utc": stamp, "first_backup": first_run,
                "label_stats": stats, "label_stats_before": prev_stats,
                "warnings": [f"label file shrank for {u}" for u in shrank],
                "changed_live_files": live_changed, "article_files_changed": sum(
                    1 for p in [*changes["added"], *changes["modified"]] if p.startswith("articles/")),
                "removed_from_source": changes["removed"]}, indent=1) + "\n", "utf-8")
            hf.sync_up(stage_hist, f"history/{stamp}")
            history_entry = f"history/{stamp}"

        # 3. manifest + status (authoritative description of what the bucket holds)
        doc = {"backup_utc": stamp, "files": manifest, "label_stats": stats}
        (scratch_path / "latest.json").write_text(json.dumps(doc) + "\n", "utf-8")
        status = {"last_backup_utc": stamp, "history_entry": history_entry, "files": len(manifest),
                  "changed": {k: len(v) for k, v in changes.items()}, "label_stats": stats}
        (scratch_path / "status.json").write_text(json.dumps(status, indent=1) + "\n", "utf-8")
        hf.put(scratch_path / "latest.json", "manifest/latest.json")
        hf.put(scratch_path / "status.json", "manifest/status.json")
        baseline.write_text(json.dumps(doc) + "\n", "utf-8")
    return status
