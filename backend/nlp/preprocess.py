"""Text preprocessing: cleaning, tokenisation, stop-word removal (negations preserved), lemmatisation."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any, Optional

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
RATED_PREFIX_RE = re.compile(r"^\s*rated\b[\s:]*", re.I)
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WS_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+")

# Negations must survive stop-word removal – "not good" is not "good".
NEGATIONS = frozenset(
    {"no", "not", "never", "nor", "none", "nothing", "neither", "cannot", "without",
     "hardly", "barely", "scarcely", "nobody", "nowhere", "isn't", "wasn't", "don't",
     "didn't", "doesn't", "won't", "can't", "couldn't", "shouldn't", "wouldn't", "aren't", "weren't"}
)
STOPWORDS = frozenset(ENGLISH_STOP_WORDS) - NEGATIONS - {"very", "too", "but", "however", "enough"}

_CONTRACTIONS = {"can't": "cannot", "won't": "will not", "ain't": "is not"}

_IRREGULAR = {
    "was": "be", "were": "be", "been": "be", "is": "be", "are": "be", "am": "be",
    "had": "have", "has": "have", "did": "do", "does": "do", "went": "go", "ate": "eat",
    "better": "good", "best": "good", "worse": "bad", "worst": "bad",
    "children": "child", "people": "person", "men": "man", "women": "woman",
}


def clean_text(raw: Any) -> Optional[str]:
    """Return display-safe cleaned text, or None when the input is null/malformed/empty."""
    if raw is None or not isinstance(raw, str):
        return None
    text = unicodedata.normalize("NFKC", raw).replace("\xa0", " ")
    text = CTRL_RE.sub(" ", text)
    text = RATED_PREFIX_RE.sub("", text, count=1)  # dataset artefact: "RATED\n  <text>"
    text = URL_RE.sub(" ", text)
    text = WS_RE.sub(" ", text).strip()
    if len(text) < 3 or not re.search(r"[A-Za-z]{2,}", text):
        return None
    return text


def expand_contractions(text: str) -> str:
    text = text.lower().replace("’", "'")
    for k, v in _CONTRACTIONS.items():
        text = text.replace(k, v)
    return re.sub(r"(\w+)n't\b", r"\1 not", text)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(expand_contractions(text))


@lru_cache(maxsize=1)
def _wordnet():
    """Use NLTK WordNet when its corpus is installed; otherwise fall back to the rule-based lemmatiser."""
    try:
        from nltk.stem import WordNetLemmatizer

        lem = WordNetLemmatizer()
        lem.lemmatize("tests")  # raises LookupError if the corpus is missing
        return lem
    except Exception:
        return None


def _rule_lemma(tok: str) -> str:
    if tok in _IRREGULAR:
        return _IRREGULAR[tok]
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 4 and tok.endswith(("ches", "shes", "xes", "sses")):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
        return tok[:-1]
    return tok


def lemmatize(tokens: list[str]) -> list[str]:
    wn = _wordnet()
    if wn is not None:
        return [wn.lemmatize(t) for t in tokens]
    return [_rule_lemma(t) for t in tokens]


def remove_stopwords(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def preprocess(raw: Any) -> dict:
    """Full pipeline. `display` keeps the original wording; `lemmas` is for analysis only."""
    display = clean_text(raw)
    if display is None:
        return {"display": None, "tokens": [], "lemmas": []}
    tokens = tokenize(display)
    lemmas = lemmatize(remove_stopwords(tokens))
    return {"display": display, "tokens": tokens, "lemmas": lemmas}
