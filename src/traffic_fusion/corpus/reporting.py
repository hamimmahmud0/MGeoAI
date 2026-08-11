from __future__ import annotations

from traffic_fusion.corpus.validation import ValidationReport


def render_validation_report(report: ValidationReport) -> str:
    status = "VALID" if report.valid else "INVALID"
    lines = [
        f"# Corpus validation: {report.corpus_id}",
        "",
        f"Status: **{status}**",
        "",
        "| Country | Accepted sources | Independent groups | Reviewed multi-source incidents |",
        "| --- | ---: | ---: | ---: |",
    ]
    for country in report.countries:
        lines.append(
            f"| {country.country_code} | {country.accepted_sources} | "
            f"{country.independent_groups} | {country.reviewed_shared_incidents} |"
        )
    lines.extend(["", "## Validation issues", ""])
    if report.issues:
        for issue in report.issues:
            location = f" ({issue.path})" if issue.path else ""
            lines.append(f"- `{issue.code}`{location}: {issue.message}")
    else:
        lines.append("- None.")
    return "\n".join(lines).rstrip() + "\n"
