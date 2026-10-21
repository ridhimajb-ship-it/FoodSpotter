"""BERT path, engine selection, shared filters and the insights API.

⚠ The BERT model itself is NOT loaded in these tests (no network / no torch is required): a deterministic *stand-in*
classifier with the same output format as the Hugging Face pipeline is injected. These tests prove the plumbing
(mapping, storage, engine switching, API shapes, failure handling) – not the quality of the real model.
"""
import pytest
from sqlalchemy import select

from backend.config import get_settings
from backend.main import app
from backend.models import BertSentimentResult, Review
from backend.nlp import bert as bert_mod
from backend.nlp.bert import BertSentimentModel, BertUnavailable, _probs_from_pipeline_output, from_star_probs
from backend.nlp.sentiment import score_text
from backend.services.pipeline import run_bert
from backend.services.sentiment_view import active_engine, engine_info
from tests.conftest import ADMIN
from tests.test_api import data  # noqa: F401  (synthetic fixture world)


def fake_classifier(texts, **_):
    """Stand-in with the pipeline's output format. 'bland' is deliberately scored positive to create a disagreement."""
    out = []
    for t in texts:
        c = score_text(t).compound
        if "bland" in t:
            p = [0.02, 0.03, 0.05, 0.2, 0.7]
        elif c >= 0.05:
            p = [0.0, 0.02, 0.08, 0.3, 0.6]
        elif c <= -0.05:
            p = [0.6, 0.25, 0.1, 0.03, 0.02]
        else:
            p = [0.05, 0.15, 0.6, 0.15, 0.05]
        out.append([{"label": f"{i + 1} star" + ("s" if i else ""), "score": v} for i, v in enumerate(p)])
    return out


class FakeTok:
    def __call__(self, text, add_special_tokens=True):
        return {"input_ids": list(range(len(text.split()) + 2))}


def model(**kw):
    s = get_settings()
    return BertSentimentModel(s, classifier=fake_classifier, tokenizer=kw.get("tokenizer"))


class TestMapping:
    def test_three_class_mapping(self):
        assert from_star_probs([0.6, 0.2, 0.1, 0.05, 0.05]).label == "negative"
        assert from_star_probs([0.1, 0.1, 0.6, 0.1, 0.1]).label == "neutral"
        p = from_star_probs([0.0, 0.1, 0.1, 0.3, 0.5])
        assert p.label == "positive" and p.confidence == pytest.approx(0.8) and p.predicted_stars == 5
        assert p.polarity == pytest.approx(0.7) and p.expected_stars == pytest.approx(4.2, abs=0.01)

    def test_probabilities_are_renormalised_and_validated(self):
        assert from_star_probs([1, 1, 1, 1, 1]).p_neutral == pytest.approx(0.2)
        for bad in ([1, 2, 3], [-0.1, 0.1, 0.1, 0.1, 0.8], [0, 0, 0, 0, 0]):
            with pytest.raises(ValueError):
                from_star_probs(bad)

    def test_pipeline_output_parsing(self):
        row = [{"label": "5 stars", "score": 0.5}, {"label": "1 star", "score": 0.1}, {"label": "3 stars", "score": 0.2},
               {"label": "2 stars", "score": 0.1}, {"label": "4 stars", "score": 0.1}]
        assert _probs_from_pipeline_output(row) == [0.1, 0.1, 0.2, 0.1, 0.5]
        with pytest.raises(ValueError):
            _probs_from_pipeline_output(row[:4])
        with pytest.raises(ValueError):
            _probs_from_pipeline_output([{"label": "LABEL_0", "score": 1.0}])

    def test_truncation_flag_and_batching(self):
        s = get_settings()
        m = BertSentimentModel(s, classifier=fake_classifier, tokenizer=FakeTok())
        long_text = "word " * (s.bert_max_length + 5)
        preds = m.predict(["short text is fine", long_text])
        assert [p.truncated for p in preds] == [False, True]
        assert BertSentimentModel(s, classifier=fake_classifier).predict(["x y z"])[0].truncated is None  # unknown, not guessed

    def test_unavailable_when_packages_missing(self, monkeypatch):
        monkeypatch.setattr(bert_mod, "availability", lambda: {"packages_installed": False, "reason": "Missing Python package(s): transformers, torch."})
        with pytest.raises(BertUnavailable, match="transformers"):
            BertSentimentModel(get_settings()).predict(["good food"])

    def test_wrong_result_count_is_refused(self):
        m = BertSentimentModel(get_settings(), classifier=lambda texts, **_: [])
        with pytest.raises(BertUnavailable):
            m.predict(["a b c"])


class TestEngine:
    def test_run_and_auto_switch(self, db, data):
        assert active_engine(db) == "vader" and engine_info(db)["coverage"]["bert"] == 0
        partial = run_bert(db, model(), limit=20)
        assert partial["reviews_analysed"] == 20 and partial["status"] == "ok"
        info = engine_info(db)
        assert info["active"] == "vader" and "20 of" in info["reason"]  # below the 95 % threshold: never a silent mix
        full = run_bert(db, model())
        assert full["status"] == "ok" and full["reviews_analysed"] > 0
        assert active_engine(db) == "bert" and engine_info(db)["coverage"]["bert_share"] == 1.0
        row = db.scalar(select(BertSentimentResult))
        assert row.model_id == get_settings().bert_model_id and len(row.star_probs) == 5 and row.label in ("positive", "neutral", "negative")
        assert run_bert(db, model())["reviews_analysed"] == 0  # idempotent

    def test_only_matched_reviews_are_analysed(self, db, data):
        run_bert(db, model())
        unresolved = db.scalars(select(Review).where(Review.restaurant_id.is_(None))).all()
        assert unresolved and all(r.bert is None for r in unresolved)

    def test_unavailable_writes_nothing(self, db, data):
        def boom(texts, **_):
            raise BertUnavailable("no weights")
        res = run_bert(db, BertSentimentModel(get_settings(), classifier=boom))
        assert res["status"] == "unavailable" and "no weights" in res["reason"] and res["reviews_analysed"] == 0
        assert db.scalar(select(BertSentimentResult)) is None and active_engine(db) == "vader"

    def test_forced_engines(self, db, data, monkeypatch):
        run_bert(db, model())
        monkeypatch.setattr(get_settings(), "sentiment_engine", "vader")
        assert active_engine(db) == "vader" and "forces" in engine_info(db)["reason"]
        monkeypatch.setattr(get_settings(), "sentiment_engine", "bert")
        assert active_engine(db) == "bert"

    def test_engine_info_labels_models_honestly(self, db, data):
        i = engine_info(db)
        assert "baseline" in i["vader"]["label"].lower() and i["bert"]["model"]["id"] == "nlptown/bert-base-multilingual-uncased-sentiment"
        assert i["bert"]["run_in_this_database"] is False and len(i["bert"]["model"]["limitations"]) >= 4
        assert "product reviews" in i["bert"]["model"]["architecture"]


class TestApiWithBert:
    def test_reviews_carry_both_models_and_label_active_engine(self, client, db, data):
        rid = data["famous"].id
        r = client.get(f"/api/restaurants/{rid}/reviews?limit=3").json()
        assert r["engine"] == "vader" and r["items"][0]["bert"] is None and r["items"][0]["sentiment"]["engine"] == "vader"
        run_bert(db, model())
        r = client.get(f"/api/restaurants/{rid}/reviews?limit=3").json()
        it = r["items"][0]
        assert r["engine"] == "bert" and it["sentiment"]["engine"] == "bert" and it["vader"]["label"]
        assert 0.33 <= it["bert"]["confidence"] <= 1 and len(it["bert"]["star_probabilities"]) == 5 and it["bert"]["model_id"]
        assert sum(it["bert"]["probabilities"].values()) == pytest.approx(1, abs=1e-3)

    def test_sentiment_endpoint_comparison(self, client, db, data):
        rid = data["famous"].id
        s = client.get(f"/api/restaurants/{rid}/sentiment").json()
        assert s["comparison"]["agreement"] is None and s["comparison"]["other_distribution"] is None
        run_bert(db, model())
        s = client.get(f"/api/restaurants/{rid}/sentiment").json()
        assert s["engine"]["active"] == "bert" and s["mean_confidence"] and s["comparison"]["other_engine"] == "vader"
        assert s["comparison"]["reviews_with_both"] == s["analysed_reviews"] and 0 <= s["comparison"]["agreement"] <= 1
        assert "not accuracy" in s["comparison"]["note"]

    def test_disagreement_is_visible(self, client, db, data):
        run_bert(db, model())
        s = client.get(f"/api/restaurants/{data['famous'].id}/sentiment").json()
        assert s["comparison"]["agreement"] < 1  # 'bland' reviews are scored positive by the stand-in, negative by VADER

    def test_review_filters_by_aspect_and_sentiment(self, client, data):
        rid = data["famous"].id
        food = client.get(f"/api/restaurants/{rid}/reviews?aspect=food&limit=100").json()
        assert 0 < food["total"] < 39 and all(any(a["aspect"] == "food" for a in i["aspects"]) for i in food["items"])
        both = client.get(f"/api/restaurants/{rid}/reviews?aspect=hygiene&sentiment=negative&limit=100").json()
        assert all(i["sentiment"]["label"] == "negative" for i in both["items"])
        assert client.get(f"/api/restaurants/{rid}/reviews?aspect=bogus").status_code == 422
        conf = client.get(f"/api/restaurants/{rid}/reviews?sort=most_confident").json()
        assert conf["items"]

    def test_admin_run_bert(self, client, db, data, monkeypatch):
        assert client.post("/api/admin/run-bert").status_code == 401
        monkeypatch.setattr("backend.api.admin.availability", lambda: {"packages_installed": False, "reason": "Missing Python package(s): transformers, torch."})
        r = client.post("/api/admin/run-bert", headers=ADMIN)
        assert r.status_code == 400 and "transformers" in r.json()["detail"]
        app.state.bert_factory = lambda: model()
        try:
            r = client.post("/api/admin/run-bert", headers=ADMIN)
            assert r.status_code == 202
            e = client.get("/api/analytics/sentiment-engine").json()
            assert e["active"] == "bert" and e["job"]["last"]["status"] == "ok" and e["job"]["running"] is False
        finally:
            del app.state.bert_factory


class TestSharedFilters:
    def test_min_reviews_sentiment_aspect_price(self, client, data):
        base = client.get("/api/restaurants?limit=100").json()["total"]
        assert client.get("/api/restaurants?min_reviews=20").json()["total"] == 1                      # only the famous one
        assert client.get("/api/restaurants?min_reviews=5").json()["total"] > 1
        pos = {i["name"] for i in client.get("/api/restaurants?sentiment=positive").json()["items"]}
        neg = {i["name"] for i in client.get("/api/restaurants?sentiment=negative").json()["items"]}
        assert "Fixture Hidden Gem" in pos and "Fixture Weak Eatery" in neg and not pos & neg and len(pos) < base
        food = {i["name"] for i in client.get("/api/restaurants?aspect=food").json()["items"]}
        assert "Fixture Famous Kitchen" in food and "Fixture Thin Cafe" not in food                     # 3 reviews < 5 mentions
        assert client.get("/api/restaurants?price_min=900").json()["total"] == 0                        # imported fixture price is 800 (12 of 13 restaurants have a Zomato row)
        assert client.get("/api/restaurants?price_max=800&price_min=800").json()["total"] == 12
        assert client.get("/api/restaurants?sentiment=sideways").status_code == 422
        assert client.get("/api/restaurants?min_reviews=-1").status_code == 422

    def test_filters_combine_and_pagination_total_is_filtered(self, client, data):
        r = client.get("/api/restaurants?neighborhood=indiranagar&min_reviews=5&limit=2").json()
        assert r["total"] > 2 and len(r["items"]) == 2 and all(i["neighborhood"] == "indiranagar" for i in r["items"])

    def test_hotspots_and_rankings_follow_filters(self, client, data):
        assert client.get("/api/analytics/hotspots?metric=density&neighborhood=koramangala").json()["n_points"] == 2
        h = client.get("/api/analytics/hotspots?metric=reviews&sentiment=negative").json()
        assert h["n_points"] >= 1 and h["filters_applied"] == {"sentiment": "negative"}
        pop = client.get("/api/restaurants/popular?neighborhood=koramangala").json()["items"]
        assert pop and all(i["neighborhood"] == "koramangala" for i in pop)
        assert client.get("/api/restaurants/hidden-gems?neighborhood=koramangala").json()["items"] == []


class TestInsights:
    def test_empty_database(self, client):
        d = client.get("/api/insights").json()
        assert d["scope"]["restaurants"] == 0 and d["scope"]["reviews_analysed"] == 0 and d["sentiment"]["positive_share"] is None
        assert d["neighborhoods"] == [] and d["cuisines"] == [] and d["hidden_gems"]["items"] == []
        assert d["time_trend"]["available"] is False and "no dates" in d["time_trend"]["reason"]
        assert all(a["mentions"] == 0 and a["net_score"] is None for a in d["aspects"])
        assert d["pipeline"]["restaurants_discovered"] == 0 and d["pipeline"]["import"] is None

    def test_numbers_come_from_the_database(self, client, data):
        d = client.get("/api/insights").json()
        assert d["scope"] == {"restaurants": 13, "restaurants_with_reviews": 12, "reviews_analysed": 130, "restaurants_in_database": 13}
        s = d["sentiment"]
        assert s["n"] == 130 and s["positive"] + s["neutral"] + s["negative"] == 130
        pl = d["pipeline"]
        assert pl["restaurants_discovered"] == 13 and pl["restaurants_with_matched_reviews"] == 12 and pl["reviews_matched"] == 130
        assert pl["reviews_unresolved_stored"] == 4 and pl["reviews_stored"] == 134 and pl["import"]["valid_reviews_imported"] == 130
        assert pl["dated_reviews"] == 0 and d["time_trend"]["available"] is False
        assert d["engine"]["active"] == "vader" and d["engine_comparison"] is None

    def test_aspect_breakdown_and_coverage(self, client, data):
        a = {x["aspect"]: x for x in client.get("/api/insights").json()["aspects"]}
        assert set(a) == {"food", "service", "ambience", "affordability", "hygiene", "waiting_time"}
        f = a["food"]
        assert f["mentions"] == f["positive"] + f["neutral"] + f["negative"] > 0 and f["restaurants_with_evidence"] >= 1
        assert 0 < f["review_coverage"] <= 1 and -1 <= f["net_score"] <= 1 and f["min_mentions_required"] == 5

    def test_neighbourhood_chart_ignores_its_own_filter_and_marks_selection(self, client, data):
        d = client.get("/api/insights?neighborhood=koramangala").json()
        assert d["scope"]["restaurants"] == 2
        hoods = {h["neighborhood"]: h for h in d["neighborhoods"]}
        assert set(hoods) == {"indiranagar", "koramangala"} and hoods["koramangala"]["selected"] and not hoods["indiranagar"]["selected"]
        assert hoods["indiranagar"]["restaurants"] == 11 and hoods["koramangala"]["reviews"] == 15

    def test_scope_responds_to_every_filter(self, client, data):
        full = client.get("/api/insights").json()["scope"]["reviews_analysed"]
        for q in ("sentiment=negative", "min_reviews=20", "aspect=hygiene", "cuisine=cafe", "neighborhood=koramangala"):
            assert client.get(f"/api/insights?{q}").json()["scope"]["reviews_analysed"] < full, q
        d = client.get("/api/insights?min_reviews=999").json()
        assert d["scope"]["restaurants"] == 0 and d["aspects"][0]["mentions"] == 0

    def test_gem_evidence(self, client, data):
        g = client.get("/api/insights").json()["hidden_gems"]
        assert [x["name"] for x in g["items"]] == ["Fixture Hidden Gem"]
        ev = g["items"][0]["evidence"]
        assert ev["analysed_reviews"] == 12 and ev["positive_reviews"] == 12 and 0.7 < ev["positive_lower_bound"] < 1
        assert ev["visibility_percentile"] is not None and g["status_counts"]["qualified"] == 1 and g["criteria"]["min_analysed_reviews"] == 8
        assert g["items"][0]["explanation"] and ev["praised_aspects"]

    def test_engine_comparison_appears_only_with_both_models(self, client, db, data):
        run_bert(db, model())
        d = client.get("/api/insights").json()
        assert d["engine"]["active"] == "bert" and d["engine_comparison"]["reviews_with_both"] == 130
        assert d["engine_comparison"]["matrix"] and 0 <= d["engine_comparison"]["agreement"] <= 1
        assert "not BERT" in d["aspect_method"]

    def test_time_trend_only_with_enough_dated_reviews(self, client, db, data):
        from datetime import datetime
        revs = db.scalars(select(Review).where(Review.restaurant_id.is_not(None))).all()
        for i, rv in enumerate(revs[:20]):
            rv.reviewed_at = datetime(2023, 1 + i % 4, 5)
        db.commit()
        t = client.get("/api/insights").json()["time_trend"]
        assert t["available"] is False and "100" in t["reason"]  # 20 dated reviews over 4 months is not a trend
        for i, rv in enumerate(revs):
            rv.reviewed_at = datetime(2023, 1 + i % 8, 5)
        db.commit()
        t = client.get("/api/insights").json()["time_trend"]
        assert t["available"] and len(t["series"]) == 8 and all(0 <= m["positive_share"] <= 1 for m in t["series"])

    def test_pipeline_endpoint(self, client, data):
        p = client.get("/api/analytics/pipeline").json()
        assert p["reviews_by_match_status"]["matched"] == 130 and p["import"]["listings_needs_review"] == 1
        assert p["import"]["dataset_note"] and p["engine"]["active"] == "vader"
