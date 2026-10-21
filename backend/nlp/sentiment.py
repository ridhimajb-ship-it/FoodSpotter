"""Sentiment classification. VADER is the baseline; an extended-lexicon variant adds restaurant-domain terms.

Both variants are exposed so the evaluation script can report the effect of the extension rather than assume it.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from backend.config import get_settings

MODEL_BASELINE = "vader"
MODEL_EXTENDED = "vader+domain"

# Hand-written, transparent domain additions. Values follow VADER's -4..+4 scale.
# Only terms VADER does not already score are added (see _build).
DOMAIN_LEXICON: dict[str, float] = {
    "slow": -1.5, "overpriced": -2.5, "pricey": -1.5, "costly": -1.2, "bland": -1.8,
    "stale": -1.6, "undercooked": -2.0, "overcooked": -1.6, "greasy": -1.2, "soggy": -1.6,
    "tasteless": -2.2, "flavourless": -2.0, "flavorless": -2.0, "unhygienic": -2.5,
    "cramped": -1.2, "noisy": -1.0, "affordable": 1.5, "flavourful": 2.0, "flavorful": 2.0,
    "authentic": 1.4, "cozy": 1.6, "cosy": 1.6, "hygienic": 1.6, "prompt": 1.2, "unfriendly": -1.8,
    "inattentive": -1.8, "mediocre": -1.4, "underwhelming": -1.6, "overhyped": -1.6,
}


@lru_cache(maxsize=2)
def get_analyzer(extended: bool = False) -> SentimentIntensityAnalyzer:
    an = SentimentIntensityAnalyzer()
    if extended:
        for word, val in DOMAIN_LEXICON.items():
            an.lexicon.setdefault(word, val)
    return an


def label_from_compound(compound: float) -> str:
    s = get_settings()
    if compound >= s.sentiment_pos_threshold:
        return "positive"
    if compound <= s.sentiment_neg_threshold:
        return "negative"
    return "neutral"


@dataclass(frozen=True)
class SentimentScore:
    compound: float
    pos: float
    neu: float
    neg: float
    label: str
    model: str


def score_text(text: str, extended: bool = True) -> SentimentScore:
    scores = get_analyzer(extended).polarity_scores(text)
    return SentimentScore(
        compound=scores["compound"], pos=scores["pos"], neu=scores["neu"], neg=scores["neg"],
        label=label_from_compound(scores["compound"]),
        model=MODEL_EXTENDED if extended else MODEL_BASELINE,
    )
