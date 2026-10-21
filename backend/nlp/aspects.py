"""Transparent, rule-based aspect-based sentiment analysis (ABSA).

Method
------
1. Split each review into clauses (sentence punctuation, contrast words such as "but", and "and" when it
   introduces a new clause with its own verb).
2. A clause *mentions* an aspect when it contains one of that aspect's seed keywords.
3. Polarity of the mention = aspect-specific cue words (checked for local negation) when present, otherwise the
   VADER compound score of the clause.
4. Mentions of the same aspect inside one review are averaged into a single (review, aspect) result.

The keyword lists are seed lexicons: they favour precision over recall (e.g. dish names beyond the listed ones are
not recognised as "food"). Evaluation of extraction recall requires manual annotation (see scripts/evaluate_models.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend.config import get_settings
from backend.nlp.sentiment import get_analyzer

ASPECTS = ["food", "service", "ambience", "affordability", "hygiene", "waiting_time"]

ASPECT_LABELS = {
    "food": "Food quality",
    "service": "Service",
    "ambience": "Ambience",
    "affordability": "Affordability",
    "hygiene": "Hygiene",
    "waiting_time": "Waiting time",
}


def _rx(*alts: str) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(alts) + r")\b", re.I)


KEYWORDS = {
    "food": _rx(
        r"foods?", r"tastes?", r"tasty", r"tasted", r"flavou?rs?", r"flavou?rful", r"delicious", r"yumm?y", r"dish(?:es)?",
        r"cuisine", r"menu", r"portions?", r"quantity", r"starters?", r"appetizers?", r"main course", r"desserts?",
        r"pizzas?", r"pasta", r"burgers?", r"biryani", r"dosas?", r"idlis?", r"noodles", r"rice", r"chicken", r"mutton",
        r"paneer", r"cakes?", r"sandwich(?:es)?", r"curry", r"kebabs?", r"tikka", r"bread", r"naan", r"soups?",
        r"salads?", r"fries", r"coffee", r"tea", r"drinks?", r"cocktails?", r"beer", r"sushi", r"momos?", r"thali",
        r"meal", r"meals", r"breakfast", r"brunch", r"steak", r"fish", r"prawns?", r"ice cream", r"sweets?", r"fresh",
    ),
    "service": _rx(
        r"service", r"staff", r"waiters?", r"waitress(?:es)?", r"servers?", r"manager", r"owner", r"hosts?",
        r"hospitality", r"attentive", r"courteous", r"behaviou?r", r"polite", r"rude", r"served", r"crew", r"captain",
    ),
    "ambience": _rx(
        r"ambien(?:ce|ts?)", r"ambian(?:ce|t)", r"atmosphere", r"d[eé]cor", r"interiors?", r"seating", r"music",
        r"vibes?", r"lighting", r"views?", r"crowd", r"noisy", r"noise", r"cozy", r"cosy", r"rooftop", r"setting",
        r"decorations?", r"environment", r"ambiance", r"space", r"cramped",
    ),
    "affordability": _rx(
        r"prices?", r"pricing", r"priced", r"pricey", r"expensive", r"cheap(?:er)?", r"costly", r"costs?", r"value",
        r"money", r"worth", r"affordable", r"reasonabl[ey]", r"budget", r"bill", r"pocket", r"overpriced",
        r"rip[- ]?off", r"rs\.?", r"₹", r"inr",
    ),
    "hygiene": _rx(
        r"hygien(?:e|ic)", r"unhygienic", r"clean(?:liness|ed|ing)?", r"unclean", r"dirty", r"filthy", r"washrooms?",
        r"restrooms?", r"toilets?", r"sanitation", r"cockroach(?:es)?", r"flies", r"tidy", r"spotless", r"stink(?:s|y)?",
    ),
    "waiting_time": _rx(
        r"wait(?:ed|ing)?", r"waiting time", r"queue", r"delay(?:ed)?", r"took (?:too |so |very )?long",
        r"long time", r"forever", r"ages", r"quickly", r"promptly",
        r"took (?:over )?\d+ ?(?:min|mins|minutes|hour|hours)",
        r"waited (?:for )?(?:about |around |almost |nearly |over )?\d+ ?(?:min|mins|minutes|hour|hours)",
    ),
}
# NB: bare "slow"/"fast"/"late"/"quick" are deliberately NOT waiting-time keywords: "the service was slow" is a
# service mention. They only act as polarity cues once a waiting-time keyword has matched.

# Aspect-specific polarity cues – checked before falling back to VADER because words such as
# "high" (prices) or "slow" (waiting) are not sentiment-bearing in general language.
CUES = {
    "food": (
        _rx(r"delicious", r"yumm?y", r"tasty", r"flavou?rful", r"fresh(?:ly)?", r"amazing", r"awesome", r"excellent", r"superb",
            r"mouth[- ]?watering", r"authentic", r"loved", r"great", r"good", r"best", r"perfectly cooked", r"scrumptious"),
        _rx(r"bland", r"tasteless", r"stale", r"undercooked", r"overcooked", r"soggy", r"greasy", r"oily", r"cold food",
            r"disappointing", r"bad", r"terrible", r"awful", r"average", r"mediocre", r"not (?:fresh|good|tasty)", r"horrible"),
    ),
    "service": (
        _rx(r"friendly", r"attentive", r"courteous", r"polite", r"helpful", r"welcoming", r"prompt", r"excellent service",
            r"great service", r"good service", r"quick service", r"warm"),
        _rx(r"slow", r"rude", r"inattentive", r"unprofessional", r"ignored", r"poor service", r"bad service", r"terrible",
            r"arrogant", r"careless", r"unfriendly", r"disrespectful", r"worst"),
    ),
    "ambience": (
        _rx(r"cozy", r"cosy", r"beautiful", r"lovely", r"nice", r"great", r"pleasant", r"relaxing", r"charming", r"vibrant",
            r"elegant", r"stunning", r"good ambien", r"peaceful", r"spacious", r"comfortable"),
        _rx(r"noisy", r"loud", r"cramped", r"stuffy", r"dull", r"dingy", r"uncomfortable", r"crowded", r"congested", r"cluttered",
            r"poor ambien", r"depressing"),
    ),
    "affordability": (
        _rx(r"affordable", r"reasonabl[ey]", r"cheap(?:er)?", r"worth", r"value for money", r"pocket[- ]?friendly", r"budget",
            r"good price", r"economical", r"low prices?", r"prices? (?:were|are|is|was) (?:very |quite |really )?(?:reasonable|good|low|fair)"),
        _rx(r"expensive", r"overpriced", r"pricey", r"costly", r"steep", r"rip[- ]?off", r"not worth", r"heavy on the pocket",
            r"high prices?", r"prices? (?:were|are|is|was) (?:a bit |bit |very |too |quite |really |on the |slightly )*(?:high|steep|higher)",
            r"too much", r"waste of money"),
    ),
    "hygiene": (
        _rx(r"clean", r"hygienic", r"spotless", r"tidy", r"neat", r"well[- ]maintained", r"sanitized"),
        _rx(r"dirty", r"unclean", r"unhygienic", r"filthy", r"cockroach(?:es)?", r"flies", r"stink(?:s|y)?", r"smelly",
            r"messy", r"unkempt", r"hair in", r"insect"),
    ),
    "waiting_time": (
        _rx(r"quick(?:ly)?", r"prompt(?:ly)?", r"fast", r"no wait", r"short wait", r"hardly (?:any )?wait", r"on time", r"speedy"),
        _rx(r"slow(?:ly)?", r"took (?:too |so |very )?long", r"long (?:wait|time|queue)", r"forever", r"ages", r"delayed?",
            r"waited (?:for )?(?:a )?(?:long|too|over|almost|nearly)", r"long waiting", r"wait(?:ing)? (?:time )?(?:was|is) (?:very |too |really )?(?:long|bad)",
            r"late", r"took (?:over )?\d+ ?(?:min|mins|minutes|hour|hours)",
            r"waited (?:for )?(?:about |around |almost |nearly |over )?\d+ ?(?:min|mins|minutes|hour|hours)"),
    ),
}

_NEGATION_RE = re.compile(r"\b(?:not|no|never|hardly|isn't|wasn't|aren't|weren't|don't|didn't|doesn't|without)\b|n't\b", re.I)

# Clause boundaries. "and" only splits when followed by a determiner/pronoun and then a verb of its own.
_SPLIT_RE = re.compile(
    r"[.;!?\n]+|,?\s*\b(?:but|however|although|though|whereas|while|yet)\b|"
    r",?\s*\band\b(?=\s+(?:the|their|our|its|they|we|it|i|my)\b[^,.;!?]*\b(?:was|were|is|are|been|felt|seemed|took|had|has|have)\b)",
    re.I,
)


@dataclass
class AspectMention:
    aspect: str
    label: str
    score: float
    evidence: str


def split_clauses(text: str) -> list[str]:
    parts = [p.strip(" ,-–—") for p in _SPLIT_RE.split(text) if p and p.strip(" ,-–—")]
    return [p for p in parts if len(p) > 2]


def _cue_hits(pattern: re.Pattern, clause: str) -> int:
    """Count cue matches, flipping handled by caller via negation window."""
    return len(pattern.findall(clause))


def _negated(clause: str, start: int) -> bool:
    window = clause[max(0, start - 18):start]
    return bool(_NEGATION_RE.search(window))


def _polarity(aspect: str, clause: str, extended: bool) -> float:
    pos_rx, neg_rx = CUES[aspect]
    pos = neg = 0
    for m in pos_rx.finditer(clause):
        if _negated(clause, m.start()):
            neg += 1
        else:
            pos += 1
    for m in neg_rx.finditer(clause):
        if _negated(clause, m.start()):
            pos += 1
        else:
            neg += 1
    compound = get_analyzer(extended).polarity_scores(clause)["compound"]
    if pos > neg:
        return min(1.0, 0.6 + 0.4 * compound)
    if neg > pos:
        return max(-1.0, -0.6 + 0.4 * compound)
    return compound


def label_from_score(score: float) -> str:
    t = get_settings().aspect_label_threshold
    if score >= t:
        return "positive"
    if score <= -t:
        return "negative"
    return "neutral"


def analyze_review_aspects(text: str, extended: bool = True) -> list[AspectMention]:
    """Return one AspectMention per aspect present in the review."""
    per_aspect: dict[str, list[tuple[float, str]]] = {}
    for clause in split_clauses(text):
        for aspect in ASPECTS:
            if KEYWORDS[aspect].search(clause):
                per_aspect.setdefault(aspect, []).append((_polarity(aspect, clause, extended), clause))
    out = []
    for aspect, items in per_aspect.items():
        mean = sum(s for s, _ in items) / len(items)
        strongest = max(items, key=lambda it: abs(it[0]))[1]
        out.append(AspectMention(aspect, label_from_score(mean), round(mean, 4), strongest[:300]))
    return out
