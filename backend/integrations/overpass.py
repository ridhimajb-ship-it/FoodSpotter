"""OpenStreetMap / Overpass API client.

* Bounded queries (one bbox per neighbourhood) – never a city-wide request.
* On-disk cache (OSM data is ODbL; caching is permitted) to avoid hammering the public servers.
* Minimum spacing between requests, retry with back-off on 429/5xx, fallback to mirror servers.
Data © OpenStreetMap contributors (ODbL) – attribution is shown in the UI.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from backend.config import Settings, get_settings

AMENITIES = "restaurant|cafe|fast_food|bar|pub|food_court|ice_cream"

_rate_lock = threading.Lock()
_last_request_at = 0.0


class OverpassError(RuntimeError):
    pass


def build_query(bbox: tuple[float, float, float, float], timeout: int = 90) -> str:
    s, w, n, e = bbox
    box = f"{s},{w},{n},{e}"
    return (
        f"[out:json][timeout:{timeout}];"
        f"(node[\"amenity\"~\"^({AMENITIES})$\"][\"name\"]({box});"
        f"way[\"amenity\"~\"^({AMENITIES})$\"][\"name\"]({box}););"
        "out center tags;"
    )


def parse_element(el: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Normalise one Overpass element. Returns None if it has no name or no verified coordinates."""
    tags = el.get("tags") or {}
    name = (tags.get("name") or "").strip()
    etype, eid = el.get("type"), el.get("id")
    if not name or etype not in ("node", "way") or eid is None:
        return None
    if etype == "node":
        lat, lon = el.get("lat"), el.get("lon")
    else:
        c = el.get("center") or {}
        lat, lon = c.get("lat"), c.get("lon")
    if lat is None or lon is None:
        return None

    addr = tags.get("addr:full") or ", ".join(
        p for p in (
            " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x),
            tags.get("addr:suburb") or tags.get("addr:neighbourhood"),
            tags.get("addr:city"),
            tags.get("addr:postcode"),
        ) if p
    )
    cuisines = [c.strip().replace("_", " ").lower() for c in (tags.get("cuisine") or "").split(";") if c.strip()]
    return {
        "source_id": f"{etype}/{eid}",
        "name": name,
        "lat": float(lat),
        "lon": float(lon),
        "address": addr or None,
        "cuisines": cuisines,
        "amenity": tags.get("amenity"),
        "source_url": f"https://www.openstreetmap.org/{etype}/{eid}",
        "suburb_tag": tags.get("addr:suburb"),
    }


class OverpassClient:
    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None, sleep=time.sleep):
        self.s = settings or get_settings()
        self.client = client or httpx.Client(timeout=120, headers={"User-Agent": self.s.overpass_user_agent})
        self._sleep = sleep

    # --- cache -------------------------------------------------------------
    def _cache_path(self, key: str) -> Path:
        return Path(self.s.data_dir) / "cache" / f"overpass_{key}.json"

    def _read_cache(self, key: str) -> Optional[dict]:
        p = self._cache_path(key)
        if not p.exists():
            return None
        try:
            doc = json.loads(p.read_text())
            fetched = datetime.fromisoformat(doc["fetched_at"])
            if datetime.now(timezone.utc) - fetched < timedelta(hours=self.s.overpass_cache_hours):
                return doc
        except Exception:
            return None
        return None

    # --- fetch -------------------------------------------------------------
    def _throttle(self) -> None:
        global _last_request_at
        with _rate_lock:
            wait = self.s.overpass_min_interval_seconds - (time.monotonic() - _last_request_at)
            if wait > 0:
                self._sleep(wait)
            _last_request_at = time.monotonic()

    def fetch_bbox(self, key: str, bbox: tuple[float, float, float, float], use_cache: bool = True) -> dict:
        """Return {"elements": [...], "fetched_at": iso, "from_cache": bool}. Raises OverpassError."""
        if use_cache:
            cached = self._read_cache(key)
            if cached:
                return {**cached, "from_cache": True}

        query = build_query(bbox)
        last_err: Exception | None = None
        for url in self.s.overpass_url_list:
            for attempt in range(3):
                self._throttle()
                try:
                    r = self.client.post(url, data={"data": query})
                except httpx.HTTPError as e:
                    last_err = e
                    break  # try next mirror
                if r.status_code == 200:
                    try:
                        elements = r.json().get("elements", [])
                    except ValueError as e:
                        last_err = e
                        break
                    doc = {"fetched_at": datetime.now(timezone.utc).isoformat(), "bbox": bbox, "elements": elements}
                    self._cache_path(key).write_text(json.dumps(doc))
                    return {**doc, "from_cache": False}
                if r.status_code in (429, 504, 502, 503):
                    last_err = OverpassError(f"{url} returned {r.status_code}")
                    self._sleep(min(30, 5 * (attempt + 1) ** 2))  # back-off
                    continue
                last_err = OverpassError(f"{url} returned HTTP {r.status_code}")
                break
        raise OverpassError(f"Overpass unavailable for '{key}': {last_err}")
