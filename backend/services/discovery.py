"""Restaurant discovery: refresh from OpenStreetMap, detect new establishments, flag ones needing a recheck.

Semantics
---------
* `first_discovered_at` is when *FoodSpotter* first saw a restaurant – NOT when it opened.
* The first successful run for a source is a *baseline*; its findings are existing restaurants, so they are
  never listed as "newly discovered".
* A restaurant that disappears from a successful query of its neighbourhood is flagged `needs_recheck`
  (never deleted – absence from OSM does not prove closure).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.base import utcnow
from backend.integrations.overpass import OverpassClient, OverpassError, parse_element
from backend.models import DiscoveryHistory, Location, Restaurant, RestaurantSourceId
from backend.services.matching import haversine_m, normalize_name
from backend.services.neighborhoods import NEIGHBORHOODS, Neighborhood, neighborhood_for_point

DUPLICATE_RADIUS_M = 30.0  # same name within 30 m => same establishment (e.g. node + building outline)


def start_run(db: Session, source: str, neighborhoods: list[str]) -> DiscoveryHistory:
    prior = db.scalar(
        select(DiscoveryHistory.id).where(DiscoveryHistory.source == source, DiscoveryHistory.status.in_(("success", "partial"))).limit(1)
    )
    run = DiscoveryHistory(source=source, status="running", is_baseline=prior is None, neighborhoods=neighborhoods, errors=[])
    db.add(run)
    db.commit()
    return run


def run_osm_discovery(
    db: Session,
    run: DiscoveryHistory,
    client: Optional[OverpassClient] = None,
    neighborhoods: Optional[list[Neighborhood]] = None,
    use_cache: bool = True,
) -> DiscoveryHistory:
    client = client or OverpassClient()
    hoods = neighborhoods or NEIGHBORHOODS
    started = run.started_at
    now = utcnow()
    errors: list[str] = []
    succeeded: set[str] = set()
    parsed: dict[str, dict] = {}

    for hood in hoods:
        try:
            doc = client.fetch_bbox(hood.key, hood.bbox, use_cache=use_cache)
        except OverpassError as e:
            errors.append(f"{hood.label}: {e}")
            continue
        succeeded.add(hood.key)
        for el in doc["elements"]:
            rec = parse_element(el)
            if rec:
                parsed[rec["source_id"]] = rec  # same element returned by overlapping boxes collapses here

    # Index existing data
    existing_ids = {
        sid.source_id: sid
        for sid in db.scalars(select(RestaurantSourceId).where(RestaurantSourceId.source == "osm"))
    }
    by_name: dict[str, list[tuple[int, float, float]]] = {}
    for r in db.scalars(select(Restaurant)):
        if r.location:
            by_name.setdefault(r.name_normalized, []).append((r.id, r.location.latitude, r.location.longitude))

    new = updated = merged = 0
    seen_restaurant_ids: set[int] = set()

    for sid, rec in parsed.items():
        hood = neighborhood_for_point(rec["lat"], rec["lon"])
        hood_key = hood.key if hood else None
        norm = normalize_name(rec["name"])
        known = existing_ids.get(sid)

        if known is not None:
            r = db.get(Restaurant, known.restaurant_id)
            known.last_seen_at = now
            if known.role == "primary":  # aliases never overwrite the primary record's attributes
                r.name, r.name_normalized = rec["name"], norm
                r.address = rec["address"] or r.address
                r.neighborhood = hood_key or r.neighborhood
                if rec["cuisines"] and r.cuisine_source in (None, "osm"):
                    r.cuisines, r.cuisine_source = ";".join(rec["cuisines"]), "osm"
                r.location.latitude, r.location.longitude, r.location.verified_at = rec["lat"], rec["lon"], now
                r.last_verified_at, r.needs_recheck, r.recheck_reason = now, False, None
                updated += 1
            seen_restaurant_ids.add(r.id)
            continue

        # Duplicate detection: same normalised name AND within 30 m of an existing record.
        dup_id = next(
            (rid for rid, la, lo in by_name.get(norm, []) if haversine_m(rec["lat"], rec["lon"], la, lo) <= DUPLICATE_RADIUS_M),
            None,
        )
        if dup_id is not None:
            db.add(RestaurantSourceId(restaurant_id=dup_id, source="osm", source_id=sid, role="alias", first_seen_at=now, last_seen_at=now))
            seen_restaurant_ids.add(dup_id)
            merged += 1
            continue

        r = Restaurant(
            name=rec["name"], name_normalized=norm, address=rec["address"], neighborhood=hood_key,
            cuisines=";".join(rec["cuisines"]) or None, cuisine_source="osm" if rec["cuisines"] else None,
            amenity=rec["amenity"], primary_source="osm", source_url=rec["source_url"],
            first_discovered_at=now, last_verified_at=now, discovery_run_id=run.id,
        )
        r.location = Location(latitude=rec["lat"], longitude=rec["lon"], source="osm", verified_at=now)
        r.source_ids.append(RestaurantSourceId(source="osm", source_id=sid, role="primary", first_seen_at=now, last_seen_at=now))
        db.add(r)
        db.flush()
        by_name.setdefault(norm, []).append((r.id, rec["lat"], rec["lon"]))
        seen_restaurant_ids.add(r.id)
        new += 1

    # Flag restaurants in successfully-queried neighbourhoods that were not seen this time.
    flagged = 0
    if succeeded:
        stale = db.scalars(
            select(Restaurant).where(
                Restaurant.primary_source == "osm",
                Restaurant.neighborhood.in_(succeeded),
                Restaurant.last_verified_at < started,
            )
        )
        for r in stale:
            if r.id not in seen_restaurant_ids and not r.needs_recheck:
                r.needs_recheck, r.recheck_reason = True, "Not returned by the latest OpenStreetMap query"
                flagged += 1

    run.found_count, run.new_count, run.updated_count = len(parsed), new, updated
    run.merged_count, run.flagged_count, run.errors = merged, flagged, errors
    run.finished_at = utcnow()
    run.status = "failed" if not succeeded else ("partial" if errors else "success")
    if run.status == "failed":
        run.is_baseline = False  # a failed run must not consume the baseline
    run.notes = {"neighborhoods_succeeded": sorted(succeeded), "data_attribution": "© OpenStreetMap contributors (ODbL)"}
    db.commit()
    return run
