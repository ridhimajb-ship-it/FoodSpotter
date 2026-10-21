"""BERT sentiment path.

Model
-----
`nlptown/bert-base-multilingual-uncased-sentiment` (MIT licence): *bert-base-multilingual-uncased fine-tuned for
sentiment analysis on product reviews* in six languages (English, Dutch, German, French, Spanish, Italian). It
predicts a 1-5 star rating for a text. FoodSpotter turns the five star probabilities into three classes:

    negative = P(1 star) + P(2 stars)      neutral = P(3 stars)      positive = P(4 stars) + P(5 stars)

That 5 -> 3 mapping is FoodSpotter's own choice, not part of the model. The label is the class with the largest
probability mass and `confidence` is that mass.

Limitations (also shown in the UI): trained on *product* reviews, not restaurant reviews (domain shift); input is
truncated at the token limit; only six languages (code-mixed text such as Hinglish may be unreliable); review-level
only, so aspect analysis remains rule-based; and no accuracy for FoodSpotter's data is claimed until labelled
ground truth exists (scripts/evaluate_models.py).

`transformers` and `torch` are optional dependencies (backend/requirements-bert.txt). Without them, or without
network access to download the weights once, `BertUnavailable` is raised and the VADER baseline stays in use.
Nothing here ever fabricates a prediction.
"""
from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from backend.config import Settings, get_settings

MODEL_FAMILY = "bert-base-multilingual-uncased"
MODEL_CARD_URL = "https://huggingface.co/nlptown/bert-base-multilingual-uncased-sentiment"
LABELS = ("negative", "neutral", "positive")

MODEL_CARD = {
    "id": "nlptown/bert-base-multilingual-uncased-sentiment",
    "architecture": "bert-base-multilingual-uncased, fine-tuned for sentiment analysis on product reviews",
    "output": "1 to 5 stars (five class probabilities)",
    "languages": ["English", "Dutch", "German", "French", "Spanish", "Italian"],
    "licence": "MIT",
    "card_url": MODEL_CARD_URL,
    "mapping": "negative = 1-2 stars, neutral = 3 stars, positive = 4-5 stars (FoodSpotter's mapping; confidence = probability mass of the winning class)",
    "limitations": [
        "Fine-tuned on product reviews, not restaurant reviews, so accuracy on restaurant text is unknown until it is measured.",
        "Reviews longer than the token limit are truncated; affected reviews are flagged.",
        "Trained on six languages; Hinglish or Kannada-English code-mixing may be misread.",
        "Predicts one label per review, so aspect findings (food, service, ...) still come from the rule-based analyser.",
        "The 1-5 star to negative/neutral/positive mapping is a design choice and moves borderline reviews between classes.",
        "Unless BERT_MODEL_REVISION is set, the latest model files are downloaded, so results may change if the authors update them.",
    ],
    "authors_reported_accuracy_note": (
        "The model authors report accuracy on held-out PRODUCT reviews on the model card. Those figures say nothing about "
        "restaurant reviews and are not FoodSpotter's evaluation."
    ),
}


class BertUnavailable(RuntimeError):
    """BERT cannot run here (missing packages, no model download, ...). The VADER baseline remains in use."""


@dataclass(frozen=True)
class BertPrediction:
    label: str
    confidence: float
    p_negative: float
    p_neutral: float
    p_positive: float
    polarity: float
    star_probs: tuple[float, float, float, float, float]
    expected_stars: float
    predicted_stars: int
    truncated: Optional[bool]


def from_star_probs(probs: Sequence[float], truncated: Optional[bool] = None) -> BertPrediction:
    """Turn P(1..5 stars) into the three-class prediction. Probabilities are renormalised defensively."""
    if len(probs) != 5 or any(p < 0 for p in probs):
        raise ValueError("expected five non-negative star probabilities")
    total = float(sum(probs))
    if total <= 0:
        raise ValueError("star probabilities sum to zero")
    p = [float(x) / total for x in probs]
    neg, neu, pos = p[0] + p[1], p[2], p[3] + p[4]
    masses = {"negative": neg, "neutral": neu, "positive": pos}
    label = max(LABELS, key=lambda k: masses[k])
    return BertPrediction(
        label=label, confidence=round(masses[label], 6),
        p_negative=round(neg, 6), p_neutral=round(neu, 6), p_positive=round(pos, 6),
        polarity=round(pos - neg, 6), star_probs=tuple(round(x, 6) for x in p),  # type: ignore[arg-type]
        expected_stars=round(sum((i + 1) * x for i, x in enumerate(p)), 4),
        predicted_stars=max(range(5), key=lambda i: p[i]) + 1, truncated=truncated,
    )


def _probs_from_pipeline_output(row: Any) -> list[float]:
    """`pipeline(..., top_k=None)` yields [{'label': '3 stars', 'score': 0.2}, ...] for each text."""
    probs = [0.0] * 5
    seen = set()
    for item in row:
        m = re.search(r"([1-5])", str(item["label"]))
        if not m:
            raise ValueError(f"unexpected label {item['label']!r}")
        probs[int(m.group(1)) - 1] = float(item["score"])
        seen.add(int(m.group(1)))
    if seen != {1, 2, 3, 4, 5}:
        raise ValueError("model output did not contain all five star classes")
    return probs


def availability() -> dict:
    """Cheap check (no model loading): are the optional packages installed?"""
    missing = [m for m in ("transformers", "torch") if importlib.util.find_spec(m) is None]
    if missing:
        return {"packages_installed": False,
                "reason": f"Missing Python package(s): {', '.join(missing)}. Install with: pip install -r backend/requirements-bert.txt"}
    return {"packages_installed": True, "reason": None}


class BertSentimentModel:
    """Lazy wrapper. Pass `classifier` (and optionally `tokenizer`) to inject a stand-in, e.g. in unit tests."""

    def __init__(self, settings: Settings | None = None, classifier: Optional[Callable[..., Any]] = None, tokenizer: Any = None):
        self.s = settings or get_settings()
        self._clf = classifier
        self._tok = tokenizer
        self.revision = self.s.bert_model_revision or None

    @property
    def model_id(self) -> str:
        return self.s.bert_model_id

    def _load(self) -> None:
        if self._clf is not None:
            return
        info = availability()
        if not info["packages_installed"]:
            raise BertUnavailable(info["reason"])
        try:
            from transformers import AutoTokenizer, pipeline

            self._tok = AutoTokenizer.from_pretrained(self.model_id, revision=self.revision)
            self._clf = pipeline("text-classification", model=self.model_id, tokenizer=self._tok, revision=self.revision,
                                 top_k=None, truncation=True, max_length=self.s.bert_max_length, device=-1)
        except Exception as e:  # network blocked, unknown model, out of memory, ...
            self._clf = None
            raise BertUnavailable(f"Could not load model '{self.model_id}': {type(e).__name__}: {str(e)[:200]}") from e

    def _is_truncated(self, text: str) -> Optional[bool]:
        if self._tok is None:
            return None
        try:
            return len(self._tok(text, add_special_tokens=True)["input_ids"]) > self.s.bert_max_length
        except Exception:
            return None

    def predict(self, texts: Sequence[str]) -> list[BertPrediction]:
        self._load()
        out: list[BertPrediction] = []
        bs = max(1, self.s.bert_batch_size)
        for i in range(0, len(texts), bs):
            batch = list(texts[i:i + bs])
            rows = self._clf(batch)  # type: ignore[misc]
            if len(rows) != len(batch):
                raise BertUnavailable("The classifier returned a different number of results than inputs; refusing to guess.")
            for text, row in zip(batch, rows):
                out.append(from_star_probs(_probs_from_pipeline_output(row), self._is_truncated(text)))
        return out
