"""Evidence-bound summaries and keyword themes. Every sentence is generated from aggregated review statistics."""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from backend.config import get_settings
from backend.nlp.aspects import ASPECT_LABELS, ASPECTS

_PHRASE = {
    "food": "the food", "service": "the service", "ambience": "the ambience",
    "affordability": "pricing and value", "hygiene": "cleanliness", "waiting_time": "waiting times",
}

# Words that carry little thematic information in restaurant reviews.
_THEME_STOP = frozenset(
    "place restaurant food good great nice really also order ordered got get go went one us like love loved "
    "try tried visit visited come came back time bit lot just well little much even still would could "
    "bangalore bengaluru eat eating ate day night people".split()
)


def aspect_stats(rows: Iterable[tuple[str, str]]) -> dict[str, dict]:
    """rows: (aspect, label) per review-aspect result -> per aspect counts, share, score and display flag."""
    min_mentions = get_settings().min_aspect_mentions
    counts: dict[str, Counter] = {a: Counter() for a in ASPECTS}
    for aspect, label in rows:
        if aspect in counts:
            counts[aspect][label] += 1
    out = {}
    for a in ASPECTS:
        c = counts[a]
        n = sum(c.values())
        out[a] = {
            "aspect": a,
            "label": ASPECT_LABELS[a],
            "mentions": n,
            "positive": c["positive"],
            "negative": c["negative"],
            "neutral": c["neutral"],
            "score": round((c["positive"] - c["negative"]) / n, 3) if n else None,
            "positive_share": round(c["positive"] / n, 3) if n else None,
            "negative_share": round(c["negative"] / n, 3) if n else None,
            "sufficient_evidence": n >= min_mentions,
            "min_mentions_required": min_mentions,
        }
    return out


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def build_summary(stats: dict[str, dict], n_reviews: int) -> dict:
    s = get_settings()
    if n_reviews < s.min_summary_reviews:
        return {
            "text": None, "basis_reviews": n_reviews, "praised": [], "criticized": [],
            "reason": f"Only {n_reviews} analysed review(s); at least {s.min_summary_reviews} are needed for a summary.",
        }
    usable = [v for v in stats.values() if v["sufficient_evidence"]]
    praised = sorted((v for v in usable if v["positive_share"] >= 0.6 and v["positive"] > v["negative"]),
                     key=lambda v: (-v["positive_share"], -v["mentions"]))
    criticized = sorted((v for v in usable if v["negative_share"] >= 0.25),
                        key=lambda v: (-v["negative_share"], -v["mentions"]))
    if not praised and not criticized:
        return {
            "text": None, "basis_reviews": n_reviews, "praised": [], "criticized": [],
            "reason": "No aspect has enough clear positive or negative mentions to summarise without over-reading the data.",
        }
    p = [_PHRASE[v["aspect"]] for v in praised[:3]]
    c = [_PHRASE[v["aspect"]] for v in criticized[:3]]
    if p and c:
        text = f"Reviews frequently praise {_join(p)}, while some mention problems with {_join(c)}."
    elif p:
        text = f"Reviews frequently praise {_join(p)}."
    else:
        text = f"Some reviews raise concerns about {_join(c)}."
    return {
        "text": text, "basis_reviews": n_reviews,
        "praised": [v["aspect"] for v in praised], "criticized": [v["aspect"] for v in criticized], "reason": None,
    }


def top_terms(lemma_lists: Iterable[list[str]], k: int = 10, min_count: int = 2) -> list[dict]:
    c: Counter = Counter()
    for lemmas in lemma_lists:
        # document frequency: count each term once per review
        c.update({t for t in lemmas if t.isalpha() and len(t) > 2 and t not in _THEME_STOP})
    return [{"term": t, "count": n} for t, n in c.most_common(k * 3) if n >= min_count][:k]


def distinctive_terms(pos_lists: list[list[str]], neg_lists: list[list[str]], k: int = 8) -> dict:
    """Terms over-represented in positive vs negative reviews (smoothed log-odds ratio)."""
    import math

    pos_c: Counter = Counter()
    neg_c: Counter = Counter()
    for l in pos_lists:
        pos_c.update({t for t in l if t.isalpha() and len(t) > 2 and t not in _THEME_STOP})
    for l in neg_lists:
        neg_c.update({t for t in l if t.isalpha() and len(t) > 2 and t not in _THEME_STOP})
    np_, nn_ = max(len(pos_lists), 1), max(len(neg_lists), 1)

    def lo(t: str) -> float:
        return math.log((pos_c[t] + 0.5) / (np_ + 1)) - math.log((neg_c[t] + 0.5) / (nn_ + 1))

    pos_terms = sorted((t for t in pos_c if pos_c[t] >= 2), key=lambda t: (-lo(t), -pos_c[t]))[:k]
    neg_terms = sorted((t for t in neg_c if neg_c[t] >= 2), key=lambda t: (lo(t), -neg_c[t]))[:k]
    return {
        "positive": [{"term": t, "count": pos_c[t]} for t in pos_terms],
        "negative": [{"term": t, "count": neg_c[t]} for t in neg_terms],
    }
