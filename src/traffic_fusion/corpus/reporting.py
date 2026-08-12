from __future__ import annotations

from collections import Counter

from bs4 import BeautifulSoup

from traffic_fusion.corpus.models import CorpusSource, SourceStatus
from traffic_fusion.corpus.store import CorpusStore
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


def render_news_source_catalog(store: CorpusStore) -> str:
    """Render every accepted news source with its two manual-verification links."""
    manifest = store.manifest()
    countries = {item.country_code: item for item in store.countries()}
    sources = [
        item
        for item in store.sources()
        if item.status == SourceStatus.ACCEPTED and item.traffic_incident
    ]
    sources.sort(key=lambda item: (item.country_code, item.corpus_source_id))
    publisher_count = len({item.publisher for item in sources})
    dependency_count = len({item.dependency_group for item in sources})
    language_count = len({language for item in sources for language in item.languages})
    discovery_hosts = Counter(
        _link_host(link.url)
        for source in sources
        for link in source.verification_links
        if link.rel == "manual"
    )
    discovery_summary = ", ".join(
        f"{host} ({count})" for host, count in sorted(discovery_hosts.items())
    )
    lines = [
        f"# News sources in {manifest.corpus_id}",
        "",
        (
            f"This catalog lists all **{len(sources)} accepted traffic-news sources** across "
            f"**{len(countries)} collection-country groups** in the versioned corpus. It "
            "provides direct publisher and discovery-record links for manual checking."
        ),
        "",
        "## Datasource details",
        "",
        f"- Corpus snapshot: `{manifest.corpus_id}`; created {manifest.created_at.isoformat()}.",
        f"- Distinct publisher labels: {publisher_count}.",
        f"- Distinct dependency/domain groups: {dependency_count}.",
        f"- Declared language tags: {language_count}.",
        f"- Discovery-link hosts: {discovery_summary}.",
        "- Stored payload: title, publisher metadata, canonical URL, publication time when "
        "available, and a short public-feed excerpt; full publisher articles are not copied.",
        "- Redistribution status: metadata-only for every source in this snapshot.",
        "- Review status: automated feed/link screening; not human verification of incident "
        "truth, event country, casualty totals, source independence, or continuing link access.",
        "- Country headings describe the collection/source bucket, not necessarily the country "
        "where the reported incident occurred.",
        "",
        "Links may change or disappear after the corpus snapshot. The source ID and committed "
        "payload hash preserve the identity of the collected record even when link rot occurs.",
        "",
    ]
    grouped: dict[str, list[CorpusSource]] = {}
    for source in sources:
        grouped.setdefault(source.country_code, []).append(source)
    for country_code, country_sources in sorted(grouped.items()):
        country = countries[country_code]
        lines.extend(
            [
                f"## {country.name} ({country_code})",
                "",
                "| Source ID | Published | Publisher | News article | Discovery record |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for source in country_sources:
            original = next(
                (item.url for item in source.verification_links if item.rel == "original"),
                source.canonical_url,
            )
            discovery = next(
                (item.url for item in source.verification_links if item.rel == "manual"),
                "",
            )
            title = _source_title(store, source)
            published = source.published_at.date().isoformat() if source.published_at else "Unknown"
            lines.append(
                f"| `{source.corpus_source_id}` | {published} | "
                f"{_table_text(source.publisher)} | "
                f"[{_table_text(title)}]({_markdown_url(original)}) | "
                f"{f'[Open discovery record]({_markdown_url(discovery)})' if discovery else '—'} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _source_title(store: CorpusStore, source: CorpusSource) -> str:
    artifact = next((item for item in source.artifacts if item.role == "html"), None)
    if artifact is None:
        return f"Traffic incident source {source.corpus_source_id}"
    document = store.artifact_path(source, artifact.path).read_text(
        encoding=artifact.encoding, errors="replace"
    )
    title = BeautifulSoup(document, "html.parser").title
    return title.get_text(" ", strip=True) if title else source.corpus_source_id


def _table_text(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")


def _markdown_url(value: str) -> str:
    return value.replace("(", "%28").replace(")", "%29")


def _link_host(value: str) -> str:
    from urllib.parse import urlsplit

    return (urlsplit(value).hostname or "unknown").removeprefix("www.")
