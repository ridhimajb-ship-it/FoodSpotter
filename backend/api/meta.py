from __future__ import annotations

import json
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import ROOT, get_settings
from backend.database.db import get_db
from backend.models import Restaurant, Review
from backend.services.neighborhoods import NEIGHBORHOODS

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", summary="Liveness check")
def health():
    return {"status": "ok"}


@router.get("/meta", summary="Filter options and feature availability")
def meta(db: Session = Depends(get_db)):
    s = get_settings()
    cuisines: Counter = Counter()
    for (c,) in db.execute(select(Restaurant.cuisines).where(Restaurant.cuisines.is_not(None))):
        cuisines.update(x for x in c.split(";") if x)
    hood_counts = dict(db.execute(select(Restaurant.neighborhood, func.count()).group_by(Restaurant.neighborhood)).all())
    return {
        "neighborhoods": [{"key": n.key, "label": n.label, "restaurants": hood_counts.get(n.key, 0), "center": [(n.bbox[0] + n.bbox[2]) / 2, (n.bbox[1] + n.bbox[3]) / 2]} for n in NEIGHBORHOODS],
        "cuisines": [{"value": c, "label": c.title(), "restaurants": n} for c, n in cuisines.most_common(25)],
        "features": {"google_live_reviews": bool(s.google_places_api_key), "admin_enabled": bool(s.admin_token)},
        "totals": {"restaurants": db.scalar(select(func.count(Restaurant.id))) or 0, "reviews": db.scalar(select(func.count(Review.id))) or 0},
        "map_attribution": "© OpenStreetMap contributors",
        "min_aspect_mentions": s.min_aspect_mentions,
    }


@router.get("/evaluation/latest", summary="Most recent evaluation results written by scripts/evaluate_models.py")
def latest_evaluation():
    p = ROOT / "docs" / "evaluation_results.json"
    if not p.exists():
        return {"available": False, "message": "No evaluation has been run yet. Run `python scripts/evaluate_models.py` after importing data."}
    return {"available": True, **json.loads(p.read_text())}
