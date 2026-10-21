"""Which sentiment engine feeds the statistics, rankings and charts?

* "bert"  – BertSentimentResult rows (label, confidence, polarity = P(pos) - P(neg))
* "vader" – SentimentResult rows, the lexicon baseline (label, compound)

`active_engine` picks BERT only when it really covers the matched reviews (default >= 95 %), so figures are never a
silent mix of two models. The other engine's results stay available for side-by-side comparison.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import BertSentimentResult, Review, SentimentResult
from backend.nlp.bert import MODEL_CARD, availability
from backend.nlp.sentiment import MODEL_EXTENDED
from backend.services.constants import VALID_REVIEW_STATUSES

VADER_LABEL = "VADER lexicon (baseline) + restaurant-domain word list"

# In-process state of the background BERT job (single-process app).
JOB: dict = {"running": False, "last": None}


def sentiment_cols(engine: str):
    """-> (result model, label column, polarity column, confidence column or None)."""
    if engine == "bert":
        return BertSentimentResult, BertSentimentResult.label, BertSentimentResult.polarity, BertSentimentResult.confidence
    return SentimentResult, SentimentResult.label, SentimentResult.compound, None


def coverage(db: Session) -> dict:
    valid = (Review.restaurant_id.is_not(None), Review.match_status.in_(VALID_REVIEW_STATUSES))
    total = db.scalar(select(func.count(Review.id)).where(*valid)) or 0
    vader_n = db.scalar(select(func.count(Review.id)).join(SentimentResult, SentimentResult.review_id == Review.id).where(*valid)) or 0
    bert_n = db.scalar(select(func.count(Review.id)).join(BertSentimentResult, BertSentimentResult.review_id == Review.id).where(*valid)) or 0
    return {"matched_reviews": total, "vader": vader_n, "bert": bert_n,
            "bert_share": round(bert_n / total, 4) if total else 0.0}


def active_engine(db: Session) -> str:
    s = get_settings()
    want = (s.sentiment_engine or "auto").lower()
    if want in ("bert", "vader"):
        return want
    cov = coverage(db)
    if cov["matched_reviews"] and cov["bert"] and cov["bert"] >= s.bert_auto_min_coverage * cov["matched_reviews"]:
        return "bert"
    return "vader"


def engine_info(db: Session) -> dict:
    s = get_settings()
    cov = coverage(db)
    active = active_engine(db)
    avail = availability()
    if active == "bert":
        why = "BERT predictions cover the matched reviews." if (s.sentiment_engine or "auto").lower() == "auto" else "BERT was selected with SENTIMENT_ENGINE=bert."
    elif (s.sentiment_engine or "auto").lower() == "vader":
        why = "SENTIMENT_ENGINE=vader forces the baseline."
    elif cov["bert"]:
        why = (f"BERT has analysed {cov['bert']} of {cov['matched_reviews']} matched reviews "
               f"(needs {int(s.bert_auto_min_coverage * 100)}% to become the active engine); showing the VADER baseline.")
    elif (s.sentiment_engine or "auto").lower() == "vader":
        why = "SENTIMENT_ENGINE=vader forces the baseline."
    else:
        why = "No BERT predictions have been generated yet; showing the VADER baseline."
    return {
        "active": active,
        "active_label": f"BERT ({MODEL_CARD['id']})" if active == "bert" else VADER_LABEL,
        "requested": (s.sentiment_engine or "auto").lower(),
        "reason": why,
        "coverage": cov,
        "job": {"running": JOB["running"], "last": JOB["last"]},
        "bert": {"model": MODEL_CARD, "model_id_configured": s.bert_model_id, "revision": s.bert_model_revision or None,
                 "packages_installed": avail["packages_installed"], "unavailable_reason": avail["reason"],
                 "max_tokens": s.bert_max_length, "predictions_stored": cov["bert"],
                 "run_in_this_database": cov["bert"] > 0},
        "vader": {"model": MODEL_EXTENDED, "label": VADER_LABEL, "predictions_stored": cov["vader"]},
    }
