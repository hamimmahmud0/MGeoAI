"""Figures for the paper. Usage: python writeups/make_figures.py <numbers.json> <reproduced-dir> <out-dir>"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

INK, MUTED = "#1b2733", "#5b6b7a"
BLUE, ORANGE, GREEN, GREY, PINK = "#1f5eff", "#e07b00", "#1a8f5a", "#9aa7b4", "#b8337a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK})


def box(ax, x, y, w, h, text, fc="#eef3fb", ec=BLUE, size=8.5, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=fc, ec=ec, lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, weight="bold" if bold else "normal", wrap=True)


def arrow(ax, a, b, color=MUTED, style="-|>", rad=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=11, lw=1.2, color=color, connectionstyle=f"arc3,rad={rad}"))


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return fig, ax


def fig_pipeline(out: Path) -> None:
    fig, ax = canvas(7.1, 2.7)
    box(ax, 0.05, 1.55, 1.1, 0.8, "Saved web page\n(HTML + images)", "#f4f4f4", GREY, size=7)
    box(ax, 1.45, 1.55, 1.35, 0.8, "Clean, convert to\nmarkdown, add the\npublish time", "#eef3fb", BLUE, size=7)
    box(ax, 3.1, 1.7, 1.3, 0.65, "LLM reads one\narticle at a time", "#fff3e0", ORANGE, size=8)
    box(ax, 3.1, 0.45, 1.3, 0.75, "People annotate\nthe same fields\n(blind)", "#e8f6ef", GREEN, size=8)
    box(ax, 4.7, 1.7, 1.2, 0.65, "Model record\n(JSON + quotes)", "#fff3e0", ORANGE, size=8)
    box(ax, 4.7, 0.5, 1.2, 0.65, "Reference\nannotation", "#e8f6ef", GREEN, size=8)
    box(ax, 6.2, 0.95, 0.85, 0.85, "Compare\nfield by\nfield", "#f6e9f1", PINK, size=8, bold=True)
    arrow(ax, (1.15, 1.95), (1.45, 1.95)); arrow(ax, (2.8, 2.0), (3.1, 2.0))
    arrow(ax, (0.6, 1.55), (3.1, 0.85), rad=0.12)
    arrow(ax, (4.4, 2.02), (4.7, 2.02)); arrow(ax, (4.4, 0.82), (4.7, 0.82))
    arrow(ax, (5.9, 2.0), (6.3, 1.65)); arrow(ax, (5.9, 0.85), (6.3, 1.1))
    ax.text(0.05, 2.6, "Every article goes down two paths. Neither path sees the other's answer.", fontsize=8.5, color=MUTED)
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")


def fig_methods(out: Path) -> None:
    fig, ax = canvas(6.6, 3.9)
    box(ax, 1.5, 3.35, 3.6, 0.42, "Do two articles report the same accident?", "#f6e9f1", PINK, bold=True)
    cols = [
        (0.0, "Pair judge (LLM)", ORANGE, "#fff3e0", ["Full articles", "Extracted fields only:\nannotator, model, or both"], "one pair at a time,\nasked in both orders"),
        (2.25, "Clustering (LLM)", BLUE, "#eef3fb", ["Short cards:\ntitle, lead, fields", "Full text\n(first 4,000 characters)"], "all 244 articles in one\nrequest, 3 shuffled runs"),
        (4.5, "No LLM baselines", GREY, "#f4f4f4", ["Text similarity:\nTF-IDF, LaBSE, E5", "Extracted-field rule:\ncountry, date, place"], "a similarity score and a\nthreshold, or a fixed rule"),
    ]
    for x, title, ec, fc, kids, note in cols:
        box(ax, x + 0.05, 2.35, 2.0, 0.55, title, fc, ec, bold=True)
        arrow(ax, (3.3, 3.35), (x + 1.05, 2.9))
        for i, kid in enumerate(kids):
            box(ax, x + 0.05, 1.45 - i * 0.78, 2.0, 0.62, kid, "white", ec, size=8)
        ax.text(x + 1.05, 0.12, note, ha="center", va="center", fontsize=7.8, color=MUTED)
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")


def fig_pairs(out: Path, pop: dict[str, int], sampled: dict[str, int]) -> None:
    order = [("positive", "Same accident"), ("hard_decoy", "Look-alike\naccident"), ("hard_near", "Same country,\nwithin 4 days"), ("hard_similar", "Most similar\nwording"), ("easy", "Random")]
    fig, ax = plt.subplots(figsize=(6.4, 2.7))
    y = range(len(order))[::-1]
    ax.barh([i + 0.2 for i in y], [pop[k] for k, _ in order], height=0.38, color=GREY, label="all possible pairs (29,646)")
    ax.barh([i - 0.2 for i in y], [sampled[k] for k, _ in order], height=0.38, color=BLUE, label="pairs we tested (973)")
    ax.set_xscale("log")
    ax.set_yticks(list(y)); ax.set_yticklabels([n for _, n in order])
    for i, (k, _) in zip(y, order):
        ax.text(pop[k] * 1.08, i + 0.2, f"{pop[k]:,}", va="center", fontsize=7.5, color=MUTED)
        ax.text(sampled[k] * 1.08, i - 0.2, f"{sampled[k]:,}", va="center", fontsize=7.5, color=BLUE)
    ax.set_xlabel("Number of article pairs (log scale)"); ax.set_xlim(60, 90000)
    ax.legend(frameon=False, loc="upper right", fontsize=8)
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")


def fig_extraction(out: Path, n: dict) -> None:
    fields = ["fatalities", "casualties", "vehicles", "date", "country"]
    labels = ["Killed", "Killed +\ninjured", "Vehicles", "Date", "Country"]
    series = [("DeepSeek [T]", "deepseek", GREY), ("DeepSeek [TP]", "deepseek_date", BLUE), ("DeepSeek [TP], reasoning off", "deepseek_off", "#7fa8ff"),
              ("Qwen [TPI]", "qwen", ORANGE), ("LFM [TP]", "lfm", GREEN), ("LFM [TP], reasoning on", "lfm_think", "#7fd1a8")]
    series = [x for x in series if x[1] in n["extraction"]]
    fig, ax = plt.subplots(figsize=(6.8, 3.2))
    w = 0.8 / len(series)
    for j, (name, key, color) in enumerate(series):
        e = n["extraction"][key]
        vals = [e[f]["value"] * 100 for f in fields]
        lo = [vals[i] - e[f]["ci95"][0] * 100 for i, f in enumerate(fields)]
        hi = [e[f]["ci95"][1] * 100 - vals[i] for i, f in enumerate(fields)]
        xs = [i + (j - (len(series) - 1) / 2) * w for i in range(len(fields))]
        ax.bar(xs, vals, w, color=color, label=f"{name} (n = {e['n']})", yerr=[lo, hi], error_kw={"lw": 0.8, "capsize": 1.5, "ecolor": INK})
    ax.set_xticks(range(len(fields))); ax.set_xticklabels(labels)
    ax.set_ylabel("Exact match with the reference (%)"); ax.set_ylim(0, 108)
    ax.legend(frameon=False, fontsize=7.2, loc="upper center", ncol=2, bbox_to_anchor=(0.5, -0.16))
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")


def fig_grouping(out: Path, results: dict, tokens: dict) -> None:
    rows = [("pair-full", "Pair judge, full articles", ORANGE), ("pair-fields-both", "Pair judge, fields (annotator + model)", ORANGE),
            ("pair-fields-human", "Pair judge, fields (annotator)", ORANGE), ("pair-fields-model", "Pair judge, fields (model)", ORANGE),
            ("cluster-cards consensus", "Clustering, short cards", BLUE), ("cluster-full consensus", "Clustering, full text", BLUE)]
    for key in results["methods"]:  # a second LLM, when its clustering runs exist
        if key.startswith("cluster-") and key.endswith("consensus") and "[" in key:
            variant = "short cards" if "cards" in key else "full text"
            model = key[key.index("[") + 1:key.index("]")].split("@")[-1].replace("openrouter-", "").replace("-free", "")
            rows.append((key, f"Clustering, {variant}, {model}", GREEN))
    rows += [("baseline embeddings multilingual-e5-base (threshold learned on other folds)", "Embedding similarity (multilingual-E5)", GREY),
             ("baseline embeddings LaBSE (threshold learned on other folds)", "Embedding similarity (LaBSE)", GREY),
             ("baseline fields rule", "Rule on extracted fields", GREY), ("baseline tf-idf (oracle threshold)", "Word similarity (TF-IDF)", GREY)]
    rows = [r for r in rows if r[0] in results["methods"]]
    fig, ax = plt.subplots(figsize=(6.6, 0.33 * len(rows) + 0.9))
    for i, (key, name, color) in enumerate(rows):
        y = len(rows) - 1 - i
        m = results["methods"][key]
        f1, (lo, hi) = m["estimated"]["f1"] * 100, [v * 100 for v in m["ci95"]["f1"]]
        ax.errorbar(f1, y, xerr=[[f1 - lo], [hi - f1]], fmt="o", color=color, ecolor=color, capsize=3, ms=6)
        ax.text(101.5, y, f"{f1:.1f}", va="center", fontsize=8)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([n for _, n, _ in rows][::-1])
    ax.set_xlim(0, 106); ax.set_xlabel("F1 score, re-weighted to all 29,646 pairs (%), 95% interval")
    ax.axvline(100, color=GREY, lw=0.6, ls=":")
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")


def main(numbers: Path, reproduced: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    n = json.loads(numbers.read_text("utf-8"))
    res = json.loads((reproduced / "grouping_results.json").read_text("utf-8"))
    sampled = {"positive": 232, "hard_decoy": 163, "hard_near": 128, "hard_similar": 300, "easy": 150}
    fig_pipeline(out / "fig1_pipeline.png")
    fig_methods(out / "fig2_methods.png")
    fig_pairs(out / "fig3_pairs.png", n["grouping_population"], sampled)
    fig_extraction(out / "fig4_extraction.png", n)
    fig_grouping(out / "fig5_grouping.png", res, {})
    print("figures:", sorted(p.name for p in out.iterdir()))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
