"""Optional Google Places API (New) integration.

Terms-driven design (see docs/DATA_SOURCES.md):
* Only the Place ID is persisted (Place IDs may be stored indefinitely).
* Ratings, review text and other Places content are fetched on demand and returned to the caller; they are
  never written to the database and never used for ranking.
* At most five reviews are returned by the API; we make no attempt to obtain more.
* Review text must be shown with Google attribution, and Google-sourced content must not be drawn on a
  non-Google map; FoodSpotter therefore shows it only in the details panel, never as map markers.
* The API key stays on the server.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from backend.services.matching import haversine_m, name_similarity

BASE = "https://places.googleapis.com/v1"


class GooglePlacesError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, quota: bool = False):
        super().__init__(message)
        self.status = status
        self.quota = quota


class GooglePlacesClient:
    def __init__(self, api_key: str, client: httpx.Client | None = None, min_interval: float = 0.2, sleep=time.sleep):
        if not api_key:
            raise GooglePlacesError("GOOGLE_PLACES_API_KEY is not configured")
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=20)
        self.min_interval = min_interval
        self._sleep = sleep
        self._last = 0.0

    def _request(self, method: str, path: str, field_mask: str, json_body: dict | None = None) -> dict[str, Any]:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            self._sleep(wait)
        self._last = time.monotonic()
        headers = {"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": field_mask}
        try:
            r = self.client.request(method, f"{BASE}{path}", headers=headers, json=json_body)
        except httpx.HTTPError as e:
            raise GooglePlacesError(f"Network error talking to Google Places: {e}") from e
        if r.status_code == 429 or (r.status_code == 403 and "quota" in r.text.lower()):
            raise GooglePlacesError("Google Places quota exceeded", r.status_code, quota=True)
        if r.status_code >= 400:
            # Never echo the request headers (they contain the key); only a short server message.
            msg = ""
            try:
                msg = r.json().get("error", {}).get("message", "")
            except ValueError:
                pass
            raise GooglePlacesError(f"Google Places error {r.status_code}: {msg[:200]}", r.status_code)
        return r.json()

    def search_text(self, query: str, lat: float, lon: float, radius_m: float = 150.0) -> list[dict]:
        body = {
            "textQuery": query,
            "includedType": "restaurant",
            "maxResultCount": 5,
            "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": radius_m}},
        }
        data = self._request("POST", "/places:searchText", "places.id,places.displayName,places.location,places.businessStatus", body)
        return data.get("places", [])

    def details(self, place_id: str, with_reviews: bool = False) -> dict:
        mask = "id,displayName,businessStatus,googleMapsUri"
        if with_reviews:
            mask += ",rating,userRatingCount,reviews"
        return self._request("GET", f"/places/{place_id}", mask)

    def find_matching_place(self, name: str, lat: float, lon: float, max_distance_m: float = 100.0) -> Optional[dict]:
        """Return a Google place only when BOTH the name and the location agree with our verified record."""
        best = None
        for p in self.search_text(name, lat, lon):
            loc = p.get("location") or {}
            if "latitude" not in loc:
                continue
            gname = (p.get("displayName") or {}).get("text", "")
            dist = haversine_m(lat, lon, loc["latitude"], loc["longitude"])
            sim = name_similarity(name, gname)
            if sim >= 0.9 and dist <= max_distance_m and (best is None or dist < best[1]):
                best = (p, dist)
        return best[0] if best else None
