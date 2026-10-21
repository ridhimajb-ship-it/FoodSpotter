"""Glue: run the NLP pipeline over stored reviews, then recompute rankings."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import AspectSentiment, BertSentimentResult, Review, SentimentResult
from backend.nlp.aspects import analyze_review_aspects
from backend.nlp.sentiment import MODEL_EXTENDED, score_text
from backend.nlp.bert import BertSentimentModel, BertUnavailable
from backend.services.constants import VALID_REVIEW_STATUSES
from backend.services.ranking import recompute_rankings

BATCH = 500


def run_nlp(db: Session, force: bool = False) -> dict:
    """Analyse every review that has no sentiment result yet (or all of them when force=True)."""
    if force:
        db.execute(delete(AspectSentiment))
        db.execute(delete(SentimentResult))
        db.commit()
    q = select(Review).outerjoin(SentimentResult, SentimentResult.review_id == Review.id).where(SentimentResult.review_id.is_(None))
    analysed = aspect_rows = 0
    batch = db.scalars(q.limit(BATCH)).all()
    while batch:
        for rv in batch:
            sc = score_text(rv.text, extended=True)
            db.add(SentimentResult(review_id=rv.id, compound=sc.compound, pos=sc.pos, neu=sc.neu, neg=sc.neg, label=sc.label, model=MODEL_EXTENDED))
            for m in analyze_review_aspects(rv.text, extended=True):
                db.add(AspectSentiment(review_id=rv.id, aspect=m.aspect, label=m.label, score=m.score, evidence=m.evidence))
                aspect_rows += 1
            analysed += 1
        db.commit()
        batch = db.scalars(q.limit(BATCH)).all()
    return {"reviews_analysed": analysed, "aspect_results": aspect_rows, "model": MODEL_EXTENDED}


def run_bert(db: Session, model: BertSentimentModel | None = None, force: bool = False, limit: int | None = None, chunk: int = 128) -> dict:
    """Run the BERT model over matched reviews that have no BERT result yet.

    Never invents output: if the model cannot run (packages missing, weights not downloadable, ...) nothing is written and
    the reason is returned, so the VADER baseline stays the active engine.
    """
    model = model or BertSentimentModel()
    if force:
        db.execute(delete(BertSentimentResult))
        db.commit()
    q = (select(Review).outerjoin(BertSentimentResult, BertSentimentResult.review_id == Review.id)
         .where(BertSentimentResult.review_id.is_(None), Review.restaurant_id.is_not(None), Review.match_status.in_(VALID_REVIEW_STATUSES))
         .order_by(Review.id))
    done = truncated = 0
    status, reason = "ok", None
    while limit is None or done < limit:
        take = chunk if limit is None else min(chunk, limit - done)
        batch = db.scalars(q.limit(take)).all()
        if not batch:
            break
        try:
            preds = model.predict([rv.text for rv in batch])
        except BertUnavailable as e:
            status, reason = ("unavailable" if done == 0 else "partial"), str(e)
            break
        for rv, p in zip(batch, preds):
            db.add(BertSentimentResult(
                review_id=rv.id, label=p.label, confidence=p.confidence, p_negative=p.p_negative, p_neutral=p.p_neutral,
                p_positive=p.p_positive, polarity=p.polarity, star_probs=list(p.star_probs), expected_stars=p.expected_stars,
                predicted_stars=p.predicted_stars, truncated=p.truncated, model_id=model.model_id, model_revision=model.revision))
            truncated += int(bool(p.truncated))
        db.commit()
        done += len(batch)
    return {"status": status, "reason": reason, "reviews_analysed": done, "truncated_reviews": truncated, "model_id": model.model_id}


def refresh_analytics(db: Session, force_nlp: bool = False, bert: bool | None = None) -> dict:
    """VADER baseline + aspects always; BERT only when enabled (ENABLE_BERT) or requested; then rankings."""
    nlp = run_nlp(db, force=force_nlp)
    if bert if bert is not None else get_settings().enable_bert:
        nlp["bert"] = run_bert(db, force=force_nlp)
    nlp["restaurants_ranked"] = recompute_rankings(db)
    return nlp
