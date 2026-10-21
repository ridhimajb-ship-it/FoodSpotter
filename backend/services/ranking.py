"""Transparent, confidence-aware ranking.

Popularity score (0-100) = weighted mean of normalised components, using only components with data
(weights are re-normalised over the available ones, so a missing component never counts as zero):

  rating     Bayesian-adjusted average rating, scaled (r-1)/4         – shrinks small-sample ratings to the global mean
  volume     log(1+votes) / log(1+max votes)                          – how widely rated the place is
  sentiment  shrunk positive-review share                              – NLP evidence from review text
  recency    share of timestamped reviews inside the recency window   – ONLY when review dates exist

Hidden gems are scored separately (Wilson lower bound of positive share + rating + low visibility) and must pass
explicit evidence thresholds; otherwise a reason is returned instead of a score.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.base import utcnow
from backend.models import Restaurant, RestaurantRanking, Review

from backend.services.constants import VALID_REVIEW_STATUSES  # noqa: E402,F401


@dataclass
class RankInput:
    restaurant_id: int
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    n_reviews: int = 0
    n_pos: int = 0
    n_neg: int = 0
    n_neu: int = 0
    recent_share: Optional[float] = None  # None when no review dates are available


@dataclass
class RankOutput:
    restaurant_id: int
    popularity_score: Optional[float] = None
    popularity_rank: Optional[int] = None
    hidden_gem_score: Optional[float] = None
    gem_status: str = "insufficient_evidence"
    confidence: Optional[float] = None
    visibility_percentile: Optional[float] = None
    components: dict = field(default_factory=dict)
    explanation: list[str] = field(default_factory=list)
    gem_explanation: str = ""


# ------------------------------------------------------------------ math helpers
def bayesian_rating(rating: float, votes: int, prior_mean: float, prior_strength: float) -> float:
    return (votes * rating + prior_strength * prior_mean) / (votes + prior_strength)


def shrunk_share(pos: int, n: int, prior: float, strength: float) -> float:
    return (pos + strength * prior) / (n + strength)


def wilson_lower_bound(pos: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = pos / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def percentile_rank(value: float, population: list[float]) -> float:
    """Share of the population strictly below `value` (0..1)."""
    if not population:
        return 0.0
    return sum(1 for v in population if v < value) / len(population)


# ------------------------------------------------------------------ core computation
def compute_rankings(rows: list[RankInput], s: Settings | None = None) -> dict[int, RankOutput]:
    s = s or get_settings()
    out: dict[int, RankOutput] = {r.restaurant_id: RankOutput(r.restaurant_id) for r in rows}

    rated = [r for r in rows if r.rating is not None]
    prior_mean = sum(r.rating for r in rated) / len(rated) if rated else None
    total_n = sum(r.n_reviews for r in rows)
    prior_pos = (sum(r.n_pos for r in rows) / total_n) if total_n else 0.5

    def visibility(r: RankInput) -> int:
        return r.rating_count if r.rating_count else r.n_reviews

    vis_values = [visibility(r) for r in rows if visibility(r) > 0]
    max_vis = max(vis_values) if vis_values else 0

    for r in rows:
        o = out[r.restaurant_id]
        v = visibility(r)
        comps: dict[str, dict] = {}
        expl: list[str] = []
        conf_parts: list[float] = []

        if r.rating is not None and prior_mean is not None:
            votes = r.rating_count or 0
            adj = bayesian_rating(r.rating, votes, prior_mean, s.rating_prior_strength)
            comps["rating"] = {"value": round((adj - 1) / 4, 4), "raw": r.rating, "adjusted": round(adj, 3), "weight": s.w_rating}
            expl.append(
                f"Rating {r.rating:.1f} from {votes} votes is adjusted to {adj:.2f} "
                f"(pulled toward the dataset mean {prior_mean:.2f}; fewer votes = stronger pull)."
            )
            conf_parts.append(votes / (votes + s.rating_prior_strength))

        if v > 0 and max_vis > 0:
            val = math.log1p(v) / math.log1p(max_vis)
            comps["volume"] = {"value": round(val, 4), "raw": v, "weight": s.w_volume}
            expl.append(f"Visibility: {v} ratings/reviews on record (log-scaled against the most-reviewed restaurant).")

        if r.n_reviews > 0:
            share = shrunk_share(r.n_pos, r.n_reviews, prior_pos, s.sentiment_prior_strength)
            comps["sentiment"] = {"value": round(share, 4), "raw": round(r.n_pos / r.n_reviews, 4), "weight": s.w_sentiment}
            expl.append(
                f"{r.n_pos} of {r.n_reviews} analysed reviews are positive "
                f"({100 * r.n_pos / r.n_reviews:.0f}% raw, {100 * share:.0f}% after small-sample shrinkage)."
            )
            conf_parts.append(r.n_reviews / (r.n_reviews + 10))

        if r.recent_share is not None:
            comps["recency"] = {"value": round(r.recent_share, 4), "weight": s.w_recency}
            expl.append(f"{100 * r.recent_share:.0f}% of dated reviews fall inside the last {s.recency_window_days} days of the data.")
        else:
            expl.append("Recency not used: the review source provides no dates.")

        o.visibility_percentile = None
        if comps:
            total_w = sum(c["weight"] for c in comps.values())
            o.popularity_score = round(100 * sum(c["value"] * c["weight"] for c in comps.values()) / total_w, 2)
            used = ", ".join(f"{k} {100 * c['weight'] / total_w:.0f}%" for k, c in comps.items())
            expl.insert(0, f"Score {o.popularity_score:.1f}/100 combines: {used}.")
        else:
            expl = ["Not ranked: no rating or analysed review text is available for this restaurant."]
        o.components, o.explanation = comps, expl
        o.confidence = round(sum(conf_parts) / len(conf_parts), 3) if conf_parts else None

    # ranks (ties broken by visibility)
    ranked = sorted((r for r in rows if out[r.restaurant_id].popularity_score is not None),
                    key=lambda r: (out[r.restaurant_id].popularity_score, visibility(r)), reverse=True)
    for i, r in enumerate(ranked, 1):
        out[r.restaurant_id].popularity_rank = i

    # ---- hidden gems
    for r in rows:
        o = out[r.restaurant_id]
        v = visibility(r)
        if v > 0:
            o.visibility_percentile = round(percentile_rank(v, [float(x) for x in vis_values]), 3)
        if r.n_reviews < s.gem_min_reviews:
            o.gem_status = "insufficient_evidence"
            o.gem_explanation = (f"Only {r.n_reviews} analysed review(s); at least {s.gem_min_reviews} are required "
                                 "before a hidden-gem judgement is made.")
            continue
        lb = wilson_lower_bound(r.n_pos, r.n_reviews)
        adj_rating = o.components.get("rating", {}).get("adjusted")
        if lb < s.gem_min_wilson_lb:
            o.gem_status, o.gem_explanation = "not_positive_enough", (
                f"Positive-sentiment lower bound {lb:.2f} is below the {s.gem_min_wilson_lb:.2f} threshold ({r.n_pos}/{r.n_reviews} positive).")
            continue
        if adj_rating is not None and adj_rating < s.gem_min_rating:
            o.gem_status, o.gem_explanation = "not_positive_enough", f"Adjusted rating {adj_rating:.2f} is below {s.gem_min_rating:.1f}."
            continue
        vp = o.visibility_percentile if o.visibility_percentile is not None else 0.0
        if vp > s.gem_max_visibility_pct:
            o.gem_status, o.gem_explanation = "not_low_visibility", (
                f"Well known: more ratings than {100 * vp:.0f}% of restaurants with data, so not a hidden gem.")
            continue
        rating_part = (adj_rating - 1) / 4 if adj_rating is not None else lb
        o.hidden_gem_score = round(100 * (0.60 * lb + 0.25 * rating_part + 0.15 * (1 - vp)), 2)
        o.gem_status = "qualified"
        o.gem_explanation = (
            f"High positive sentiment (confidence-adjusted {lb:.2f} from {r.n_pos}/{r.n_reviews} reviews) "
            f"with relatively low review visibility (more ratings than {100 * vp:.0f}% of restaurants with data)."
        )
    return out


# ------------------------------------------------------------------ database glue
def gather_inputs(db: Session, s: Settings | None = None, engine: str | None = None) -> list[RankInput]:
    from backend.services.sentiment_view import active_engine, sentiment_cols

    s = s or get_settings()
    model, label_col, _, _ = sentiment_cols(engine or active_engine(db))
    stats = {
        rid: (n, pos, neg, neu)
        for rid, n, pos, neg, neu in db.execute(
            select(
                Review.restaurant_id,
                func.count(Review.id),
                func.sum(case((label_col == "positive", 1), else_=0)),
                func.sum(case((label_col == "negative", 1), else_=0)),
                func.sum(case((label_col == "neutral", 1), else_=0)),
            )
            .join(model, model.review_id == Review.id)
            .where(Review.restaurant_id.is_not(None), Review.match_status.in_(VALID_REVIEW_STATUSES))
            .group_by(Review.restaurant_id)
        )
    }
    # recency, only for restaurants with dated reviews
    newest = db.scalar(select(func.max(Review.reviewed_at)))
    recent: dict[int, float] = {}
    if newest is not None:
        cutoff = newest - timedelta(days=s.recency_window_days)
        for rid, dated, recent_n in db.execute(
            select(Review.restaurant_id, func.count(Review.id), func.sum(case((Review.reviewed_at >= cutoff, 1), else_=0)))
            .where(Review.restaurant_id.is_not(None), Review.reviewed_at.is_not(None), Review.match_status.in_(VALID_REVIEW_STATUSES))
            .group_by(Review.restaurant_id)
        ):
            recent[rid] = (recent_n or 0) / dated if dated else None

    rows = []
    for r in db.scalars(select(Restaurant)):
        n, pos, neg, neu = stats.get(r.id, (0, 0, 0, 0))
        rows.append(RankInput(r.id, r.rating, r.rating_count, n or 0, int(pos or 0), int(neg or 0), int(neu or 0), recent.get(r.id)))
    return rows


def recompute_rankings(db: Session, s: Settings | None = None, engine: str | None = None) -> int:
    rows = gather_inputs(db, s, engine)
    results = compute_rankings(rows, s)
    now = utcnow()
    existing = {rk.restaurant_id: rk for rk in db.scalars(select(RestaurantRanking))}
    for rid, o in results.items():
        rk = existing.get(rid) or RestaurantRanking(restaurant_id=rid)
        rk.popularity_score, rk.popularity_rank = o.popularity_score, o.popularity_rank
        rk.hidden_gem_score, rk.gem_status, rk.confidence = o.hidden_gem_score, o.gem_status, o.confidence
        rk.visibility_percentile, rk.components = o.visibility_percentile, o.components
        rk.explanation, rk.gem_explanation, rk.computed_at = o.explanation, o.gem_explanation, now
        db.add(rk)
    db.commit()
    return len(results)
