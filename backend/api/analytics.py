from __future__ import annotations

from collections import Counter, defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.config import get_settings
from backend.database.base import iso
from backend.database.db import get_db
from backend.models import DiscoveryHistory, ImportHistory, Restaurant, RestaurantRanking, Review
from backend.nlp.preprocess import preprocess
from backend.nlp.summarize import distinctive_terms, top_terms
from backend.services import queries as Q
from backend.services.filters import Filters, filter_params, select_restaurants
from backend.services.neighborhoods import label_for
from backend.services.sentiment_view import active_engine, engine_info, sentiment_cols

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

_kw_cache: dict = {}


@router.get("/overview", summary="Dataset coverage, sentiment distribution and data-source statistics")
def overview(db: Session = Depends(get_db)):
    s = get_settings()
    total = db.scalar(select(func.count(Restaurant.id))) or 0
    by_source = dict(db.execute(select(Restaurant.primary_source, func.count()).group_by(Restaurant.primary_source)).all())
    with_rating = db.scalar(select(func.count(Restaurant.id)).where(Restaurant.rating.is_not(None))) or 0
    valid = Q.valid_review_filter()
    eng = engine_info(db)
    model, label_col, _, _ = sentiment_cols(eng["active"])
    analysed = db.scalar(select(func.count(Review.id)).join(model, model.review_id == Review.id).where(*valid)) or 0
    per_rest = [n for (n,) in db.execute(select(func.count(Review.id)).where(*valid).group_by(Review.restaurant_id))]
    dist = dict(db.execute(select(label_col, func.count()).join(Review, Review.id == model.review_id).where(*valid).group_by(label_col)).all())
    status_counts = dict(db.execute(select(Review.match_status, func.count()).group_by(Review.match_status)).all())
    src_counts = dict(db.execute(select(Review.source, func.count()).where(*valid).group_by(Review.source)).all())
    gem_counts = dict(db.execute(select(RestaurantRanking.gem_status, func.count()).group_by(RestaurantRanking.gem_status)).all())
    last_import = db.scalar(select(ImportHistory).order_by(ImportHistory.id.desc()).limit(1))
    last_disc = db.scalar(select(DiscoveryHistory).order_by(DiscoveryHistory.id.desc()).limit(1))
    return {
        "empty": total == 0,
        "restaurants": {
            "total": total, "by_source": by_source, "with_rating": with_rating,
            "with_analysed_reviews": len(per_rest), "with_min_aspect_evidence": sum(1 for n in per_rest if n >= s.min_aspect_mentions),
            "needing_recheck": db.scalar(select(func.count(Restaurant.id)).where(Restaurant.needs_recheck.is_(True))) or 0,
        },
        "reviews": {
            "analysed": analysed, "by_source": src_counts, "by_match_status": status_counts,
            "excluded_from_analytics": sum(v for k, v in status_counts.items() if k not in ("matched", "verified_manual")),
            "dated_reviews": db.scalar(select(func.count(Review.id)).where(Review.reviewed_at.is_not(None), *valid)) or 0,
            "mean_per_restaurant": round(sum(per_rest) / len(per_rest), 2) if per_rest else 0,
        },
        "sentiment_distribution": {k: dist.get(k, 0) for k in ("positive", "neutral", "negative")},
        "sentiment_engine": eng,
        "gem_status_counts": gem_counts,
        "last_import": None if not last_import else {"filename": last_import.filename, "status": last_import.status, "finished_at": iso(last_import.finished_at),
                                                      "valid_reviews_imported": (last_import.report or {}).get("valid_reviews_imported")},
        "last_discovery": None if not last_disc else {"source": last_disc.source, "status": last_disc.status, "finished_at": iso(last_disc.finished_at),
                                                       "found": last_disc.found_count, "new": last_disc.new_count, "is_baseline": last_disc.is_baseline},
        "data_notes": [
            "Restaurant names and coordinates: OpenStreetMap contributors (ODbL).",
            "Reviews, ratings and vote counts: historical Zomato Bangalore dataset (Kaggle) – a past snapshot, not current.",
            "Coverage is partial: only restaurants that could be matched with name + area + address evidence carry reviews.",
        ],
    }


@router.get("/hotspots", summary="Heatmap points. Density, review activity and popularity are DIFFERENT measures.")
def hotspots(metric: Literal["density", "reviews", "popularity"] = "density", f: Filters = Depends(filter_params), db: Session = Depends(get_db)):
    sel = select_restaurants(db, f)
    pts = []
    for r in sel.restaurants:
        if not r.location:
            continue
        if metric == "density":
            w = 1.0
        elif metric == "reviews":
            w = float(sel.counts.get(r.id, {}).get("n", 0))
        else:
            w = (r.ranking.popularity_score or 0) / 100 if r.ranking else 0.0
        if w > 0:
            pts.append([r.location.latitude, r.location.longitude, round(w, 4)])
    desc = {
        "density": "Where restaurants are concentrated. Density says nothing about how popular or well-liked they are.",
        "reviews": "Where analysed review text is concentrated. Reflects the coverage of the historical dataset, not current activity.",
        "popularity": "Restaurant coordinates weighted by FoodSpotter's confidence-adjusted popularity score (only restaurants with a score).",
    }[metric]
    return {"metric": metric, "description": desc, "n_points": len(pts), "max_weight": max((p[2] for p in pts), default=0), "points": pts,
            "filters_applied": f.active()}


@router.get("/cuisines", summary="Cuisine distribution and popularity")
def cuisines(min_restaurants: int = Query(3, ge=1, le=50), db: Session = Depends(get_db)):
    rows = db.execute(select(Restaurant.cuisines, RestaurantRanking.popularity_score).outerjoin(RestaurantRanking, RestaurantRanking.restaurant_id == Restaurant.id)).all()
    count: Counter = Counter()
    pops: dict[str, list[float]] = defaultdict(list)
    unspecified = 0
    for c, pop in rows:
        items = [x for x in (c or "").split(";") if x]
        if not items:
            unspecified += 1
        for x in items:
            count[x] += 1
            if pop is not None:
                pops[x].append(pop)
    return {
        "distribution": [{"cuisine": k.title(), "value": k, "restaurants": v} for k, v in count.most_common(30)],
        "popularity": sorted(
            [{"cuisine": k.title(), "value": k, "mean_popularity": round(sum(v) / len(v), 2), "rated_restaurants": len(v)} for k, v in pops.items() if len(v) >= min_restaurants],
            key=lambda d: -d["mean_popularity"])[:20],
        "unspecified_cuisine": unspecified,
        "min_restaurants_for_popularity": min_restaurants,
    }


@router.get("/neighborhoods", summary="Per-neighbourhood counts and popularity")
def neighborhoods(db: Session = Depends(get_db)):
    rows = db.execute(select(Restaurant.id, Restaurant.neighborhood, RestaurantRanking.popularity_score).outerjoin(RestaurantRanking, RestaurantRanking.restaurant_id == Restaurant.id)).all()
    counts = Q.sentiment_counts(db)
    agg: dict = defaultdict(lambda: {"restaurants": 0, "pops": [], "reviews": 0})
    for rid, hood, pop in rows:
        a = agg[hood or "unknown"]
        a["restaurants"] += 1
        a["reviews"] += counts.get(rid, {}).get("n", 0)
        if pop is not None:
            a["pops"].append(pop)
    return {"items": sorted(
        [{"neighborhood": k, "label": label_for(k) if k != "unknown" else "Unknown", "restaurants": v["restaurants"], "analysed_reviews": v["reviews"],
          "rated_restaurants": len(v["pops"]), "mean_popularity": round(sum(v["pops"]) / len(v["pops"]), 2) if v["pops"] else None}
         for k, v in agg.items()], key=lambda d: -d["restaurants"])}


@router.get("/keywords", summary="Most frequent / most distinctive terms in positive vs negative reviews")
def keywords(db: Session = Depends(get_db)):
    mx = db.scalar(select(func.max(Review.id))) or 0
    n = db.scalar(select(func.count(Review.id))) or 0
    engine = active_engine(db)
    model, label_col, _, _ = sentiment_cols(engine)
    key = (mx, n, engine)
    if _kw_cache.get("key") == key:
        return _kw_cache["value"]
    pos, neg, allr = [], [], []
    for text, label in db.execute(select(Review.text, label_col).join(model, model.review_id == Review.id).where(*Q.valid_review_filter())):
        lemmas = preprocess(text)["lemmas"]
        allr.append(lemmas)
        (pos if label == "positive" else neg if label == "negative" else []).append(lemmas)
    value = {"overall": top_terms(allr, k=25, min_count=3), "distinctive": distinctive_terms(pos, neg, k=15),
             "basis": {"reviews": len(allr), "positive": len(pos), "negative": len(neg), "engine": engine}}
    _kw_cache.update(key=key, value=value)
    return value
