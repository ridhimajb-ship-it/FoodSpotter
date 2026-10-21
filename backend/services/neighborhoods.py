"""Neighbourhood search windows.

IMPORTANT: these bounding boxes are *approximate search windows* used to bound Overpass queries
(south, west, north, east). They are configuration, not restaurant data, and they do not claim to be
official administrative boundaries. Boxes may overlap (Church Street lies inside MG Road); a point is
assigned to the *smallest* box that contains it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Neighborhood:
    key: str
    label: str
    bbox: tuple[float, float, float, float]  # south, west, north, east

    @property
    def area(self) -> float:
        s, w, n, e = self.bbox
        return (n - s) * (e - w)

    def contains(self, lat: float, lon: float) -> bool:
        s, w, n, e = self.bbox
        return s <= lat <= n and w <= lon <= e


NEIGHBORHOODS: list[Neighborhood] = [
    Neighborhood("indiranagar", "Indiranagar", (12.965, 77.633, 12.990, 77.655)),
    Neighborhood("koramangala", "Koramangala", (12.918, 77.612, 12.945, 77.642)),
    Neighborhood("jayanagar", "Jayanagar", (12.910, 77.570, 12.940, 77.598)),
    Neighborhood("jp-nagar", "JP Nagar", (12.883, 77.572, 12.913, 77.600)),
    Neighborhood("malleshwaram", "Malleshwaram", (12.992, 77.560, 13.012, 77.583)),
    Neighborhood("whitefield", "Whitefield", (12.958, 77.730, 12.998, 77.770)),
    Neighborhood("hsr-layout", "HSR Layout", (12.898, 77.626, 12.923, 77.660)),
    Neighborhood("mg-road", "MG Road", (12.968, 77.600, 12.982, 77.625)),
    Neighborhood("church-street", "Church Street", (12.972, 77.600, 12.978, 77.612)),
]

BY_KEY = {n.key: n for n in NEIGHBORHOODS}

# Substrings (lower-case) of the dataset's free-text "location" field -> neighbourhood key.
_ZOMATO_LOCATION_HINTS = [
    ("church street", "church-street"),
    ("mg road", "mg-road"),
    ("indiranagar", "indiranagar"),
    ("koramangala", "koramangala"),
    ("jayanagar", "jayanagar"),
    ("jp nagar", "jp-nagar"),
    ("malleshwaram", "malleshwaram"),
    ("whitefield", "whitefield"),
    ("hsr", "hsr-layout"),
]


def neighborhood_for_point(lat: float, lon: float) -> Neighborhood | None:
    hits = [n for n in NEIGHBORHOODS if n.contains(lat, lon)]
    return min(hits, key=lambda n: n.area) if hits else None


def neighborhood_from_free_text(location: str | None) -> str | None:
    if not location:
        return None
    loc = location.lower()
    for hint, key in _ZOMATO_LOCATION_HINTS:
        if hint in loc:
            return key
    return None


def label_for(key: str | None) -> str | None:
    return BY_KEY[key].label if key in BY_KEY else key
