"""Build both Word versions of the paper.

paper.md          plain-language revision      -> MGeoAI_ASCE_Proceedings_revised.docx
paper_journal.md  journal-style revision       -> MGeoAI_ASCE_Proceedings_revised_journal.docx
The journal version reuses the tables and figures of the plain version, so numbers cannot drift apart.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import tables as T

HERE = Path(__file__).parent
DATA = HERE / "data"
CAPTIONS = {
    3: "Model configurations evaluated. T = article text, P = publication timestamp, I = images. All runs use temperature 0 and the same prompt.",
    4: "Reliability of the model configurations.",
    5: "Agreement with the reference annotation, with 95% bootstrap intervals.",
    6: "Agreement beyond chance (Cohen's kappa) with the reference annotation.",
    7: "Paired differences in exact match, in percentage points, with paired 95% bootstrap intervals (bold: the interval excludes zero).",
    8: "Exact match by region and language.",
    9: "Image coverage and agreement between Qwen [TPI] and the annotator.",
    10: "Same-accident identification, re-weighted to all 29,646 pairs.",
    11: "Types of error by field, in number of articles.",
}


def load() -> dict[str, dict]:
    def j(name: str) -> dict:
        path = DATA / name
        return json.loads(path.read_text("utf-8")) if path.exists() else {}
    return {"n": j("numbers.json"), "e": j("error_analysis.json"), "g": j("grouping_results.json"), "m": j("grouping_meta.json")}


def render_table(number: int, d: dict[str, dict]) -> str:
    n, e, g, m = d["n"], d["e"], d["g"], d["m"]
    body = {3: lambda: T.table_configs(n), 4: lambda: T.table_reliability(n, e), 5: lambda: T.table_fields(n), 6: lambda: T.table_kappa(n),
            7: lambda: T.table_pairs(n), 8: lambda: T.table_subsets(n), 9: lambda: T.table_images(n), 10: lambda: T.table_grouping(g, m),
            11: lambda: T.table_errors(e, n)}[number]()
    return f": **Table {number}. {CAPTIONS[number]}**\n\n{body}"


def values(d: dict[str, dict]) -> dict[str, str]:
    """Named numbers used in the prose as {{name}}; resolved from the data files so the text cannot go stale."""
    n, e = d["n"], d["e"]
    v: dict[str, str] = {}
    for key, run in n.get("runs", {}).items():
        v[f"runs.{key}.okpct"] = T.pct(run["ok"] / run["articles"])
        v[f"runs.{key}.ok"] = str(run["ok"])
        v[f"runs.{key}.articles"] = str(run["articles"])
        v[f"runs.{key}.median_latency_s"] = f"{run['median_latency_s']:.1f}"
    for key, ex in n.get("extraction", {}).items():
        v[f"{key}.n"] = str(ex["n"])
        for f, name in (("fatalities", "killed"), ("casualties", "cas"), ("vehicles", "veh"), ("date", "date"), ("country", "country")):
            v[f"{key}.{name}"] = T.pct(ex[f]["value"])
    for key, ee in e.get("end_to_end", {}).items():
        for f, name in (("fatalities", "e2e_killed"), ("casualities", "e2e_cas"), ("date", "e2e_date"), ("country", "e2e_country")):
            v[f"{key}.{name}"] = T.pct(ee[f])
    # short aliases used in the prose
    for alias, key, ekey in (("lfm", "lfm", "lfm_TP"), ("ds", "deepseek_date", "deepseek_TP")):
        for name in ("n", "killed", "cas", "veh", "date", "country"):
            if f"{key}.{name}" in v:
                v[f"{alias}.{name}"] = v[f"{key}.{name}"]
        for name in ("e2e_killed", "e2e_cas", "e2e_date", "e2e_country"):
            if f"{ekey}.{name}" in v:
                v[f"{alias}.{name}"] = v[f"{ekey}.{name}"]
    return v


def fill_values(text: str, v: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1).split("|")[0]
        if key not in v:
            raise SystemExit(f"unknown value {{{{{m.group(1)}}}}}")
        return v[key]
    return re.sub(r"\{\{([^}]+)\}\}", sub, text)
REFS = [
    ("AlDhanhani", None),
    ("Ali", None),
    ("Amoros", '''Amoros, Emmanuelle, Jean-Louis Martin, and Bernard Laumon. 2006. "Under-Reporting of Road Crash Casualties in France." *Accident Analysis & Prevention* 38 (4): 627--35. <https://doi.org/10.1016/j.aap.2005.11.006>.'''),
    ("Bhattacharjee", '''Bhattacharjee, Abhik, Tahmid Hasan, Wasi Uddin Ahmad, Kazi Samin Mubasshir, Md Saiful Islam, Anindya Iqbal, M. Sohel Rahman, and Rifat Shahriyar. 2022. "BanglaBERT: Language Model Pretraining and Benchmarks for Low-Resource Language Understanding Evaluation in Bangla." In *Findings of the Association for Computational Linguistics: NAACL 2022*, 1318--27. Association for Computational Linguistics. <https://doi.org/10.18653/v1/2022.findings-naacl.98>.'''),
    ("Bhuiyan", '''Bhuiyan, Hanif, Jinat Ara, Khan Md. Hasib, Md Imran Hossain Sourav, Faria Benta Karim, Cecilia Sik-Lanyi, Guido Governatori, Andry Rakotonirainy, and Shamsunnahar Yasmin. 2022. "Crash Severity Analysis and Risk Factors Identification Based on an Alternate Data Source: A Case Study of Developing Country." *Scientific Reports* 12: 21243. <https://doi.org/10.1038/s41598-022-25361-5>.'''),
    ("Chowdhury", '''Chowdhury, Md Thamed Bin Zaman, Md. Ridwanul Islam, and Moazzem Hossain. 2024. "Durghotona GPT: A Web Scraping and Large Language Model Based Framework to Generate Road Accident Dataset Automatically in Bangladesh." In *2024 27th International Conference on Computer and Information Technology (ICCIT)*, 50--55. IEEE. <https://doi.org/10.1109/ICCIT64611.2024.11021969>.'''),
    ("Feng", '''Feng, Fangxiaoyu, Yinfei Yang, Daniel Cer, Naveen Arivazhagan, and Wei Wang. 2022. "Language-Agnostic BERT Sentence Embedding." In *Proceedings of the 60th Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)*, 878--91. Association for Computational Linguistics. <https://doi.org/10.18653/v1/2022.acl-long.62>.'''),
    ("Gao", None), ("Grigorev", None), ("Gu", None),
    ("Juillard", '''Juillard, Catherine, Marquise Kouo Ngamby, Martin Ekeke Monono, Georges Alain Etoundi Mballa, Rochelle A. Dicker, Kent A. Stevens, and Adnan A. Hyder. 2017. "Exploring Data Sources for Road Traffic Injury in Cameroon: Collection and Completeness of Police Records, Newspaper Reports, and a Hospital Trauma Registry." *Surgery* 162 (6): S24--31. <https://doi.org/10.1016/j.surg.2017.01.025>.'''),
    ("Leban", None), ("Li", None), ("Mahmud", None),
    ("Mumtarin", '''Mumtarin, Maroa, Md Samiullah Chowdhury, and Jonathan Wood. 2023. "Large Language Models in Analyzing Crash Narratives: A Comparative Study of ChatGPT, BARD and GPT-4." arXiv preprint arXiv:2308.13563. <https://arxiv.org/abs/2308.13563>.'''),
    ("Nath", None), ("OpenStreetMap", None),
    ("Reimers", '''Reimers, Nils, and Iryna Gurevych. 2019. "Sentence-BERT: Sentence Embeddings Using Siamese BERT-Networks." In *Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing and the 9th International Joint Conference on Natural Language Processing (EMNLP-IJCNLP)*, 3982--92. Association for Computational Linguistics. <https://doi.org/10.18653/v1/D19-1410>.'''),
    ("Schwitter", None),
    ("Wandelt", '''Wandelt, Sebastian, Changhong Zheng, Shuang Wang, Yucheng Liu, and Xiaoqian Sun. 2024. "Large Language Models for Intelligent Transportation: A Review of the State of the Art and Challenges." *Applied Sciences* 14 (17): 7455. <https://doi.org/10.3390/app14177455>.'''),
    ("Wang", '''Wang, Liang, Nan Yang, Xiaolong Huang, Linjun Yang, Rangan Majumder, and Furu Wei. 2024. "Multilingual E5 Text Embeddings: A Technical Report." arXiv preprint arXiv:2402.05672. <https://arxiv.org/abs/2402.05672>.'''),
    ("Watson", '''Watson, Angela, Barry Watson, and Kirsten Vallmuur. 2015. "Estimating Under-Reporting of Road Crash Injuries to Police Using Multiple Linked Data Collections." *Accident Analysis & Prevention* 83: 18--25. <https://doi.org/10.1016/j.aap.2015.06.011>.'''),
    ("World", None), ("Xu", None), ("Zhang", None),
    ("Zhen", '''Zhen, Hao, Yucheng Shi, Yongcan Huang, Jidong J. Yang, and Ninghao Liu. 2024. "Leveraging Large Language Models with Chain-of-Thought and Prompt Engineering for Traffic Crash Severity Analysis and Inference." *Computers* 13 (9): 232. <https://doi.org/10.3390/computers13090232>.'''),
]


def split_refs(text: str) -> tuple[str, dict[str, str]]:
    head, _, body = text.partition("**REFERENCES**")
    entries = [e.strip() for e in body.strip().split("\n\n") if e.strip()]
    return head, {e.split(",")[0].split(" ")[0]: e for e in entries}


def merged_refs(existing: dict[str, str]) -> str:
    out = []
    for key, new in REFS:
        entry = new or existing.get(key)
        if entry is None:
            raise SystemExit(f"missing reference {key}")
        out.append(entry)
    return "\n\n".join(out) + "\n"


def blocks(v1: str) -> tuple[dict[int, str], dict[int, str]]:
    tables, figures = {}, {}
    lines = v1.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r": \*\*Table (\d+)\.", line)
        if m:
            j = i + 2
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            tables[int(m.group(1))] = "\n".join(lines[i:j])
        m = re.match(r"!\[Figure (\d+)\.", line)
        if m:
            figures[int(m.group(1))] = line
    return tables, figures


def fill(text: str, tables: dict[int, str], figures: dict[int, str]) -> str:
    out = []
    for line in text.splitlines():
        m = re.fullmatch(r"@@(T|FIG)(\d+)@@", line.strip())
        if m:
            out.append((tables if m.group(1) == "T" else figures)[int(m.group(2))])
            out.append("")
        else:
            out.append(line)
    text = "\n".join(out)
    text = re.sub(r"@@T(\d+)@@", r"Table \1", text)
    return re.sub(r"@@FIG(\d+)@@", r"Figure \1", text)


def pandoc(src: Path, dst: Path) -> None:
    subprocess.run(["pandoc", str(src), "-f", "markdown+tex_math_dollars", "-o", str(dst),
                    f"--reference-doc={HERE / 'MGeoAI_ASCE_Proceedings_pre_revision.docx'}", f"--resource-path={HERE}"], check=True)


def main() -> None:
    d = load()
    vals = values(d)
    v1_path = HERE / "paper.md"
    v1 = v1_path.read_text("utf-8")
    head, existing = split_refs(v1)
    refs = merged_refs(existing)
    v1 = head + "**REFERENCES**\n\n" + refs
    for name, marker in (("v1", "@@LFMREASON@@"), ("v1", "@@LFMREASON2@@"), ("v1", "@@LFMGROUP@@")):
        f = HERE / f"extra_{name}_{marker.strip('@')}.md"
        v1 = v1.replace(marker, f.read_text("utf-8").strip() if f.exists() else "")
    # tables 3..11 are rendered from data; 1 and 2 stay as written
    tables = {i: render_table(i, d) for i in CAPTIONS}
    tables_static = {int(m.group(1)): None for m in re.finditer(r"@@T(\d+)@@", v1)}
    v1_filled = re.sub(r"^@@T(\d+)@@$", lambda m: tables[int(m.group(1))], v1, flags=re.M)
    v1_filled = fill_values(v1_filled, vals)
    (HERE / "_v1_build.md").write_text(v1_filled, "utf-8")
    pandoc(HERE / "_v1_build.md", HERE / "MGeoAI_ASCE_Proceedings_revised.docx")
    # journal version: same tables and figures, different prose
    static_tables, figures = blocks(v1_filled)
    all_tables = {**static_tables, **tables}
    v2 = (HERE / "paper_journal.md").read_text("utf-8").replace("@@REFERENCES@@", refs)
    for marker in ("@@LFMREASON@@", "@@LFMREASON2@@", "@@LFMGROUP@@"):
        f = HERE / f"extra_journal_{marker.strip('@')}.md"
        v2 = v2.replace(marker, f.read_text("utf-8").strip() if f.exists() else "")
    v2 = fill_values(fill(v2, all_tables, figures), vals)
    (HERE / "_v2_build.md").write_text(v2, "utf-8")
    pandoc(HERE / "_v2_build.md", HERE / "MGeoAI_ASCE_Proceedings_revised_journal.docx")
    print("built both")


if __name__ == "__main__":
    main()
