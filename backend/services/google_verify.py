"""Optional Google Places verification pass.

Links our verified OSM restaurants to Google Place IDs (only when name AND location agree) and flags
establishments Google reports as permanently/temporarily closed. Only Place IDs are stored.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.base import utcnow
from backend.integrations.google_places import GooglePlacesClient, GooglePlacesError
from backend.models import DiscoveryHistory, Restaurant, RestaurantSourceId
from backend.services.discovery import start_run


def google_place_id(r: Restaurant) -> str | None:
    return next((s.source_id for s in r.source_ids if s.source == "google_place_id"), None)


def run_google_verification(db: Session, run: DiscoveryHistory, client: GooglePlacesClient, limit: int = 100) -> DiscoveryHistory:
    """Verify at most `limit` restaurants per run so a scheduled job stays inside the API quota."""
    now = utcnow()
    errors: list[str] = []
    linked = flagged = checked = unmatched = 0
    quota_hit = False

    todo = db.scalars(
        select(Restaurant).where(Restaurant.primary_source == "osm").order_by(Restaurant.last_verified_at.asc())
    ).all()

    for r in todo:
        if checked >= limit:
            break
        checked += 1
        try:
            pid = google_place_id(r)
            if pid is None:
                match = client.find_matching_place(r.name, r.location.latitude, r.location.longitude)
                if match is None:
                    unmatched += 1
                    continue
                pid = match["id"]
                db.add(RestaurantSourceId(restaurant_id=r.id, source="google_place_id", source_id=pid, role="alias", first_seen_at=now, last_seen_at=now))
                linked += 1
                status = match.get("businessStatus")
            else:
                status = client.details(pid).get("businessStatus")
            if status in ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"):
                r.needs_recheck = True
                r.recheck_reason = f"Google Places reports {status.lower().replace('_', ' ')}"
                flagged += 1
            for s in r.source_ids:
                if s.source == "google_place_id":
                    s.last_seen_at = now
        except GooglePlacesError as e:
            errors.append(f"{r.name}: {e}")
            if e.quota:
                quota_hit = True
                break  # stop immediately: do not keep spending a quota that is exhausted

    run.found_count = checked
    run.new_count = linked  # place IDs newly linked
    run.flagged_count = flagged
    run.errors = errors
    run.finished_at = utcnow()
    run.status = "failed" if (errors and linked == 0 and checked and quota_hit) else ("partial" if errors else "success")
    run.notes = {"place_ids_linked": linked, "no_google_match": unmatched, "quota_exceeded": quota_hit,
                 "note": "Only Google Place IDs are stored; no Google ratings/reviews are persisted."}
    db.commit()
    return run


__all__ = ["run_google_verification", "google_place_id", "start_run"]
