from __future__ import annotations

from collections import Counter
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.api.deps import like_escape
from backend.config import get_settings
from backend.database.base import iso, utcnow
from backend.database.db import get_db
from backend.integrations.google_places import GooglePlacesClient, GooglePlacesError
from backend.models import AspectSentiment, BertSentimentResult, DiscoveryHistory, Restaurant, RestaurantRanking, RestaurantSourceId, Review, SentimentResult
from backend.nlp.sentiment import score_text
from backend.schemas import CompareRequest, Page, RestaurantDetail, RestaurantSummary
from backend.services import queries as Q
from backend.services.neighborhoods import NEIGHBORHOODS, label_for
from backend.services.constants import VALID_REVIEW_STATUSES
from backend.services.filters import Filters, Selection, filter_params, select_restaurants
from backend.services.sentiment_view import active_engine, engine_info, sentiment_cols

router = APIRouter(prefix="/api/restaurants", tags=["restaurants"])


def _summaries(db: Session, restaurants: list[Restaurant], counts: dict | None = None) -> list[dict]:
    if counts is None:
        counts = Q.sentiment_counts(db, [r.id for r in restaurants]) if restaurants else {}
    return [Q.summary_dict(r, counts.get(r.id)) for r in restaurants]


def _base_query():
    return (
        select(Restaurant)
        .outerjoin(RestaurantRanking, RestaurantRanking.restaurant_id == Restaurant.id)
        .options(joinedload(Restaurant.location), joinedload(Restaurant.ranking))
    )


def _get_or_404(db: Session, rid: int) -> Restaurant:
    r = Q.load_restaurant(db, rid)
    if r is None:
        raise HTTPException(404, f"Restaurant {rid} not found")
    return r


@router.get("", response_model=Page[RestaurantSummary], summary="List and filter restaurants (all filters are shared with the map layers and charts)")
def list_restaurants(
    f: Filters = Depends(filter_params),
    sort: Literal["name", "popularity", "rating", "reviews", "gem"] = "popularity",
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    sel = select_restaurants(db, f, sort=sort)
    page = sel.restaurants[offset:offset + limit]
    return {"total": len(sel.restaurants), "limit": limit, "offset": offset, "items": _summaries(db, page, sel.counts)}


@router.get("/search", summary="Search suggestions (restaurants, neighbourhoods, cuisines)")
def search_suggestions(q: str = Query(..., min_length=1, max_length=100), limit: int = Query(8, ge=1, le=20), db: Session = Depends(get_db)):
    ql = q.strip().lower()
    out: list[dict] = []
    for n in NEIGHBORHOODS:
        if ql in n.label.lower():
            out.append({"type": "neighborhood", "label": n.label, "value": n.key})
    cuisine_counts: Counter = Counter()
    for (c,) in db.execute(select(Restaurant.cuisines).where(Restaurant.cuisines.is_not(None))):
        cuisine_counts.update(x for x in c.split(";") if x)
    out += [{"type": "cuisine", "label": c.title(), "value": c} for c, _ in cuisine_counts.most_common() if ql in c][:4]
    term = f"%{like_escape(ql)}%"
    rows = db.execute(
        select(Restaurant.id, Restaurant.name, Restaurant.neighborhood)
        .where(func.lower(Restaurant.name).like(term, escape="\\"))
        .order_by(func.length(Restaurant.name), Restaurant.name)
        .limit(limit)
    ).all()
    out += [{"type": "restaurant", "label": n, "value": str(i), "restaurant_id": i, "neighborhood_label": label_for(h)} for i, n, h in rows]
    return {"query": q, "suggestions": out[:limit + 6]}


@router.get("/popular", summary="Popular restaurants (never labelled 'trending' without dated data)")
def popular(limit: int = Query(25, ge=1, le=200), f: Filters = Depends(filter_params), db: Session = Depends(get_db)):
    sel = select_restaurants(db, f, sort="popularity")
    rows = [r for r in sel.restaurants if r.ranking and r.ranking.popularity_score is not None]
    rows.sort(key=lambda r: r.ranking.popularity_rank if r.ranking.popularity_rank is not None else 10**9)
    rows = rows[:limit]

    dated = db.scalar(select(func.count(Review.id)).where(Review.reviewed_at.is_not(None), *Q.valid_review_filter())) or 0
    month_counts: Counter = Counter()
    if dated:  # grouped in Python so the query stays portable to PostgreSQL
        for (ts,) in db.execute(select(Review.reviewed_at).where(Review.reviewed_at.is_not(None), *Q.valid_review_filter())):
            month_counts[ts.strftime("%Y-%m")] += 1
    months = sorted(month_counts.items())
    trending = dated >= 100 and len(months) >= 6
    return {
        "label": "Trending" if trending else "Popular Restaurants",
        "trending_available": trending,
        "basis_note": (
            "Trends are computed from dated reviews." if trending else
            "Rankings reflect aggregate ratings and review sentiment from historical data. No (or too few) dated reviews "
            "are available, so FoodSpotter does not claim anything is currently trending."
        ),
        "dated_reviews": dated,
        "time_trend": [{"month": m, "reviews": n} for m, n in months] if trending else [],
        "items": _summaries(db, rows, sel.counts),
    }


@router.get("/hidden-gems", summary="Hidden gems: positive feedback, low visibility, enough evidence")
def hidden_gems(limit: int = Query(25, ge=1, le=200), f: Filters = Depends(filter_params), db: Session = Depends(get_db)):
    s = get_settings()
    sel = select_restaurants(db, f, sort="gem")
    scoped = [r for r in sel.restaurants if r.ranking]
    status_counts = dict(Counter(r.ranking.gem_status for r in scoped))
    rows = [r for r in scoped if r.ranking.gem_status == "qualified"][:limit]
    items = _summaries(db, rows, sel.counts)
    asp = Q.aspect_scores_by_restaurant(db, [r.id for r in rows]) if rows else {}
    for it, r in zip(items, rows):
        it["gem_explanation"] = r.ranking.gem_explanation
        it["visibility_percentile"] = r.ranking.visibility_percentile
        c = sel.counts.get(r.id, {})
        n, pos = c.get("n", 0), c.get("positive", 0)
        from backend.services.ranking import wilson_lower_bound

        it["evidence"] = {
            "analysed_reviews": n, "positive_reviews": pos, "negative_reviews": c.get("negative", 0), "neutral_reviews": c.get("neutral", 0),
            "positive_share": round(pos / n, 3) if n else None,
            "positive_lower_bound": round(wilson_lower_bound(pos, n), 3) if n else None,
            "adjusted_rating": (r.ranking.components or {}).get("rating", {}).get("adjusted"),
            "praised_aspects": [a["label"] for a in sorted(asp.get(r.id, {}).values(), key=lambda a: -(a["positive_share"] or 0))
                                if a["sufficient_evidence"] and (a["positive_share"] or 0) >= 0.6][:3],
        }
    return {
        "criteria": {
            "min_analysed_reviews": s.gem_min_reviews,
            "min_positive_confidence_bound": s.gem_min_wilson_lb,
            "max_visibility_percentile": s.gem_max_visibility_pct,
            "min_adjusted_rating": s.gem_min_rating,
        },
        "sentiment_engine": sel.engine,
        "status_counts": status_counts,
        "insufficient_evidence_count": status_counts.get("insufficient_evidence", 0),
        "items": items,
    }


@router.get("/newly-discovered", summary="Establishments first seen by FoodSpotter after the baseline run")
def newly_discovered(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    baseline = db.scalar(select(DiscoveryHistory).where(DiscoveryHistory.is_baseline.is_(True)).limit(1))
    last = db.scalar(select(DiscoveryHistory).order_by(DiscoveryHistory.id.desc()).limit(1))
    running = db.scalar(select(func.count()).select_from(DiscoveryHistory).where(DiscoveryHistory.status == "running")) or 0
    rows = db.scalars(
        _base_query().join(DiscoveryHistory, DiscoveryHistory.id == Restaurant.discovery_run_id)
        .where(DiscoveryHistory.is_baseline.is_(False)).order_by(Restaurant.first_discovered_at.desc()).limit(limit)
    ).unique().all()
    return {
        "baseline_established": baseline is not None,
        "baseline_at": iso(baseline.finished_at) if baseline else None,
        "refresh_running": bool(running),
        "last_run": None if last is None else {
            "id": last.id, "source": last.source, "status": last.status, "started_at": iso(last.started_at), "finished_at": iso(last.finished_at),
            "new": last.new_count, "found": last.found_count, "flagged": last.flagged_count, "errors": last.errors or [],
        },
        "note": ("'Newly discovered' means FoodSpotter first saw this place in a refresh after its initial baseline scan. "
                 "It does NOT mean the restaurant recently opened – no opening dates are verified."),
        "items": _summaries(db, rows),
    }


@router.post("/compare", summary="Compare two or three restaurants")
def compare(body: CompareRequest, db: Session = Depends(get_db)):
    rests = []
    for rid in body.ids:
        rests.append(_get_or_404(db, rid))
    counts = Q.sentiment_counts(db, body.ids)
    aspects = Q.aspect_scores_by_restaurant(db, body.ids)
    items = []
    for r in rests:
        d = Q.summary_dict(r, counts.get(r.id))
        c = counts.get(r.id)
        d["sentiment"] = {**c, "distribution_share": {k: round(c[k] / c["n"], 3) for k in ("positive", "negative", "neutral")}} if c else None
        d["aspects"] = {k: v for k, v in aspects[r.id].items()}
        d["ranking_explanation"] = r.ranking.explanation if r.ranking else []
        items.append(d)
    return {"items": items, "min_aspect_mentions": get_settings().min_aspect_mentions}


@router.get("/{restaurant_id}", response_model=RestaurantDetail, summary="Restaurant details")
def get_restaurant(restaurant_id: int, db: Session = Depends(get_db)):
    return Q.detail_dict(db, _get_or_404(db, restaurant_id))


def _bert_dict(b: BertSentimentResult | None) -> dict | None:
    if b is None:
        return None
    return {"label": b.label, "confidence": b.confidence, "probabilities": {"negative": b.p_negative, "neutral": b.p_neutral, "positive": b.p_positive},
            "star_probabilities": b.star_probs, "predicted_stars": b.predicted_stars, "expected_stars": b.expected_stars,
            "truncated": b.truncated, "model_id": b.model_id, "model_revision": b.model_revision}


@router.get("/{restaurant_id}/reviews", summary="Genuine historical reviews with BERT and VADER-baseline sentiment")
def get_reviews(
    restaurant_id: int,
    sentiment: Optional[Literal["positive", "negative", "neutral"]] = Query(None, description="Filter by the active engine's label"),
    aspect: Optional[Literal["food", "service", "ambience", "affordability", "hygiene", "waiting_time"]] = Query(None, description="Only reviews that mention this aspect"),
    sort: Literal["rating_desc", "rating_asc", "most_positive", "most_negative", "most_confident"] = "most_positive",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    _get_or_404(db, restaurant_id)
    engine = active_engine(db)
    model, label_col, pol_col, conf_col = sentiment_cols(engine)
    where = [Review.restaurant_id == restaurant_id, Review.match_status.in_(VALID_REVIEW_STATUSES)]
    if sentiment:
        where.append(label_col == sentiment)
    if aspect:
        where.append(Review.id.in_(select(AspectSentiment.review_id).where(AspectSentiment.aspect == aspect)))
    base = select(Review).outerjoin(model, model.review_id == Review.id).where(*where)
    total = db.scalar(select(func.count()).select_from(base.with_only_columns(Review.id).subquery())) or 0
    order = {
        "rating_desc": Review.rating.desc().nulls_last(), "rating_asc": Review.rating.asc().nulls_last(),
        "most_positive": pol_col.desc().nulls_last(), "most_negative": pol_col.asc().nulls_last(),
        "most_confident": (conf_col if conf_col is not None else func.abs(pol_col)).desc().nulls_last(),
    }[sort]
    revs = db.scalars(base.options(joinedload(Review.sentiment), joinedload(Review.bert), joinedload(Review.aspects)).order_by(order, Review.id).limit(limit).offset(offset)).unique().all()
    items = []
    for rv in revs:
        bert, vader = _bert_dict(rv.bert), ({"label": rv.sentiment.label, "compound": rv.sentiment.compound} if rv.sentiment else None)
        if engine == "bert" and bert:
            active = {"engine": "bert", "label": bert["label"], "confidence": bert["confidence"], "compound": rv.bert.polarity}
        elif vader:
            active = {"engine": "vader", "label": vader["label"], "confidence": None, "compound": vader["compound"]}
        else:
            active = None
        items.append({
            "id": rv.id, "text": rv.text, "rating": rv.rating, "reviewed_at": iso(rv.reviewed_at),
            "date_note": None if rv.reviewed_at else "Review date not provided by the source.",
            "source": rv.source, "source_label": Q.REVIEW_SOURCE_LABELS.get(rv.source, rv.source),
            "match_status": rv.match_status, "match_confidence": rv.match_confidence,
            "sentiment": active, "bert": bert, "vader": vader,
            "aspects": [{"aspect": a.aspect, "label": a.label, "evidence": a.evidence} for a in rv.aspects],
        })
    return {"total": total, "limit": limit, "offset": offset, "engine": engine, "items": items}


@router.get("/{restaurant_id}/sentiment", summary="Review sentiment distribution (active engine) with BERT vs VADER comparison")
def get_sentiment(restaurant_id: int, db: Session = Depends(get_db)):
    r = _get_or_404(db, restaurant_id)
    info = engine_info(db)
    engine = info["active"]
    c = Q.sentiment_counts(db, [restaurant_id], engine=engine).get(restaurant_id)
    if not c:
        return {"restaurant_id": restaurant_id, "analysed_reviews": 0, "available": False, "engine": info,
                "message": "No verified reviews have been analysed for this restaurant."}
    n = c["n"]
    model, label_col, pol_col, conf_col = sentiment_cols(engine)
    valid = (Review.restaurant_id == restaurant_id, Review.match_status.in_(VALID_REVIEW_STATUSES))
    bins = [-1.0, -0.6, -0.2, 0.2, 0.6, 1.0001]
    comp = [v for (v,) in db.execute(select(pol_col).join(Review, Review.id == model.review_id).where(*valid))]
    hist = [sum(1 for v in comp if bins[i] <= v < bins[i + 1]) for i in range(5)]
    avg_conf = None
    if conf_col is not None:
        avg_conf = db.scalar(select(func.avg(conf_col)).join(Review, Review.id == model.review_id).where(*valid))
    other = "vader" if engine == "bert" else "bert"
    oc = Q.sentiment_counts(db, [restaurant_id], engine=other).get(restaurant_id)
    pair = db.execute(
        select(SentimentResult.label, BertSentimentResult.label, func.count())
        .select_from(Review).join(SentimentResult, SentimentResult.review_id == Review.id).join(BertSentimentResult, BertSentimentResult.review_id == Review.id)
        .where(*valid).group_by(SentimentResult.label, BertSentimentResult.label)
    ).all()
    both = sum(k for _, _, k in pair)
    agree = sum(k for a, b, k in pair if a == b)
    return {
        "restaurant_id": restaurant_id, "available": True, "analysed_reviews": n, "engine": info,
        "distribution": {"positive": c["positive"], "negative": c["negative"], "neutral": c["neutral"]},
        "share": {k: round(c[k] / n, 3) for k in ("positive", "negative", "neutral")},
        "mean_compound": c["mean_compound"],
        "mean_confidence": round(float(avg_conf), 4) if avg_conf is not None else None,
        "histogram": [{"range": lab, "count": h} for lab, h in zip(["very negative", "negative", "neutral", "positive", "very positive"], hist)],
        "model": info["active_label"],
        "comparison": {
            "other_engine": other,
            "other_distribution": ({"positive": oc["positive"], "negative": oc["negative"], "neutral": oc["neutral"], "n": oc["n"]} if oc else None),
            "reviews_with_both": both, "agreement": round(agree / both, 3) if both else None,
            "note": "Agreement is how often the two models give the same label. It is not accuracy: no ground truth is involved.",
        },
        "note": "Sentiment is computed from review text and can differ from the star rating.",
        "star_rating": r.rating,
        "themes": Q.themes_for_restaurant(db, restaurant_id, engine=engine),
    }


@router.get("/{restaurant_id}/aspects", summary="Aspect-based sentiment")
def get_aspects(restaurant_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, restaurant_id)
    return {"restaurant_id": restaurant_id, **Q.aspects_for_restaurant(db, restaurant_id)}


@router.get("/{restaurant_id}/live-reviews", summary="Currently available Google reviews (optional, not stored)")
def live_reviews(restaurant_id: int, db: Session = Depends(get_db)):
    s = get_settings()
    r = _get_or_404(db, restaurant_id)
    base = {"restaurant_id": restaurant_id, "source": "google_places", "stored": False}
    if not s.google_places_api_key:
        return {**base, "configured": False, "reviews": [],
                "message": "Live reviews are disabled: no Google Places API key is configured on the server."}
    try:
        client = GooglePlacesClient(s.google_places_api_key, min_interval=s.google_min_interval_seconds)
        pid = next((x.source_id for x in r.source_ids if x.source == "google_place_id"), None)
        if pid is None:
            match = client.find_matching_place(r.name, r.location.latitude, r.location.longitude)
            if match is None:
                return {**base, "configured": True, "reviews": [],
                        "message": "No Google place could be verified for this restaurant (name and location must both agree)."}
            pid = match["id"]
            db.add(RestaurantSourceId(restaurant_id=r.id, source="google_place_id", source_id=pid, role="alias"))
            db.commit()
        data = client.details(pid, with_reviews=True)
    except GooglePlacesError as e:
        raise HTTPException(429 if e.quota else 502, str(e)) from e
    reviews = []
    for rv in (data.get("reviews") or [])[:5]:  # the API returns at most five; we do not try to get more
        text = ((rv.get("text") or rv.get("originalText") or {}).get("text") or "").strip()
        sc = score_text(text) if text else None
        reviews.append({
            "rating": rv.get("rating"), "text": text, "published": rv.get("publishTime"),
            "relative_time": rv.get("relativePublishTimeDescription"),
            "author": (rv.get("authorAttribution") or {}).get("displayName"),
            "author_url": (rv.get("authorAttribution") or {}).get("uri"),
            "sentiment": {"label": sc.label, "compound": sc.compound, "engine": "vader"} if sc else None,
        })
    return {**base, "configured": True, "reviews": reviews, "google_rating": data.get("rating"),
            "google_rating_count": data.get("userRatingCount"), "google_maps_uri": data.get("googleMapsUri"),
            "attribution": "Reviews and ratings © Google. Fetched live, shown as returned (max. 5), not stored and not used in rankings.",
            "fetched_at": utcnow().isoformat() + "Z"}
