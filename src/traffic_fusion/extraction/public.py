"""Read-only data for the open dashboard. Everything here is gated by `labelling_open`.

While labelling is open the open view may only show corpus facts that do not depend on
model output or on any annotator's labels: article counts, labelling progress counts, and
per-country article counts drawn at collection-country centroids (not incident locations).
Map, agreement and model scores unlock when an admin ends labelling.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from traffic_fusion.corpus.discovery import load_country_profiles
from traffic_fusion.extraction.annotation_store import ArticleStore
from traffic_fusion.extraction.control import ControlStore
from traffic_fusion.extraction.geocode import GeocodeStore
from traffic_fusion.extraction.runs import RunManager
from traffic_fusion.extraction.schema import lonlat_from_string
from traffic_fusion.extraction.scoring import (
    UNRESOLVED,
    annotation_stats,
    build_gold,
    model_metrics,
)

# Collection-country centroids for countries missing from configs/global_countries.toml
# (lon, lat, name). Approximate; used only for the "collection countries" map layer.
EXTRA_CENTROIDS = {
    "guatemala": (-90.23, 15.78, "Guatemala"), "bolivia": (-63.59, -16.29, "Bolivia"),
    "cambodia": (104.99, 12.57, "Cambodia"), "afghanistan": (67.71, 33.94, "Afghanistan"),
    "iran": (53.69, 32.43, "Iran"), "iraq": (43.68, 33.22, "Iraq"), "algeria": (1.66, 28.03, "Algeria"),
}


class PublicData:
    def __init__(self, root: Path, control: ControlStore, store: ArticleStore,
                 runs: RunManager, geocoder: GeocodeStore) -> None:
        self.root, self.control, self.store = root, control, store
        self.runs, self.geocoder = runs, geocoder
        self._cache: dict[str, tuple[tuple[Any, ...], Any]] = {}

    def locked(self) -> bool:
        return self.control.settings().labelling_open

    def _signature(self) -> tuple[Any, ...]:
        files = [*self.store.labels_dir.glob("*.jsonl"), *self.runs.runs_dir.glob("*/*.json"),
                 self.geocoder.path, self.control.path]
        sig = []
        for path in sorted(files):
            try:
                stat = path.stat()
                sig.append((str(path), stat.st_mtime_ns, stat.st_size))
            except OSError:
                continue
        return tuple(sig)

    def _cached(self, key: str, build: Any) -> Any:
        signature = self._signature()
        hit = self._cache.get(key)
        if hit and hit[0] == signature:
            return hit[1]
        value = build()
        self._cache[key] = (signature, value)
        return value

    # always available ----------------------------------------------------------------
    def overview(self) -> dict[str, Any]:
        ids = self.store.article_ids()
        publishers: Counter[str] = Counter()
        languages: Counter[str] = Counter()
        images = with_images = 0
        for article_id in ids:
            meta = self.store.meta(article_id)
            publishers[str(meta.get("publisher"))] += 1
            languages[str(meta.get("language") or "unknown")] += 1
            image_list: list[dict[str, Any]] = list(meta.get("images") or [])  # type: ignore[call-overload]
            saved = sum(1 for i in image_list if i.get("file"))
            images += saved
            with_images += 1 if saved else 0
        labels = self.store.all_latest()
        per_article = Counter(a for recs in labels.values() for a in recs)
        return {
            "labelling_open": self.locked(),
            "articles": len(ids), "images": images, "articles_with_images": with_images,
            "top_publishers": publishers.most_common(12), "languages": languages.most_common(8),
            "labelling": {
                "annotators": len(labels),
                "articles_with_1plus_labels": len(per_article),
                "articles_with_3plus_labels": sum(v >= 3 for v in per_article.values()),
                "labels_submitted": sum(len(r) for r in labels.values()),
            },
        }

    def coverage_geojson(self) -> dict[str, Any]:
        """Per-country article counts at collection-country centroids (not incidents)."""
        path = Path(__file__).resolve().parents[3] / "configs" / "global_countries.toml"
        centroids = {}
        try:
            for profile in load_country_profiles(path).values():
                centroids[profile.name.casefold()] = (
                    profile.coverage_longitude, profile.coverage_latitude, profile.name)
        except Exception:  # noqa: BLE001 - optional config; map just stays empty
            centroids = {}
        for key, value in EXTRA_CENTROIDS.items():
            centroids.setdefault(key, value)
        counts: Counter[str] = Counter()
        for article_id in self.store.article_ids():
            admin = self.store.meta(article_id).get("admin") or {}
            counts[str(admin.get("country") or "").casefold()] += 1  # type: ignore[attr-defined]
        features = [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [centroids[k][0], centroids[k][1]]},
             "properties": {"country": centroids[k][2], "articles": n,
                            "is_incident_location": False,
                            "note": "Collection-country centroid; not an incident location."}}
            for k, n in counts.items() if k in centroids
        ]
        return {"type": "FeatureCollection", "features": features}

    # unlocked only ---------------------------------------------------------------------
    def annotation_scores(self) -> dict[str, Any]:
        return self._cached("annotation", lambda: annotation_stats(self.store))  # type: ignore[no-any-return]

    def model_scores(self) -> list[dict[str, Any]]:
        def build() -> list[dict[str, Any]]:
            labels = self.store.all_latest()
            gold = build_gold(labels)
            rows = []
            for state in self.runs.list():
                config_dir = self.runs.runs_dir / state["config_id"]
                rows.append({
                    "config_id": state["config_id"], "spec": state["spec"],
                    "tokens": {"input": state["input_tokens"], "output": state["output_tokens"]},
                    "cost_usd": state["cost_usd"], "cost_known": state["cost_known"],
                    "metrics": model_metrics(config_dir, gold, self.store, labels),
                })
            return rows

        return self._cached("models", build)  # type: ignore[no-any-return]

    def sources(self) -> list[str]:
        return ["gold", *[row["config_id"] for row in self.runs.list()]]

    def incidents_geojson(self, source: str) -> dict[str, Any]:
        def build() -> dict[str, Any]:
            records = self._gold_records() if source == "gold" else self._run_records(source)
            features = []
            for rec in records:
                point = self._locate(rec)
                if point is None:
                    continue
                features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(point["lonlat"])},
                                 "properties": {**{k: rec[k] for k in rec if k != "coords"}, **point["props"]}})
            return {"type": "FeatureCollection", "features": features,
                    "meta": {"source": source, "records": len(records), "mapped": len(features),
                             "verified": source == "gold"}}

        return self._cached(f"geo:{source}", build)  # type: ignore[no-any-return]

    def geocode_queries(self) -> list[tuple[str, str | None]]:
        queries = []
        for rec in [*self._gold_records(), *[r for s in self.sources()[1:] for r in self._run_records(s)]]:
            if rec.get("location") and not rec.get("coords"):
                queries.append((rec["location"], rec.get("country")))
        return queries

    # internals -------------------------------------------------------------------------
    def _article_props(self, article_id: str) -> dict[str, Any]:
        meta = self.store.meta(article_id)
        return {"incident_id": article_id, "title": meta.get("title"),
                "publisher": meta.get("publisher"), "source_url": meta.get("url")}

    def _gold_records(self) -> list[dict[str, Any]]:
        out = []
        for article_id, g in build_gold(self.store.all_latest()).items():
            if not (g.get("usable") and g.get("accident") is True and g.get("accident_count") == 1):
                continue
            raw = {k: json.loads(v) for k, v in (g.get("raw") or {}).items()}
            fields = g["fields"]
            out.append({**self._article_props(article_id), "origin": "human_gold", "verified": True,
                        "fatalities": None if fields.get("fatalities") in (UNRESOLVED, None) else fields["fatalities"],
                        "casualities": None if fields.get("casualities") in (UNRESOLVED, None) else fields["casualities"],
                        "date": raw.get("date"), "location": raw.get("location"),
                        "country": raw.get("country"), "coords": raw.get("longitude and latitude")})
        return out

    def _run_records(self, config_id: str) -> list[dict[str, Any]]:
        out = []
        folder = self.runs.runs_dir / config_id
        for path in sorted(folder.glob("*.json")):
            if path.name == "run.json":
                continue
            row = json.loads(path.read_text("utf-8"))
            if row.get("status") != "ok":
                continue
            for accident in row["accidents"]:
                if accident["accident"]:
                    out.append({**self._article_props(row["article_id"]), "origin": f"model:{config_id}",
                                "verified": False, "fatalities": accident["fatalities"],
                                "casualities": accident["casualities"], "date": accident["date"],
                                "location": accident["location"], "country": accident["country"],
                                "coords": accident["longitude and latitude"]})
        return out

    def _locate(self, rec: dict[str, Any]) -> dict[str, Any] | None:
        if rec.get("coords"):
            lonlat = lonlat_from_string(rec["coords"])
            if lonlat:
                return {"lonlat": lonlat, "props": {"granularity": "point", "uncertainty_radius_km": 0.2,
                        "is_incident_location": True, "location_method": "stated in article or by annotator"}}
        hit = self.geocoder.lookup(rec.get("location"), rec.get("country"))
        if hit:
            return {"lonlat": (hit["longitude"], hit["latitude"]),
                    "props": {"granularity": hit["granularity"],
                              "uncertainty_radius_km": hit["uncertainty_radius_km"],
                              "is_incident_location": True,
                              "location_method": "geocoded place centroid (OpenStreetMap Nominatim); not a crash coordinate"}}
        return None
