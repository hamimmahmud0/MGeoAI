"""Render the paper's data tables (markdown) from numbers.json, error_analysis.json and grouping_results.json.

Every number in a table comes from these files, so the plain-language and journal versions cannot disagree.
Configuration labels: model, then input codes in brackets (T = article text, P = publication timestamp,
I = images), then the reasoning setting when it is not the provider default.
"""

from __future__ import annotations

from typing import Any

LABEL = {
    "deepseek": "DeepSeek [T]",
    "deepseek_date": "DeepSeek [TP]",
    "deepseek_off": "DeepSeek [TP], reasoning off",
    "qwen": "Qwen [TPI]",
    "lfm": "LFM [TP]",
    "lfm_think": "LFM [TP], reasoning on",
}
ERR_KEY = {"deepseek": "deepseek_T", "deepseek_date": "deepseek_TP", "deepseek_off": "deepseek_TP_off", "qwen": "qwen_TPI",
           "lfm": "lfm_TP", "lfm_think": "lfm_TP_on"}
FIELDS = [("fatalities", "Killed"), ("casualties", "Killed + injured"), ("vehicles", "Vehicles"), ("date", "Date"), ("country", "Country")]


def pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{digits}f}%"


def pci(entry: dict[str, Any]) -> str:
    lo, hi = entry["ci95"]
    return f"{pct(entry['value'])} [{lo * 100:.1f}, {hi * 100:.1f}]"


def md(header: list[str], rows: list[list[str]], widths: list[int] | None = None) -> str:
    widths = widths or [14] + [12] * (len(header) - 1)
    sep = "|" + "|".join((":" + "-" * (w - 1)) if i == 0 else (":" + "-" * (w - 2) + ":") for i, w in enumerate(widths)) + "|"
    out = ["| " + " | ".join(header) + " |", sep]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def active(n: dict[str, Any], order: list[str] | None = None) -> list[str]:
    order = order or list(LABEL)
    return [k for k in order if k in n["extraction"]]


def table_configs(n: dict[str, Any]) -> str:
    rows = [
        ["DeepSeek [T]", "DeepSeek API, model identifier `deepseek-flash` as returned by the API", "Article text", "On (provider default)", "Provider maximum", "20 Oct 2026"],
        ["DeepSeek [TP]", "same", "Text + publication timestamp", "On (provider default)", "Provider maximum", "8 Nov 2026"],
        ["DeepSeek [TP], reasoning off", "same", "Text + publication timestamp", "Off", "Provider maximum", "10 Nov 2026"],
        ["Qwen [TPI]", "Qwen3.8-27B, 4-bit (Q4) quantization; hosted by the authors behind an OpenAI-compatible endpoint", "Text + timestamp + up to 3 images", "Off", "8,192 tokens", "8--9 Nov 2026"],
        ["LFM [TP]", "LFM3-1.7B (1.7 billion parameters); hosted by the authors on two NVIDIA T4 GPUs behind an OpenAI-compatible endpoint", "Text + publication timestamp", "Off", "2,048 tokens", "10 Nov 2026"],
    ]
    if "lfm_think" in n["extraction"]:
        rows.append(["LFM [TP], reasoning on", "same", "Text + publication timestamp", "On", "16,384 tokens", "10 Nov 2026"])
    return md(["Label", "Model and access", "Input", "Reasoning", "Output limit", "Run date"], rows, [16, 30, 17, 11, 11, 11])


def table_reliability(n: dict[str, Any], e: dict[str, Any]) -> str:
    keys = [k for k in LABEL if k in n["runs"]]
    cause_names = {"schema": "invalid format", "vocabulary": "vehicle not in list", "transport": "network timeout", "no_accident_object": "no accident object",
                   "malformed_json": "malformed JSON", "truncated": "cut off at the output limit", "http_error": "network error", "other": "other"}
    rows: list[list[str]] = []
    rows.append(["Articles with a valid answer"] + [f"{n['runs'][k]['ok']} of {n['runs'][k]['articles']} ({pct(n['runs'][k]['ok'] / n['runs'][k]['articles'])})" for k in keys])
    rows.append(["Main causes of failure"] + [", ".join(f"{cause_names.get(c, c)} {v}" for c, v in sorted(e["failures"][ERR_KEY[k]]["by_cause"].items(), key=lambda x: -x[1])) or "none" for k in keys])
    rows.append(["Accident-flag recall (valid answers)"] + [pct(n["runs"][k]["flagged_accident"] / n["runs"][k]["ok"]) for k in keys])
    rows.append(["Same number of accidents as reference"] + [f"{n['accident_count_agreement'][k]['same_count']} of {n['accident_count_agreement'][k]['articles']}" for k in keys])
    rows.append(["Evidence quotes found word for word"] + [pct(n["runs"][k]["verbatim"] / n["runs"][k]["quotes"]) if n["runs"][k]["quotes"] else "n/a" for k in keys])
    rows.append(["Median seconds per article"] + [f"{n['runs'][k]['median_latency_s']:.1f}" for k in keys])
    rows.append(["Output tokens per valid article"] + [f"{n['runs'][k]['output_tokens'] / n['runs'][k]['ok']:,.0f}" for k in keys])
    return md(["Measure"] + [LABEL[k] for k in keys], rows, [22] + [14] * len(keys))


def table_fields(n: dict[str, Any]) -> str:
    keys = active(n)
    rows = [["Articles scored"] + [str(n["extraction"][k]["n"]) for k in keys]]
    for f, name in FIELDS:
        rows.append([f"{name} (exact match)"] + [pci(n["extraction"][k][f]) for k in keys])
        if f == "fatalities":
            rows.append(["Killed (mean absolute error, people)"] + [f"{n['extraction'][k]['fatalities_mae']:.2f}" for k in keys])
        if f == "vehicles":
            rows.append(["Vehicles (word overlap, Equation 3)"] + [f"{n['extraction'][k]['vehicles_jaccard']:.2f}" for k in keys])
    rows.append(["Location (exact match)"] + [pci(n["extraction"][k]["location"]) for k in keys])
    rows.append(["Location (word overlap, Equation 3)"] + [f"{n['extraction'][k]['location_word_overlap']:.2f}" for k in keys])
    return md(["Field (measure)"] + [LABEL[k] for k in keys], rows, [22] + [14] * len(keys))


def table_kappa(n: dict[str, Any]) -> str:
    keys = active(n)
    k = n["kappa"]
    rows = []
    for f, name in (("fatalities", "Killed"), ("casualties", "Killed + injured"), ("country", "Country")):
        rows.append([name] + [f"{k[f][c]:.2f}" if k[f].get(c) is not None else "n/a" for c in keys])
    rows.append(["Vehicle types (mean of 5)"] + [f"{k['vehicle_types_mean'][c]:.2f}" if c in k["vehicle_types_mean"] else "n/a" for c in keys])
    return md(["Field"] + [LABEL[c] for c in keys], rows, [22] + [14] * len(keys))


def table_pairs(n: dict[str, Any]) -> str:
    d = n["paired_differences"]
    cols = [("Publication timestamp\nDeepSeek [TP] minus [T]", "deepseek_date-deepseek"), ("Reasoning off\nDeepSeek [TP] off minus on", "deepseek_off-deepseek_date"),
            ("Model\nQwen [TPI] minus DeepSeek [TP]", "qwen-deepseek_date"), ("Model size\nLFM [TP] minus DeepSeek [TP]", "lfm-deepseek_date")]
    cols = [(h, k) for h, k in cols if f"{k}:fatalities" in d]
    rows = []
    for f, name in FIELDS:
        row = [name]
        for _, k in cols:
            v = d[f"{k}:{f}"]
            lo, hi = v["ci95"]
            cell = f"{v['diff'] * 100:+.1f} [{lo * 100:.1f}, {hi * 100:.1f}]"
            row.append(f"**{cell}**" if (lo > 0 or hi < 0) else cell)
        rows.append(row)
    rows.append(["Articles compared"] + [str(d[f"{k}:fatalities"].get("articles", n["common_articles"])) for _, k in cols])
    return md(["Field"] + [h.replace("\n", ": ") for h, _ in cols], rows, [16] + [20] * len(cols))


def table_subsets(n: dict[str, Any]) -> str:
    rows = []
    for label, key in (("Bangladesh", "region=bangladesh"), ("International", "region=international"), ("Bengali", "language=bn"), ("English", "language=en")):
        for run in ("deepseek_date", "qwen"):
            v = n["extraction_by_subset"][key][run]
            rows.append([label if run == "deepseek_date" else "", LABEL[run], str(v["articles"])] + [pct(v[f]) for f, _ in FIELDS if f != "casualties"][:2]
                        + [pct(v["casualties"])] + [pct(v["date"]), pct(v["country"])])
    return md(["Subset", "Configuration", "N", "Killed", "Vehicles", "Killed + inj.", "Date", "Country"], rows, [14, 16, 6, 10, 10, 11, 10, 10])


def table_images(n: dict[str, Any]) -> str:
    i = n["images"]
    rows = [["Articles with at least one image", f"{i['articles_with_images']} of 244"], ["Images saved", str(i["images_saved"])],
            ["Images analyzed by Qwen [TPI]", str(i["images_analysed_by_qwen"])], ["Images labeled by the reference annotator", str(i["images_labelled_by_reference_annotator"])],
            ["Images labeled by both", str(i["compared"])], ["Agreement on \"shows the accident\"", f"{i['agree']} of {i['compared']} ({pct(i['agreement'])})"],
            ["Annotator says \"shows the accident\"", f"{i['human_says_accident']} of {i['compared']} ({pct(i['human_says_accident'] / i['compared'])})"],
            ["Precision / recall of Qwen's \"shows the accident\"", f"{pct(i['tp'] / (i['tp'] + i['fp']))} / {pct(i['tp'] / (i['tp'] + i['fn']))}"]]
    return md(["Measure", "Value"], rows, [40, 22])


def _tok(m: dict[str, Any]) -> str:
    return "none" if not m.get("tokens") else f"{m['tokens'] / 1e6:.2f}"


def table_grouping(g: dict[str, Any], meta: dict[str, Any]) -> str:
    methods = g["methods"]
    tok = meta.get("tokens", {})
    rows: list[list[str]] = []

    def add(label: str, key: str, tokens: str | None = None) -> None:
        if key not in methods:
            return
        m = methods[key]["estimated"]
        lo, hi = methods[key]["ci95"]["f1"]
        rows.append([label, pct(m["precision"]), pct(m["recall"]), f"{pct(m['f1'])} [{lo * 100:.1f}, {hi * 100:.1f}]", tokens or "none"])

    def pair_tokens(key: str) -> str:
        t = tok.get(key)
        return f"{t['in'] / 1e6:.2f} / {t['out'] / 1e6:.2f}" if t else "n/a"

    add("Pair judge, full articles", "pair-full", pair_tokens("pair-full"))
    add("Pair judge, fields (annotator + model)", "pair-fields-both", pair_tokens("pair-fields-both"))
    add("Pair judge, fields (annotator only)", "pair-fields-human", pair_tokens("pair-fields-human"))
    add("Pair judge, fields (model only)", "pair-fields-model", pair_tokens("pair-fields-model"))
    add("Clustering, short cards (consensus of 3 runs)", "cluster-cards consensus", "0.25 / 0.05 (all 3 runs)")
    add("Clustering, full text (consensus of 3 runs)", "cluster-full consensus", "0.51 / 0.07 (all 3 runs)")
    for key in methods:
        if "[" in key and key.startswith("pair-"):
            model = key[key.index("[") + 1:key.index("]")]
            add(f"{key.split(' [')[0].replace('pair-fields-both', 'Pair judge, fields (annotator + model)').replace('pair-full', 'Pair judge, full articles')} -- {_pretty(model)}", key)
        if "[" in key and key.startswith("cluster-") and key.endswith("consensus"):
            add(f"Clustering, {'short cards' if 'cards' in key else 'full text'} -- {_pretty(key[key.index('[') + 1:key.index(']')])}", key)
    add("Embedding similarity, multilingual E5 (threshold from other folds)", "baseline embeddings multilingual-e5-base (threshold learned on other folds)")
    add("Embedding similarity, LaBSE (threshold from other folds)", "baseline embeddings LaBSE (threshold learned on other folds)")
    add("Rule on extracted fields", "baseline fields rule")
    add("Word similarity (TF-IDF, threshold tuned on the sample)", "baseline tf-idf (oracle threshold)")
    return md(["Method", "Precision", "Recall", "F1 [95% interval]", "Tokens read / written (millions)"], rows, [34, 11, 11, 20, 18])


def _pretty(tag: str) -> str:
    tag = tag.split("@")[-1]
    return "LFM3-1.7B, reasoning on" if "thinking" in tag and "lfm" in tag else "LFM3-1.7B" if "lfm" in tag else tag


def table_errors(e: dict[str, Any], n: dict[str, Any]) -> str:
    keys = [k for k in active(n) if ERR_KEY[k] in e["killed_plus_injured_errors"]]
    rows: list[list[str]] = []

    def block(field: str, title: str, data: dict[str, Any], types: list[str]) -> None:
        for t in types:
            row = [title if t == types[0] else "", t]
            for k in keys:
                d = data[ERR_KEY[k]]
                row.append(str(d["by_type"].get(t, 0)))
            rows.append(row)
        rows.append(["", "Articles scored"] + [str(data[ERR_KEY[k]]["scored"]) for k in keys])

    block("cas", "Killed + injured", e["killed_plus_injured_errors"], ["model gave no total", "total equals the model's killed count (injured not added)",
                                                                       "model total higher", "model total lower", "reference gave no total"])
    block("date", "Date", e["date_errors"], ["model gave no date", "model returned the publication day", "off by one day", "off by more than one day"])
    block("veh", "Vehicles", e["vehicle_errors"], ["model list is a subset (vehicles left out)", "model list is a superset (extra vehicles)", "different vehicles"])
    short = {"total equals the model's killed count (injured not added)": "total equals killed count (injured not added)"}
    rows = [[r[0], short.get(r[1], r[1])] + r[2:] for r in rows]
    return md(["Field", "Type of error (articles)"] + [LABEL[k] for k in keys], rows, [14, 34] + [13] * len(keys))
