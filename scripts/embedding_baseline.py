"""Embedding-similarity baseline for the same-accident benchmark.

Embeds each article (title + first 1,500 characters, the same text the TF-IDF baseline reads) with multilingual
sentence-embedding models and stores the cosine similarity of every sampled pair in
`<root>/matching/embedding_baseline.json`. Needs `pip install sentence-transformers` (not a project dependency).

Usage: python scripts/embedding_baseline.py <data root>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

MODELS = {"LaBSE": ("sentence-transformers/LaBSE", ""), "multilingual-e5-base": ("intfloat/multilingual-e5-base", "query: ")}


def main(root: Path) -> None:
    ids = sorted(p.name for p in (root / "articles").iterdir() if (p / "meta.json").exists())
    texts = []
    for a in ids:
        meta = json.loads((root / "articles" / a / "meta.json").read_text("utf-8"))
        body = (root / "articles" / a / "article.md").read_text("utf-8")
        texts.append(f"{meta['title']} {body[:1500]}")
    pairs = json.loads((root / "matching" / "pairs.json").read_text("utf-8"))["pairs"]
    index = {a: i for i, a in enumerate(ids)}
    out: dict[str, object] = {"text": "title + first 1500 characters of the article", "models": {}}
    for name, (repo, prefix) in MODELS.items():
        model = SentenceTransformer(repo, device="cpu")
        vectors = model.encode([prefix + t for t in texts], batch_size=16, normalize_embeddings=True, show_progress_bar=False)
        sims = {p["pair_id"]: round(float(np.dot(vectors[index[p["a"]]], vectors[index[p["b"]]])), 4) for p in pairs}
        out["models"][name] = {"repo": repo, "cosine": sims}  # type: ignore[index]
        print(name, "done", flush=True)
    (root / "matching" / "embedding_baseline.json").write_text(json.dumps(out, indent=1) + "\n", "utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
