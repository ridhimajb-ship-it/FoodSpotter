import pytest

from backend.nlp.aspects import analyze_review_aspects, split_clauses
from backend.nlp.preprocess import clean_text, preprocess, tokenize
from backend.nlp.sentiment import score_text
from backend.nlp.summarize import aspect_stats, build_summary


def aspects(text):
    return {m.aspect: m.label for m in analyze_review_aspects(text)}


class TestPreprocess:
    @pytest.mark.parametrize("bad", [None, 3.5, float("nan"), "", "   ", "!!", "12"])
    def test_null_and_malformed_become_none(self, bad):
        assert clean_text(bad) is None

    def test_strips_dataset_prefix_urls_and_whitespace(self):
        assert clean_text("RATED\n  Nice   place \xa0 see http://x.io/abc now") == "Nice place see now"

    def test_negations_survive_stopword_removal(self):
        lemmas = preprocess("The food was not good and I would never return")["lemmas"]
        assert "not" in lemmas and "never" in lemmas

    def test_contractions_become_not(self):
        assert "not" in tokenize("It wasn't fresh and I don't recommend it")

    def test_original_text_kept_for_display(self):
        assert preprocess("Great FOOD!!")["display"] == "Great FOOD!!"


class TestSentiment:
    def test_labels(self):
        assert score_text("Absolutely delicious, loved it").label == "positive"
        assert score_text("Horrible food and rude staff").label == "negative"
        assert score_text("We went there on Tuesday").label == "neutral"

    def test_negation_flips(self):
        assert score_text("The food was not good").compound < score_text("The food was good").compound

    def test_domain_lexicon_changes_score_only_when_extended(self):
        t = "The service was slow and the food was bland"
        assert score_text(t, extended=True).compound < score_text(t, extended=False).compound


class TestAspects:
    def test_spec_example(self):
        r = aspects("The pizza was delicious, but the service was slow and the prices were high.")
        assert r == {"food": "positive", "service": "negative", "affordability": "negative"}

    def test_clause_splitting(self):
        parts = split_clauses("The pizza was delicious, but the service was slow and the prices were high.")
        assert len(parts) == 3

    def test_negated_cue_flips_polarity(self):
        assert aspects("The staff were not rude at all.")["service"] == "positive"
        assert aspects("The place was not clean.")["hygiene"] == "negative"

    def test_waiting_time(self):
        assert aspects("We waited 45 minutes for a table.")["waiting_time"] == "negative"
        assert aspects("Food arrived quickly.")["waiting_time"] == "positive"

    def test_slow_service_is_not_a_waiting_time_mention(self):
        assert "waiting_time" not in aspects("The service was slow.")

    def test_no_aspect_when_no_evidence(self):
        assert aspects("We went there on Tuesday.") == {}

    def test_hygiene_and_ambience(self):
        r = aspects("Dirty washrooms but a lovely atmosphere.")
        assert r["hygiene"] == "negative" and r["ambience"] == "positive"


class TestSummary:
    def _stats(self, **kw):
        rows = []
        for aspect, (p, n) in kw.items():
            rows += [(aspect, "positive")] * p + [(aspect, "negative")] * n
        return aspect_stats(rows)

    def test_summary_praise_and_criticism(self):
        s = build_summary(self._stats(food=(8, 1), ambience=(6, 0), waiting_time=(1, 5)), 20)
        assert "food" in s["text"] and "ambience" in s["text"] and "waiting times" in s["text"]
        assert s["praised"] == ["ambience", "food"] or set(s["praised"]) == {"food", "ambience"}

    def test_insufficient_evidence_is_reported_not_guessed(self):
        stats = self._stats(food=(2, 0))  # below min mentions
        assert stats["food"]["sufficient_evidence"] is False
        assert build_summary(stats, 20)["text"] is None

    def test_too_few_reviews(self):
        assert build_summary(self._stats(food=(9, 0)), 1)["text"] is None
