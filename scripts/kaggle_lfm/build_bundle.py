"""Build the private Kaggle dataset used to run LFM3-1.7B inside notebooks (no tunnel, so no 100-second limit).

Contents: `root/` (a data root rebuilt from the PUBLIC dataset, so annotators are pseudonyms, plus the article text,
which is third-party and therefore only ever uploaded to a private dataset) and `code/` (the package).

Usage: python scripts/kaggle_lfm/build_bundle.py <public dataset folder> <local data root with articles/> <out dir>
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from traffic_fusion.extraction.reproduce import materialise

KEEP_RUN = "deepseek__deepseek-flash__markdown__txt__meta"  # supplies the model fields of the field-based pair judges


def main(dataset: Path, source_root: Path, out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    root = out / "root"
    materialise(dataset, root)
    for run in (root / "runs").iterdir():
        if run.name != KEEP_RUN:
            shutil.rmtree(run)
    for folder in (root / "matching").iterdir():
        if folder.is_dir():
            shutil.rmtree(folder)
    missing = 0
    for article in (root / "articles").iterdir():
        text = source_root / "articles" / article.name / "article.md"
        if text.exists():
            shutil.copy(text, article / "article.md")
        else:
            missing += 1
    here = Path(__file__).resolve().parents[2]
    code = out / "code"
    shutil.copytree(here / "src", code / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (code / "assets").mkdir(parents=True)
    shutil.copytree(here / "assets" / "mllm_prompts", code / "assets" / "mllm_prompts")
    shutil.copy(here / "pyproject.toml", code / "pyproject.toml")
    (code / "README.md").write_text("package for the notebook run\n", "utf-8")
    shutil.copytree(here / "configs", code / "configs", dirs_exist_ok=True) if (here / "configs").exists() else None
    print(f"bundle at {out}; articles without text: {missing}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]).expanduser(), Path(sys.argv[3]))
