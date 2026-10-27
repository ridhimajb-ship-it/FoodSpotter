#!/usr/bin/env python
"""Import the historical Zomato Bangalore reviews CSV, run NLP and recompute rankings.

    python scripts/import_reviews.py data/zomato.csv [--max-reviews 5000] [--no-unresolved]
    python scripts/import_reviews.py --verify data/verified_matches.csv     # apply manual match decisions
    python scripts/import_reviews.py --dedupe-only                          # merge repeated reviews already stored

Run scripts/discover_restaurants.py first: reviews are only attributed to restaurants that exist in the database.
Download the dataset (needs a free Kaggle account):
    https://www.kaggle.com/datasets/himanshupoddar/zomato-bangalore-restaurants
"""
import argparse
import json

from _common import session

from backend.services.importer import DatasetError, apply_verified_matches, dedupe_existing_reviews, import_zomato_csv
from backend.services.pipeline import refresh_analytics


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--max-reviews", type=int, default=None, help="stop after N verified reviews (e.g. 5000)")
    ap.add_argument("--no-unresolved", action="store_true", help="do not store reviews whose restaurant match is unresolved")
    ap.add_argument("--verify", metavar="CSV", help="apply manual verification decisions (source_restaurant_key,restaurant_id,confirm)")
    ap.add_argument("--dedupe-only", action="store_true",
                    help="merge reviews stored once per listing row by older imports, then recompute analytics (no CSV needed)")
    args = ap.parse_args()
    db = session()
    try:
        if args.dedupe_only:
            print(json.dumps(dedupe_existing_reviews(db), indent=2))
        elif args.verify:
            print(json.dumps(apply_verified_matches(db, args.verify), indent=2))
        else:
            if not args.csv:
                ap.error("provide the dataset CSV path")
            hist = import_zomato_csv(db, args.csv, max_reviews=args.max_reviews, store_unresolved=not args.no_unresolved)
            rep = dict(hist.report)
            rep.pop("unmatched_restaurant_samples", None)
            print(json.dumps(rep, indent=2, default=str))
        print("NLP + ranking:", refresh_analytics(db))
        return 0
    except DatasetError as e:
        print(f"ERROR: {e}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
