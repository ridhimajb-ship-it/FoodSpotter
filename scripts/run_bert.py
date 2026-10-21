#!/usr/bin/env python
"""Run the BERT sentiment model over matched reviews, then recompute rankings.

    pip install -r backend/requirements-bert.txt        # one-off: transformers + torch
    python scripts/run_bert.py                           # first run downloads the model (several hundred MB) from Hugging Face
    python scripts/run_bert.py --limit 200               # quick trial on 200 reviews
    python scripts/run_bert.py --force                   # recompute everything

Model: nlptown/bert-base-multilingual-uncased-sentiment (1-5 stars -> negative / neutral / positive).
The VADER baseline is kept and stays the active engine until BERT covers >= 95% of the matched reviews
(SENTIMENT_ENGINE=bert forces BERT). If the model cannot be loaded nothing is written and the reason is printed.
"""
import argparse
import json

from _common import session

from backend.services.pipeline import run_bert
from backend.services.ranking import recompute_rankings
from backend.services.sentiment_view import engine_info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="delete existing BERT results and recompute")
    ap.add_argument("--limit", type=int, default=None, help="analyse at most N reviews")
    args = ap.parse_args()
    db = session()
    try:
        res = run_bert(db, force=args.force, limit=args.limit)
        print(json.dumps(res, indent=2))
        if res["status"] == "unavailable":
            return 2
        recompute_rankings(db)
        info = engine_info(db)
        print(f"Active engine: {info['active']} - {info['reason']}")
        print(f"BERT coverage: {info['coverage']['bert']} / {info['coverage']['matched_reviews']} matched reviews")
        return 0 if res["status"] == "ok" else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
