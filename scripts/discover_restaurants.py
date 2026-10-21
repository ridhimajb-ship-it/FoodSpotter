#!/usr/bin/env python
"""Discover restaurants from OpenStreetMap (Overpass) – or verify them against Google Places.

    python scripts/discover_restaurants.py                       # all nine neighbourhoods
    python scripts/discover_restaurants.py --only indiranagar koramangala
    python scripts/discover_restaurants.py --no-cache             # bypass the 24 h on-disk cache
    python scripts/discover_restaurants.py --google --limit 50    # needs GOOGLE_PLACES_API_KEY

The first successful run is the *baseline* (nothing in it is reported as "newly discovered").
Re-run it later (or enable the scheduler) to detect establishments FoodSpotter has not seen before.
"""
import argparse
import json

from _common import session

from backend.config import get_settings
from backend.integrations.google_places import GooglePlacesClient
from backend.services.discovery import run_osm_discovery, start_run
from backend.services.google_verify import run_google_verification
from backend.services.neighborhoods import BY_KEY, NEIGHBORHOODS
from backend.services.pipeline import refresh_analytics


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=list(BY_KEY), help="limit to these neighbourhoods")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--google", action="store_true", help="Google Places verification pass instead of OSM discovery")
    ap.add_argument("--limit", type=int, default=50, help="max restaurants to verify per Google run (quota guard)")
    args = ap.parse_args()
    s = get_settings()
    db = session()
    try:
        if args.google:
            if not s.google_places_api_key:
                print("GOOGLE_PLACES_API_KEY is not set (see .env.example). OSM discovery works without it.")
                return 2
            run = start_run(db, "google", [])
            run_google_verification(db, run, GooglePlacesClient(s.google_places_api_key, min_interval=s.google_min_interval_seconds), limit=args.limit)
        else:
            hoods = [BY_KEY[k] for k in args.only] if args.only else NEIGHBORHOODS
            print(f"Querying Overpass for {len(hoods)} neighbourhood(s); polite spacing is {s.overpass_min_interval_seconds}s per request …")
            run = start_run(db, "osm", [h.key for h in hoods])
            run_osm_discovery(db, run, neighborhoods=hoods, use_cache=not args.no_cache)
        print(json.dumps({"status": run.status, "baseline": run.is_baseline, "found": run.found_count, "new": run.new_count,
                          "updated": run.updated_count, "merged_duplicates": run.merged_count, "flagged_for_recheck": run.flagged_count,
                          "errors": run.errors, "notes": run.notes}, indent=2, default=str))
        refresh_analytics(db)
        return 0 if run.status in ("success", "partial") else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
