"""Read-only data for the open dashboard. Everything here is gated by `labelling_open`.

While labelling is open the open view may only show corpus facts that do not depend on
model output or on any annotator's labels: article counts, labelling progress counts, and
per-country article counts drawn at collection-country centroids (not incident locations).
Map, agreement and model scores unlock when an admin ends labelling.
"""

from __future__ import annotations

import json
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from traffic_fusion.extraction.annotation_store import ArticleStore
from traffic_fusion.extraction.control import ControlStore
from traffic_fusion.extraction.geocode import GeocodeStore
from traffic_fusion.extraction.runs import RunManager
from traffic_fusion.extraction.schema import lonlat_from_string
from traffic_fusion.extraction.scoring import (
    annotation_stats,
    build_reference,
    model_metrics,
)

# Collection-country centroids for countries missing from configs/global_countries.toml
# (lon, lat, name). Approximate; used only for the "collection countries" map layer.
EXTRA_CENTROIDS = {
    "guatemala": (-90.23, 15.78, "Guatemala"), "bolivia": (-63.59, -16.29, "Bolivia"),
    "cambodia": (104.99, 12.57, "Cambodia"), "afghanistan": (67.71, 33.94, "Afghanistan"),
    "iran": (53.69, 32.43, "Iran"), "iraq": (43.68, 33.22, "Iraq"), "algeria": (1.66, 28.03, "Algeria"),
}


_VEHICLE_GROUP = {
    "bus": "bus", "truck": "truck", "covered_van": "truck", "pickup": "truck", "tractor": "truck",
    "car": "car", "microbus": "car", "van": "car", "ambulance": "car", "human_hauler": "car",
    "motorcycle": "two_wheeler", "rickshaw": "two_wheeler", "cng_autorickshaw": "two_wheeler",
    "battery_autorickshaw": "two_wheeler", "bicycle": "two_wheeler", "train": "train",
}


def vehicle_group(vehicles: list[str] | None) -> str:
    """Map style group of the first listed vehicle (the one described first or at fault comes first)."""
    if not vehicles:
        return "unknown"
    return _VEHICLE_GROUP.get(vehicles[0], "other")


class PublicData:
    def __init__(self, root: Path, control: ControlStore, store: ArticleStore,
                 runs: RunManager, geocoder: GeocodeStore) -> None:
        self.root, self.control, self.store = root, control, store
        self.runs, self.geocoder = runs, geocoder
        self._cache: dict[str, tuple[tuple[Any, ...], Any]] = {}

    def locked(self) -> bool:
        return self.control.settings().labelling_open

    def _signature(self) -> tuple[Any, ...]:
        files = [*self.store.labels_dir.glob("*.jsonl"), self.root / "matching" / "incidents.json", *[f for f in self.runs.runs_dir.glob("*/*.json") if not f.parent.name.startswith("_")],
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

    def grouping_summary(self) -> dict[str, Any]:
        """Aggregate results of the same-accident grouping benchmark (no article or pair identifiers)."""
        try:
            return json.loads((self.root / "matching" / "public_summary.json").read_text("utf-8"))  # type: ignore[no-any-return]
        except (OSError, json.JSONDecodeError):
            return {"available": False}

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
        centroids: dict[str, tuple[float, float, str]] = {}
        try:
            for row in tomllib.loads(path.read_text("utf-8")).get("countries", []):
                point = row["coverage_centroid"]
                centroids[str(row["name"]).casefold()] = (point["longitude"], point["latitude"], str(row["name"]))
        except (OSError, KeyError, tomllib.TOMLDecodeError):  # optional file: the map just shows fewer countries
            centroids = {}
        for key, value in EXTRA_CENTROIDS.items():
            centroids.setdefault(key, value)
        counts: Counter[str] = Counter()
        listed: dict[str, list[dict[str, str | None]]] = {}
        for article_id in self.store.article_ids():
            meta = self.store.meta(article_id)
            admin = meta.get("admin") or {}
            key = str(admin.get("country") or "").casefold()  # type: ignore[attr-defined]
            counts[key] += 1
            listed.setdefault(key, []).append({"id": article_id, "title": str(meta.get("title")),
                                               "publisher": str(meta.get("publisher"))})
        features = [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [centroids[k][0], centroids[k][1]]},
             "properties": {"country": centroids[k][2], "articles": n, "items": listed[k][:12],
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
            reference = build_reference(labels)
            rows = []
            for state in self.runs.list():
                config_dir = self.runs.runs_dir / state["config_id"]
                rows.append({
                    "config_id": state["config_id"], "spec": state["spec"],
                    "tokens": {"input": state["input_tokens"], "output": state["output_tokens"]},
                    "cost_usd": state["cost_usd"], "cost_known": state["cost_known"],
                    "metrics": model_metrics(config_dir, reference, self.store, labels),
                })
            return rows

        return self._cached("models", build)  # type: ignore[no-any-return]

    def sources(self) -> list[str]:
        grouped = ["grouped"] if (self.root / "matching" / "incidents.json").exists() else []
        return [*grouped, *[row["config_id"] for row in self.runs.list()]]

    def grouped_geojson(self) -> dict[str, Any]:
        """One marker per incident (an LLM-clustered group of articles) with a fused DeepSeek summary."""
        try:
            doc = json.loads((self.root / "matching" / "incidents.json").read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"type": "FeatureCollection", "features": [], "meta": {"source": "grouped", "records": 0, "mapped": 0, "verified": False}}
        features = []
        for inc in doc["incidents"]:
            geo, f = inc.get("geo"), inc["fusion"]
            if not geo:
                continue
            articles = []
            for a in inc["articles"]:
                m = self.store.meta(a)
                articles.append({"id": a, "title": m.get("title"), "publisher": m.get("publisher"), "url": m.get("url"),
                                 "published_at": m.get("published_at"), "language": m.get("language")})
            features.append({
                "type": "Feature", "geometry": {"type": "Point", "coordinates": [geo["longitude"], geo["latitude"]]},
                "properties": {
                    "kind": "incident", "incident_id": inc["incident_id"], "headline": f["headline"], "summary": f["summary"],
                    "when": f.get("when"), "place": f.get("place_query"), "killed": f.get("killed"), "injured": f.get("injured"),
                    "vehicles": f.get("vehicles"), "casualty_note": f.get("casualty_note"), "disagreements": f.get("source_disagreements"),
                    "killed_n": f.get("killed") or 0, "injured_n": f.get("injured") or 0,
                    "vehicle_main": vehicle_group(f.get("vehicles")),
                    "year": int(str(f["when"])[:4]) if f.get("when") and str(f["when"])[:4].isdigit() else None,
                    "n_articles": len(articles), "articles": articles, "granularity": geo["granularity"],
                    "uncertainty_radius_km": geo["uncertainty_radius_km"], "is_incident_location": True, "verified": False,
                    "location_method": f"OpenStreetMap place centroid ({geo['granularity']}, query level {geo.get('fallback_level')}); not a crash coordinate",
                    "fused_by": doc.get("model"), "grouping": doc.get("source")}})
        return {"type": "FeatureCollection", "features": features,
                "meta": {"source": "grouped", "records": len(doc["incidents"]), "mapped": len(features), "verified": False}}

    def incidents_geojson(self, source: str) -> dict[str, Any]:
        if source == "grouped":
            return self._cached("geo:grouped", self.grouped_geojson)  # type: ignore[no-any-return]

        def build() -> dict[str, Any]:
            records = self._run_records(source)
            features = []
            for rec in records:
                point = self._locate(rec)
                if point is None:
                    continue
                features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(point["lonlat"])},
                                 "properties": {**{k: rec[k] for k in rec if k != "coords"}, **point["props"],
                                                "killed_n": rec.get("fatalities") or 0}})
            return {"type": "FeatureCollection", "features": features,
                    "meta": {"source": source, "records": len(records), "mapped": len(features),
                             "verified": False}}

        return self._cached(f"geo:{source}", build)  # type: ignore[no-any-return]

    def geocode_queries(self) -> list[tuple[str, str | None]]:
        queries = []
        for rec in [r for s in self.sources() if s != "grouped" for r in self._run_records(s)]:
            if rec.get("location") and not rec.get("coords"):
                queries.append((rec["location"], rec.get("country")))
        return queries

    # article pages (text and images are always open; annotations and model output unlock) ----
    def article_list(self) -> list[dict[str, Any]]:
        unlocked = not self.locked()
        labels = self.store.all_latest() if unlocked else {}
        runs = [r["config_id"] for r in self.runs.list()] if unlocked else []
        rows = []
        for article_id in self.store.article_ids():
            meta = self.store.meta(article_id)
            row: dict[str, Any] = {"id": article_id, "title": meta.get("title"),
                                   "publisher": meta.get("publisher"), "language": meta.get("language"),
                                   "published_at": meta.get("published_at")}
            if unlocked:
                row["annotations"] = sum(1 for per_user in labels.values() if article_id in per_user)
                row["models_with_result"] = sum(
                    1 for c in runs if (self.runs.runs_dir / c / f"{article_id}.json").exists())
            rows.append(row)
        return rows

    def article_detail(self, article_id: str) -> dict[str, Any] | None:
        if article_id not in set(self.store.article_ids()):
            return None
        meta = self.store.meta(article_id)
        image_list: list[dict[str, Any]] = list(meta.get("images") or [])  # type: ignore[call-overload]
        detail: dict[str, Any] = {
            "id": article_id, "url": meta.get("url"), "title": meta.get("title"),
            "publisher": meta.get("publisher"), "published_at": meta.get("published_at"),
            "language": meta.get("language"), "markdown": self.store.markdown(article_id),
            "images": [{"image_id": f"{article_id}-{i + 1}", "alt": img.get("alt", ""),
                        "url": f"/api/x/public/articles/{article_id}/images/{i + 1}"}
                       for i, img in enumerate(image_list) if img.get("file")],
            "locked": self.locked(),
        }
        if detail["locked"]:
            return detail
        labels = self.store.all_latest()
        names = sorted(labels)
        # public pseudonyms: usernames are never exposed
        detail["annotators"] = [
            {"annotator": f"Annotator {chr(65 + i)}", "unusable": rec.unusable, "notes": rec.notes,
             "accidents": [a.wire() for a in rec.accidents],
             "images": [x.model_dump() for x in rec.images], "revision": rec.revision}
            for i, name in enumerate(names) if (rec := labels[name].get(article_id))
        ]
        models = []
        for state in self.runs.list():
            path = self.runs.runs_dir / state["config_id"] / f"{article_id}.json"
            if not path.exists():
                continue
            row = json.loads(path.read_text("utf-8"))
            models.append({"config_id": state["config_id"], "spec": state["spec"],
                           **{k: row.get(k) for k in (
                               "status", "error", "accidents", "images", "quality", "input_tokens",
                               "output_tokens", "latency_ms", "finish_reason", "model_returned",
                               "images_sent", "call_settings", "raw_text", "retries")}})
        detail["models"] = models
        return detail

    def public_image(self, article_id: str, index: int) -> tuple[Path, str] | None:
        if article_id not in set(self.store.article_ids()):
            return None
        images = list(self.store.meta(article_id).get("images") or [])  # type: ignore[call-overload]
        if not 1 <= index <= len(images):
            return None
        image = images[index - 1]
        name = str(image.get("file") or "")
        path = self.root / "articles" / article_id / "images" / name
        if not name or "/" in name or not path.is_file():
            return None
        return path, str(image.get("content_type"))

    # internals -------------------------------------------------------------------------
    def _article_props(self, article_id: str) -> dict[str, Any]:
        meta = self.store.meta(article_id)
        return {"incident_id": article_id, "title": meta.get("title"),
                "publisher": meta.get("publisher"), "source_url": meta.get("url")}

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
