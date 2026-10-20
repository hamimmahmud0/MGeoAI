"""Wire schema for road-accident extraction (LLM output and human annotation).

Key names follow the prompt contract exactly, including the misspelled
`casualities` and the key `longitude and latitude`. That key holds the string
"<latitude>,<longitude>", while GeoJSON is [longitude, latitude]; use
`lonlat_from_string` for any map or GeoJSON conversion.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

VEHICLE_VOCAB: tuple[str, ...] = (
    "car",
    "bus",
    "truck",
    "covered_van",
    "pickup",
    "microbus",
    "motorcycle",
    "cng_autorickshaw",
    "battery_autorickshaw",
    "rickshaw",
    "human_hauler",
    "bicycle",
    "tractor",
    "train",
    "ambulance",
    "van",
)
ACCIDENT_FIELDS: tuple[str, ...] = (
    "accident",
    "casualities",
    "fatalities",
    "vehicles",
    "date",
    "country",
    "location",
    "longitude and latitude",
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z))?$")
_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    quote: str = Field(max_length=2000)
    note: str | None = Field(default=None, max_length=500)


class AccidentRecord(BaseModel):
    """One road accident reported by an article (or `accident=false`)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    accident: bool
    casualities: int | None = Field(default=None, ge=0, le=100000)
    fatalities: int | None = Field(default=None, ge=0, le=100000)
    vehicles: list[str] | None = None
    date: str | None = None
    country: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=500)
    latitude_longitude: str | None = Field(default=None, alias="longitude and latitude")
    evidences: list[Evidence] = Field(default_factory=list, max_length=60)

    @field_validator("date")
    @classmethod
    def _date(cls, value: str | None) -> str | None:
        if value is not None and not _DATE_RE.match(value):
            raise ValueError("date must be YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS+HH:MM")
        return value

    @field_validator("latitude_longitude")
    @classmethod
    def _coords(cls, value: str | None) -> str | None:
        if value is not None and lonlat_from_string(value) is None:
            raise ValueError('coordinates must be "<latitude>,<longitude>" within range')
        return value

    @field_validator("vehicles")
    @classmethod
    def _vehicles(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        seen: list[str] = []
        for item in value:
            item = item.strip()
            if not item:
                continue
            if item not in VEHICLE_VOCAB and not (
                item.startswith("other:") and len(item) > len("other:")
            ):
                raise ValueError(f"vehicle {item!r} is not in the vocabulary")
            if item not in seen:
                seen.append(item)
        return seen

    def wire(self) -> dict[str, Any]:
        """Dict with the exact wire keys in the contract order."""
        data = self.model_dump(by_alias=True, mode="json")
        return {key: data[key] for key in (*ACCIDENT_FIELDS, "evidences")}


def lonlat_from_string(value: str) -> tuple[float, float] | None:
    """Parse "<lat>,<lon>" and return GeoJSON order (lon, lat), or None if invalid."""
    match = _COORD_RE.match(value)
    if not match:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lon, lat


class ImageAnalysis(BaseModel):
    """What a model reports it can see in one article image (LLM side)."""

    model_config = ConfigDict(extra="forbid")

    image_id: str
    what_is_visible: str = Field(max_length=2000)
    shows_accident: bool | None = None
    vehicles_visible: list[str] = Field(default_factory=list)
    people_or_casualty_cues: str | None = Field(default=None, max_length=1000)
    text_in_image: str | None = Field(default=None, max_length=1000)
    location_cues: str | None = Field(default=None, max_length=1000)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ImageLabel(BaseModel):
    """Human annotation of one image."""

    model_config = ConfigDict(extra="forbid")

    image_id: str
    description: str = Field(default="", max_length=2000)
    shows_accident: bool | None = None
    vehicles_visible: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=1000)


class ExtractionOutput(BaseModel):
    """Full model response: accidents for the article plus per-image analyses."""

    model_config = ConfigDict(extra="forbid")

    accidents: list[AccidentRecord] = Field(min_length=1, max_length=20)
    images: list[ImageAnalysis] = Field(default_factory=list, max_length=20)
