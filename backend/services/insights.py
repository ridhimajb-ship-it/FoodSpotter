"""Everything the Overview / Sentiment Insights pages show, computed from the database for the *filtered* scope.

Rules: every number is counted from stored data; empty scopes return empty lists and zeros (never placeholders);
time trends exist only when reviews carry dates; BERT and VADER are never mixed inside one figure.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.base import iso
from backend.models import AspectSentiment, BertSentimentResult, ImportHistory, Restaurant, Review, SentimentResult
from backend.nlp.aspects import ASPECT_LABELS, ASPECTS
from backend.services import queries as Q
from backend.services.constants import VALID_REVIEW_STATUSES
from backend.services.filters import Filters, _chunks, select_restaurants
from backend.services.neighborhoods import NEIGHBORHOODS, label_for
from backend.services.ranking import wilson_lower_bound
from backend.services.sentiment_view import coverage, engine_info, sentiment_cols

VALID = (Review.restaurant_id.is_not(None), Review.match_status.in_(VALID_REVIEW_STATUSES))


def _share(a: int, n: int) -> Optional[float]:
    return round(a / n, 4) if n else None


def _tally(rows) -> dict:
    n = sum(c["n"] for c in rows)
    pos = sum(c["positive"] for c in rows)
    neu = sum(c["neutral"] for c in rows)
    neg = sum(c["negative"] for c in rows)
    return {"n": n, "positive": pos, "neutral": neu, "negative": neg,
            "positive_share": _share(pos, n), "neutral_share": _share(neu, n), "negative_share": _share(neg, n)}


def aspect_breakdown(db: Session, ids: list[int], reviews_analysed: int) -> list[dict]:
    need = get_settings().min_aspect_mentions
    per_rest: dict[str, dict[int, int]] = {a: defaultdict(int) for a in ASPECTS}
    totals = {a: Counter() for a in ASPECTS}
    for part in _chunks(ids):
        for rid, aspect, label, n in db.execute(
            select(Review.restaurant_id, AspectSentiment.aspect, AspectSentiment.label, func.count(AspectSentiment.id))
            .join(Review, Review.id == AspectSentiment.review_id)
            .where(Review.restaurant_id.in_(part), Review.match_status.in_(VALID_REVIEW_STATUSES))
            .group_by(Review.restaurant_id, AspectSentiment.aspect, AspectSentiment.label)
        ):
            if aspect in totals:
                totals[aspect][label] += n
                per_rest[aspect][rid] += n
    out = []
    for a in ASPECTS:
        t = totals[a]
        m = sum(t.values())
        out.append({
            "aspect": a, "label": ASPECT_LABELS[a], "mentions": m,
            "positive": t["positive"], "neutral": t["neutral"], "negative": t["negative"],
            "positive_share": _share(t["positive"], m), "negative_share": _share(t["negative"], m),
            "net_score": round((t["positive"] - t["negative"]) / m, 3) if m else None,
            "review_coverage": _share(m, reviews_analysed),  # share of analysed reviews that mention the aspect
            "restaurants_with_mentions": len(per_rest[a]),
            "restaurants_with_evidence": sum(1 for v in per_rest[a].values() if v >= need),
            "min_mentions_required": need,
        })
    return out


def _engine_pairs(db: Session, ids: list[int]) -> dict:
    pairs: Counter = Counter()
    for part in _chunks(ids):
        for a, b, n in db.execute(
            select(SentimentResult.label, BertSentimentResult.label, func.count())
            .select_from(Review).join(SentimentResult, SentimentResult.review_id == Review.id)
            .join(BertSentimentResult, BertSentimentResult.review_id == Review.id)
            .where(Review.restaurant_id.in_(part), Review.match_status.in_(VALID_REVIEW_STATUSES)).group_by(SentimentResult.label, BertSentimentResult.label)
        ):
            pairs[(a, b)] += n
    both = sum(pairs.values())
    agree = sum(n for (a, b), n in pairs.items() if a == b)
    return {"reviews_with_both": both, "agreement": _share(agree, both),
            "matrix": [{"vader": a, "bert": b, "count": n} for (a, b), n in sorted(pairs.items())]}


def time_trend(db: Session, ids: list[int], engine: str) -> dict:
    model, label_col, _, _ = sentiment_cols(engine)
    rows: list[tuple] = []
    for part in _chunks(ids):
        rows += db.execute(select(Review.reviewed_at, label_col).join(model, model.review_id == Review.id)
                           .where(Review.reviewed_at.is_not(None), Review.restaurant_id.in_(part), Review.match_status.in_(VALID_REVIEW_STATUSES))).all()
    months: dict[str, Counter] = defaultdict(Counter)
    for ts, label in rows:
        months[ts.strftime("%Y-%m")][label] += 1
    if len(rows) < 100 or len(months) < 6:
        return {"available": False, "dated_reviews": len(rows), "months": len(months),
                "reason": ("These reviews have no dates, so no time trend is shown." if not rows else
                           f"Only {len(rows)} dated reviews across {len(months)} month(s); a trend needs at least 100 reviews over 6 months.")}
    return {"available": True, "dated_reviews": len(rows), "months": len(months),
            "series": [{"month": m, "reviews": sum(c.values()), "positive_share": _share(c["positive"], sum(c.values()))} for m, c in sorted(months.items())]}


def pipeline_summary(db: Session) -> dict:
    """Unfiltered, whole-database counts for the WSMA pipeline strip and the Methodology page."""
    eng = engine_info(db)
    model, _, _, _ = sentiment_cols(eng["active"])
    status = dict(db.execute(select(Review.match_status, func.count()).group_by(Review.match_status)).all())
    valid_n = sum(v for k, v in status.items() if k in VALID_REVIEW_STATUSES)
    analysed = db.scalar(select(func.count(Review.id)).join(model, model.review_id == Review.id).where(*VALID)) or 0
    last = db.scalar(select(ImportHistory).order_by(ImportHistory.id.desc()).limit(1))
    rep = (last.report or {}) if last else {}
    osm = db.scalar(select(func.count(Restaurant.id)).where(Restaurant.primary_source == "osm")) or 0
    with_reviews = db.scalar(select(func.count(func.distinct(Review.restaurant_id))).where(*VALID)) or 0
    return {
        "restaurants_discovered": osm,
        "restaurants_total": db.scalar(select(func.count(Restaurant.id))) or 0,
        "restaurants_with_matched_reviews": with_reviews,
        "reviews_stored": sum(status.values()),
        "reviews_matched": valid_n,
        "reviews_by_match_status": status,
        "reviews_unresolved_stored": sum(v for k, v in status.items() if k not in VALID_REVIEW_STATUSES),
        "reviews_analysed": analysed,
        "dated_reviews": db.scalar(select(func.count(Review.id)).where(Review.reviewed_at.is_not(None), *VALID)) or 0,
        "engine": eng,
        "import": None if not last else {
            "filename": last.filename, "status": last.status, "finished_at": iso(last.finished_at),
            "rows_read": rep.get("rows_read"), "duplicate_listing_rows_removed": rep.get("duplicate_listing_rows_removed"),
            "rows_in_focus_areas": rep.get("rows_in_focus_areas"), "rows_outside_focus_areas": rep.get("rows_outside_focus_areas"),
            "listings_matched": rep.get("match_matched"), "listings_needs_review": rep.get("match_needs_review"),
            "listings_ambiguous": rep.get("match_ambiguous"), "listings_without_osm_record": rep.get("match_no_candidate"),
            "review_entries_parsed": rep.get("review_entries_parsed"), "malformed_review_entries": rep.get("malformed_review_entries"),
            "duplicate_reviews_skipped": rep.get("duplicate_reviews_skipped"),
            "reviews_unmatched_no_osm_record": rep.get("reviews_unmatched_no_osm_record"),
            "valid_reviews_imported": rep.get("valid_reviews_imported"),
            "restaurants_with_verified_reviews": rep.get("restaurants_with_verified_reviews"),
            "dataset_note": rep.get("dataset_note"),
        },
    }


def build_insights(db: Session, f: Filters) -> dict:
    s = get_settings()
    sel = select_restaurants(db, f)
    engine = sel.engine
    ids = sel.ids
    counts = sel.counts
    tally = _tally(list(counts.values()))
    with_reviews = sum(1 for i in ids if counts.get(i, {}).get("n"))

    # sentiment by neighbourhood / cuisine ignore their own filter so the comparison stays meaningful
    hood_sel = select_restaurants(db, f.without("neighborhood"), engine=engine)
    hoods: dict[str, dict] = {}
    for r in hood_sel.restaurants:
        h = hoods.setdefault(r.neighborhood or "unknown", {"restaurants": 0, "with_reviews": 0, "c": [], "pops": []})
        h["restaurants"] += 1
        c = hood_sel.counts.get(r.id)
        if c:
            h["with_reviews"] += 1
            h["c"].append(c)
        if r.ranking and r.ranking.popularity_score is not None:
            h["pops"].append(r.ranking.popularity_score)
    hood_items = []
    for k, h in hoods.items():
        t = _tally(h["c"])
        hood_items.append({"neighborhood": k, "label": label_for(k) if k != "unknown" else "Unknown", "selected": f.neighborhood == k,
                           "restaurants": h["restaurants"], "restaurants_with_reviews": h["with_reviews"], "reviews": t["n"],
                           "positive": t["positive"], "neutral": t["neutral"], "negative": t["negative"],
                           "positive_share": t["positive_share"], "negative_share": t["negative_share"],
                           "mean_popularity": round(sum(h["pops"]) / len(h["pops"]), 1) if h["pops"] else None})
    hood_items.sort(key=lambda d: (-d["reviews"], -d["restaurants"]))

    cui_sel = select_restaurants(db, f.without("cuisine"), engine=engine)
    cui: dict[str, list] = defaultdict(list)
    cui_n: Counter = Counter()
    for r in cui_sel.restaurants:
        for c in [x for x in (r.cuisines or "").split(";") if x]:
            cui_n[c] += 1
            if cui_sel.counts.get(r.id):
                cui[c].append(cui_sel.counts[r.id])
    cuisine_items = []
    for c, rows in cui.items():
        if len(rows) >= 3:
            t = _tally(rows)
            cuisine_items.append({"cuisine": c.title(), "value": c, "selected": f.cuisine == c, "restaurants": cui_n[c], "restaurants_with_reviews": len(rows),
                                  "reviews": t["n"], "positive_share": t["positive_share"], "negative_share": t["negative_share"]})
    cuisine_items.sort(key=lambda d: -d["reviews"])

    gem_rows = [r for r in ids and sel.restaurants if r.ranking and r.ranking.gem_status == "qualified"]
    gem_rows.sort(key=lambda r: -(r.ranking.hidden_gem_score or 0))
    asp = Q.aspect_scores_by_restaurant(db, [r.id for r in gem_rows[:8]]) if gem_rows else {}
    gems = []
    for r in gem_rows[:8]:
        c = counts.get(r.id, {})
        n, pos = c.get("n", 0), c.get("positive", 0)
        praised = [a["label"] for a in sorted(asp.get(r.id, {}).values(), key=lambda a: -(a["positive_share"] or 0))
                   if a["sufficient_evidence"] and (a["positive_share"] or 0) >= 0.6][:2]
        gems.append({**Q.summary_dict(r, c), "evidence": {
            "analysed_reviews": n, "positive_reviews": pos, "positive_share": _share(pos, n), "positive_lower_bound": round(wilson_lower_bound(pos, n), 3),
            "adjusted_rating": (r.ranking.components or {}).get("rating", {}).get("adjusted"), "ratings_on_record": r.rating_count,
            "visibility_percentile": r.ranking.visibility_percentile, "praised_aspects": praised},
            "explanation": r.ranking.gem_explanation})
    gem_status = dict(Counter(r.ranking.gem_status for r in sel.restaurants if r.ranking))

    cov = coverage(db)
    return {
        "filters_applied": f.active(),
        "engine": engine_info(db),
        "scope": {"restaurants": len(ids), "restaurants_with_reviews": with_reviews, "reviews_analysed": tally["n"],
                  "restaurants_in_database": db.scalar(select(func.count(Restaurant.id))) or 0},
        "sentiment": tally,
        "engine_comparison": _engine_pairs(db, ids) if cov["bert"] and cov["vader"] else None,
        "aspects": aspect_breakdown(db, ids, tally["n"]),
        "aspect_method": "Rule-based, clause-level aspect analysis (not BERT). An aspect is scored only with enough mentions.",
        "neighborhoods": hood_items,
        "cuisines": cuisine_items[:10],
        "hidden_gems": {"items": gems, "status_counts": gem_status,
                        "criteria": {"min_analysed_reviews": s.gem_min_reviews, "min_positive_confidence_bound": s.gem_min_wilson_lb,
                                     "max_visibility_percentile": s.gem_max_visibility_pct, "min_adjusted_rating": s.gem_min_rating}},
        "time_trend": time_trend(db, ids, engine),
        "pipeline": pipeline_summary(db),
    }
