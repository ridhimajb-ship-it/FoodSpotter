"""One set of filters shared by the restaurant list, rankings, map layers and the insights charts.

SQL handles the cheap filters (text, area, cuisine, rating, price, gems). Review-derived filters are applied afterwards
from the per-restaurant statistics of the *active* sentiment engine:

* min_reviews  – at least N analysed (matched) reviews
* sentiment    – the restaurant's dominant review sentiment (the label with the most reviews; ties match nothing)
* aspect       – at least `min_aspect_mentions` reviews mention that aspect, i.e. enough evidence to show a score
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Literal, Optional

from fastapi import Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from backend.api.deps import like_escape
from backend.config import get_settings
from backend.models import AspectSentiment, Restaurant, RestaurantRanking, Review
from backend.nlp.aspects import ASPECTS
from backend.services import queries as Q
from backend.services.constants import VALID_REVIEW_STATUSES
from backend.services.neighborhoods import NEIGHBORHOODS
from backend.services.sentiment_view import active_engine

SENTIMENTS = ("positive", "neutral", "negative")


@dataclass(frozen=True)
class Filters:
    q: Optional[str] = None
    neighborhood: Optional[str] = None
    cuisine: Optional[str] = None
    min_rating: Optional[float] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    min_popularity: Optional[float] = None
    hidden_gems_only: bool = False
    has_reviews: bool = False
    min_reviews: int = 0
    sentiment: Optional[str] = None
    aspect: Optional[str] = None

    def without(self, *names: str) -> "Filters":
        return replace(self, **{n: getattr(Filters(), n) for n in names})

    def active(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v not in (None, False, 0, "")}
        return d


def filter_params(
    q: Optional[str] = Query(None, max_length=100, description="Name, neighbourhood or cuisine"),
    neighborhood: Optional[str] = Query(None, max_length=64),
    cuisine: Optional[str] = Query(None, max_length=64),
    min_rating: Optional[float] = Query(None, ge=0, le=5),
    price_min: Optional[int] = Query(None, ge=0, le=100000, description="Historical approx. cost for two (INR)"),
    price_max: Optional[int] = Query(None, ge=0, le=100000),
    min_popularity: Optional[float] = Query(None, ge=0, le=100),
    hidden_gems_only: bool = False,
    has_reviews: bool = False,
    min_reviews: int = Query(0, ge=0, le=100000, description="Minimum analysed reviews"),
    sentiment: Optional[Literal["positive", "neutral", "negative"]] = Query(None, description="Dominant review sentiment"),
    aspect: Optional[Literal["food", "service", "ambience", "affordability", "hygiene", "waiting_time"]] = Query(None, description="Aspect with enough review evidence"),
) -> Filters:
    return Filters(q=(q or "").strip() or None, neighborhood=neighborhood or None, cuisine=(cuisine or "").strip().lower() or None,
                   min_rating=min_rating, price_min=price_min, price_max=price_max, min_popularity=min_popularity,
                   hidden_gems_only=hidden_gems_only, has_reviews=has_reviews, min_reviews=min_reviews, sentiment=sentiment, aspect=aspect)


@dataclass
class Selection:
    restaurants: list[Restaurant]
    counts: dict[int, dict]
    engine: str
    aspect_mentions: dict[int, int] = field(default_factory=dict)

    @property
    def ids(self) -> list[int]:
        return [r.id for r in self.restaurants]


def _chunks(seq: list, n: int = 500) -> Iterable[list]:
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def aspect_mention_counts(db: Session, ids: list[int], aspect: str) -> dict[int, int]:
    out: dict[int, int] = {}
    for part in _chunks(ids):
        for rid, n in db.execute(
            select(Review.restaurant_id, func.count(AspectSentiment.id))
            .join(Review, Review.id == AspectSentiment.review_id)
            .where(AspectSentiment.aspect == aspect, Review.restaurant_id.in_(part), Review.match_status.in_(VALID_REVIEW_STATUSES))
            .group_by(Review.restaurant_id)
        ):
            out[rid] = n
    return out


def dominant(c: dict) -> Optional[str]:
    if not c or not c.get("n"):
        return None
    ranked = sorted(((c[k], k) for k in SENTIMENTS), reverse=True)
    return ranked[0][1] if ranked[0][0] > ranked[1][0] else None


def select_restaurants(db: Session, f: Filters, sort: str = "popularity", engine: Optional[str] = None) -> Selection:
    engine = engine or active_engine(db)
    stmt = (select(Restaurant).outerjoin(RestaurantRanking, RestaurantRanking.restaurant_id == Restaurant.id)
            .options(joinedload(Restaurant.location), joinedload(Restaurant.ranking)))
    if f.q:
        term = f"%{like_escape(f.q.lower())}%"
        hood_keys = [n.key for n in NEIGHBORHOODS if f.q.lower() in n.label.lower()]
        conds = [func.lower(Restaurant.name).like(term, escape="\\"), func.lower(Restaurant.cuisines).like(term, escape="\\")]
        if hood_keys:
            conds.append(Restaurant.neighborhood.in_(hood_keys))
        stmt = stmt.where(or_(*conds))
    if f.neighborhood:
        stmt = stmt.where(Restaurant.neighborhood == f.neighborhood)
    if f.cuisine:
        stmt = stmt.where(func.lower(Restaurant.cuisines).like(f"%{like_escape(f.cuisine)}%", escape="\\"))
    if f.min_rating is not None:
        stmt = stmt.where(Restaurant.rating >= f.min_rating)
    if f.price_min is not None:
        stmt = stmt.where(Restaurant.price_for_two >= f.price_min)
    if f.price_max is not None:
        stmt = stmt.where(Restaurant.price_for_two <= f.price_max)
    if f.min_popularity is not None:
        stmt = stmt.where(RestaurantRanking.popularity_score >= f.min_popularity)
    if f.hidden_gems_only:
        stmt = stmt.where(RestaurantRanking.gem_status == "qualified")
    if f.has_reviews:
        stmt = stmt.where(Restaurant.id.in_(select(Review.restaurant_id).where(*Q.valid_review_filter())))
    order = {
        "name": [func.lower(Restaurant.name)],
        "popularity": [RestaurantRanking.popularity_score.desc().nulls_last(), func.lower(Restaurant.name)],
        "rating": [Restaurant.rating.desc().nulls_last(), Restaurant.rating_count.desc().nulls_last()],
        "reviews": [Restaurant.rating_count.desc().nulls_last(), func.lower(Restaurant.name)],
        "gem": [RestaurantRanking.hidden_gem_score.desc().nulls_last(), func.lower(Restaurant.name)],
    }[sort]
    rows = list(db.scalars(stmt.order_by(*order).execution_options(populate_existing=True)).unique().all())
    counts = Q.sentiment_counts(db, engine=engine)  # every restaurant with analysed reviews; cheap single query
    mentions: dict[int, int] = {}
    if f.min_reviews:
        rows = [r for r in rows if counts.get(r.id, {}).get("n", 0) >= f.min_reviews]
    if f.sentiment:
        rows = [r for r in rows if dominant(counts.get(r.id, {})) == f.sentiment]
    if f.aspect:
        need = get_settings().min_aspect_mentions
        mentions = aspect_mention_counts(db, [r.id for r in rows], f.aspect)
        rows = [r for r in rows if mentions.get(r.id, 0) >= need]
    return Selection(rows, {r.id: counts[r.id] for r in rows if r.id in counts}, engine, mentions)
