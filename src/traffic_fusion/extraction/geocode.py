"""Cached place geocoding via Nominatim (OpenStreetMap). Admin-triggered only.

Usage policy: at most 1 request per second, identifying User-Agent, results cached on disk
so each place is asked once. A geocoded point is the centroid of a *named place*; it is
never a crash coordinate. Each result keeps a granularity and an uncertainty radius
derived from the bounding box (AGENTS.md).
"""

from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path
from typing import Any

import httpx

UA = "MGeoAI-extraction/0.1 (academic research; https://github.com/hamimmahmud0/MGeoAI)"
URL = "https://nominatim.openstreetmap.org/search"
_GRAN = {
    "house": "point", "building": "point", "amenity": "point", "road": "road_segment",
    "highway": "road_segment", "motorway": "road_segment", "trunk": "road_segment",
    "suburb": "area", "neighbourhood": "area", "quarter": "area", "village": "area",
    "hamlet": "area", "locality": "area", "town": "city", "city": "city", "municipality": "city",
    "county": "district", "state_district": "district", "district": "district",
    "state": "district", "country": "country",
}


def cache_key(location: str, country: str | None) -> str:
    return f"{location.strip().casefold()}|{(country or '').strip().casefold()}"


def _radius_km(box: list[str]) -> float:
    south, north, west, east = (float(v) for v in box)
    lat = (south + north) / 2
    height = (north - south) * 111.32
    width = (east - west) * 111.32 * max(math.cos(math.radians(lat)), 0.2)
    return round(min(max(math.hypot(height, width) / 2, 0.3), 300.0), 2)


class GeocodeStore:
    def __init__(self, root: Path) -> None:
        self.path = root / "geocode_cache.json"
        self._lock = threading.Lock()
        self.progress: dict[str, Any] = {"running": False, "done": 0, "total": 0, "found": 0}

    def load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text("utf-8"))  # type: ignore[no-any-return]
        except (OSError, json.JSONDecodeError):
            return {}

    def lookup(self, location: str | None, country: str | None) -> dict[str, Any] | None:
        """A usable place: found, and more specific than a whole country (a country centroid is
        not a location for a crash)."""
        if not location:
            return None
        entry: dict[str, Any] | None = self.load().get(cache_key(location, country))
        if entry and entry.get("status") == "found" and entry.get("granularity") != "country":
            return entry
        return None

    def start(self, queries: list[tuple[str, str | None]]) -> bool:
        with self._lock:
            if self.progress["running"]:
                return False
            cache = self.load()
            todo = [q for q in dict.fromkeys(queries) if cache_key(*q) not in cache]
            self.progress = {"running": True, "done": 0, "total": len(todo), "found": 0}
        threading.Thread(target=self._run, args=(todo,), daemon=True).start()
        return True

    def _run(self, todo: list[tuple[str, str | None]]) -> None:
        try:
            with httpx.Client(timeout=20, headers={"User-Agent": UA}) as client:
                for location, country in todo:
                    entry = self._resolve(client, location, country)
                    cache = self.load()
                    cache[cache_key(location, country)] = entry
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self.path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), "utf-8")
                    self.progress["done"] += 1
                    self.progress["found"] += entry["status"] == "found"
                    time.sleep(1.1)
        finally:
            self.progress["running"] = False

    @staticmethod
    def variants(location: str, country: str | None) -> list[str]:
        """Queries from most to least specific: the full location, then with the leading (most
        specific) component dropped one at a time. A country-only query is never used (not useful)."""
        parts = [p.strip() for p in location.split(",") if p.strip()]
        out = []
        for i in range(len(parts)):
            rest = ", ".join(parts[i:])
            out.append(f"{rest}, {country}" if country and country.casefold() not in rest.casefold() else rest)
        return list(dict.fromkeys(out))

    def _resolve(self, client: httpx.Client, location: str, country: str | None) -> dict[str, Any]:
        last: dict[str, Any] = {"status": "not_found"}
        for level, query in enumerate(self.variants(location, country)):
            entry = self._ask(client, query)
            if entry["status"] == "found":
                # Dropping the most specific components makes the place less precise than the bounding
                # box says, so the radius gets a floor that grows with every component dropped.
                floor = (0.3, 2.0, 5.0, 15.0)[min(level, 3)]
                entry.update(query_used=query, fallback_level=level, bbox_radius_km=entry["uncertainty_radius_km"],
                             uncertainty_radius_km=max(entry["uncertainty_radius_km"], floor))
                return entry
            last = entry
            time.sleep(1.1)
        return last

    @staticmethod
    def _ask(client: httpx.Client, query: str) -> dict[str, Any]:
        try:
            response = client.get(URL, params={"q": query, "format": "jsonv2", "limit": 1})
            if response.status_code == 429:
                return {"status": "error", "error": "rate limited"}
            hits = response.json() if response.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            return {"status": "error", "error": "network"}
        if not hits:
            return {"status": "not_found"}
        hit = hits[0]
        kind = str(hit.get("addresstype") or hit.get("type") or "")
        return {
            "status": "found", "latitude": float(hit["lat"]), "longitude": float(hit["lon"]),
            "display_name": str(hit.get("display_name", ""))[:300],
            "granularity": _GRAN.get(kind, "area"), "osm_type": kind,
            "uncertainty_radius_km": _radius_km(hit["boundingbox"]),
            "method": "nominatim",
        }
