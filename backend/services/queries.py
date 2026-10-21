"""Read-side helpers shared by the API routes."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from backend.config import get_settings
from backend.database.base import iso
from backend.models import AspectSentiment, Restaurant, RestaurantRanking, Review
from backend.nlp.aspects import ASPECTS
from backend.nlp.preprocess import preprocess
from backend.nlp.summarize import aspect_stats, build_summary, distinctive_terms, top_terms
from backend.services.neighborhoods import label_for
from backend.services.constants import VALID_REVIEW_STATUSES
from backend.services.sentiment_view import active_engine, sentiment_cols

REVIEW_SOURCE_LABELS = {
    "zomato_kaggle": "Zomato Bangalore Restaurants dataset (Kaggle) – historical snapshot, not current",
}
RATING_NOTE = {
    "zomato_kaggle": "Rating and vote count come from a historical Zomato dataset snapshot and may be out of date.",
}


def valid_review_filter():
    return (Review.restaurant_id.is_not(None), Review.match_status.in_(VALID_REVIEW_STATUSES))


def sentiment_counts(db: Session, ids: Optional[list[int]] = None, engine: Optional[str] = None) -> dict[int, dict]:
    """Per-restaurant sentiment counts from the active engine (BERT when it covers the reviews, else VADER)."""
    model, label_col, pol_col, _ = sentiment_cols(engine or active_engine(db))
    q = (
        select(
            Review.restaurant_id,
            func.count(Review.id),
            func.sum(case((label_col == "positive", 1), else_=0)),
            func.sum(case((label_col == "negative", 1), else_=0)),
            func.sum(case((label_col == "neutral", 1), else_=0)),
            func.avg(pol_col),
        )
        .join(model, model.review_id == Review.id)
        .where(*valid_review_filter())
        .group_by(Review.restaurant_id)
    )
    if ids is not None:
        q = q.where(Review.restaurant_id.in_(ids))
    return {
        rid: {"n": n, "positive": int(p or 0), "negative": int(ng or 0), "neutral": int(nu or 0), "mean_compound": round(float(avg or 0), 4)}
        for rid, n, p, ng, nu, avg in db.execute(q)
    }


def summary_dict(r: Restaurant, counts: dict | None = None) -> dict:
    rk = r.ranking
    c = counts or {}
    n = c.get("n", 0)
    return {
        "id": r.id,
        "name": r.name,
        "address": r.address,
        "neighborhood": r.neighborhood,
        "neighborhood_label": label_for(r.neighborhood),
        "cuisines": [x for x in (r.cuisines or "").split(";") if x],
        "latitude": r.location.latitude if r.location else None,
        "longitude": r.location.longitude if r.location else None,
        "rating": r.rating,
        "rating_count": r.rating_count,
        "rating_source": r.rating_source,
        "price_info": r.price_info,
        "review_count": n,
        "positive_share": round(c["positive"] / n, 3) if n else None,
        "popularity_score": rk.popularity_score if rk else None,
        "popularity_rank": rk.popularity_rank if rk else None,
        "hidden_gem_score": rk.hidden_gem_score if rk else None,
        "gem_status": rk.gem_status if rk else "insufficient_evidence",
        "confidence": rk.confidence if rk else None,
        "needs_recheck": r.needs_recheck,
        "first_discovered_at": iso(r.first_discovered_at),
    }


def detail_dict(db: Session, r: Restaurant) -> dict:
    counts = sentiment_counts(db, [r.id]).get(r.id)
    d = summary_dict(r, counts)
    rk = r.ranking
    d.update(
        {
            "source": r.primary_source,
            "source_url": r.source_url,
            "source_attribution": "© OpenStreetMap contributors" if r.primary_source == "osm" else r.primary_source,
            "rating_note": RATING_NOTE.get(r.rating_source or ""),
            "price_source": r.price_source,
            "last_verified_at": iso(r.last_verified_at),
            "recheck_reason": r.recheck_reason,
            "opening_date": r.opening_date,
            "ranking_explanation": rk.explanation if rk else [],
            "ranking_components": rk.components if rk else {},
            "gem_explanation": rk.gem_explanation if rk else None,
            "visibility_percentile": rk.visibility_percentile if rk else None,
            "directions_url": (
                f"https://www.google.com/maps/dir/?api=1&destination={r.location.latitude},{r.location.longitude}"
                if r.location else None
            ),
            "has_google_place_id": any(s.source == "google_place_id" for s in r.source_ids),
        }
    )
    return d


def load_restaurant(db: Session, rid: int) -> Optional[Restaurant]:
    return db.scalar(
        select(Restaurant)
        .options(joinedload(Restaurant.location), joinedload(Restaurant.ranking), joinedload(Restaurant.source_ids))
        .where(Restaurant.id == rid)
    )


def aspects_for_restaurant(db: Session, rid: int, engine: Optional[str] = None) -> dict:
    model, _, _, _ = sentiment_cols(engine or active_engine(db))
    rows = db.execute(
        select(AspectSentiment.aspect, AspectSentiment.label)
        .join(Review, Review.id == AspectSentiment.review_id)
        .where(Review.restaurant_id == rid, Review.match_status.in_(VALID_REVIEW_STATUSES))
    ).all()
    stats = aspect_stats(rows)
    n_reviews = db.scalar(
        select(func.count(Review.id)).join(model, model.review_id == Review.id)
        .where(Review.restaurant_id == rid, Review.match_status.in_(VALID_REVIEW_STATUSES))
    ) or 0
    return {"aspects": [stats[a] for a in ASPECTS], "summary": build_summary(stats, n_reviews), "analysed_reviews": n_reviews,
            "min_mentions_required": get_settings().min_aspect_mentions}


def themes_for_restaurant(db: Session, rid: int, engine: Optional[str] = None) -> dict:
    model, label_col, _, _ = sentiment_cols(engine or active_engine(db))
    pos, neg = [], []
    rows = db.execute(
        select(Review.text, label_col)
        .join(model, model.review_id == Review.id)
        .where(Review.restaurant_id == rid, Review.match_status.in_(VALID_REVIEW_STATUSES))
    ).all()
    for text, label in rows:
        lemmas = preprocess(text)["lemmas"]
        if label == "positive":
            pos.append(lemmas)
        elif label == "negative":
            neg.append(lemmas)
    out = distinctive_terms(pos, neg)
    out["basis"] = {"positive_reviews": len(pos), "negative_reviews": len(neg)}
    return out


def aspect_scores_by_restaurant(db: Session, ids: list[int]) -> dict[int, dict]:
    rows = db.execute(
        select(Review.restaurant_id, AspectSentiment.aspect, AspectSentiment.label)
        .join(Review, Review.id == AspectSentiment.review_id)
        .where(Review.restaurant_id.in_(ids), Review.match_status.in_(VALID_REVIEW_STATUSES))
    ).all()
    grouped: dict[int, list] = defaultdict(list)
    for rid, a, l in rows:
        grouped[rid].append((a, l))
    return {rid: aspect_stats(grouped.get(rid, [])) for rid in ids}
