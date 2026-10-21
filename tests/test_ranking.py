import math

import pytest

from backend.config import Settings
from backend.services.ranking import RankInput, bayesian_rating, compute_rankings, percentile_rank, shrunk_share, wilson_lower_bound

S = Settings()


def run(rows):
    return compute_rankings(rows, S)


class TestMath:
    def test_bayesian_rating_shrinks_small_samples(self):
        assert bayesian_rating(5.0, 3, 3.5, 50) < 3.6
        assert bayesian_rating(5.0, 5000, 3.5, 50) > 4.9

    def test_wilson_penalises_small_n(self):
        assert wilson_lower_bound(3, 3) < wilson_lower_bound(90, 100)
        assert wilson_lower_bound(0, 0) == 0.0

    def test_shrunk_share_between_prior_and_raw(self):
        assert 0.5 < shrunk_share(3, 3, 0.5, 5) < 1.0

    def test_percentile(self):
        assert percentile_rank(5, [1, 2, 3, 4, 5]) == 0.8


class TestPopularity:
    def test_tiny_sample_does_not_outrank_established_restaurant(self):
        rows = [
            RankInput(1, rating=4.3, rating_count=2500, n_reviews=40, n_pos=30, n_neg=5, n_neu=5),
            RankInput(2, rating=5.0, rating_count=3, n_reviews=3, n_pos=3),
            RankInput(3, rating=3.5, rating_count=400, n_reviews=20, n_pos=10, n_neg=6, n_neu=4),
        ]
        out = run(rows)
        assert out[1].popularity_rank == 1
        assert out[2].popularity_score < out[1].popularity_score

    def test_restaurant_without_data_is_unranked_with_reason(self):
        out = run([RankInput(1), RankInput(2, rating=4.0, rating_count=100, n_reviews=5, n_pos=4)])
        assert out[1].popularity_score is None and out[1].popularity_rank is None
        assert "Not ranked" in out[1].explanation[0]

    def test_missing_components_are_renormalised_not_zeroed(self):
        # sentiment only, no rating/votes: score must reflect sentiment alone, not be dragged down by absent components
        out = run([RankInput(1, n_reviews=10, n_pos=9, n_neg=1), RankInput(2, n_reviews=10, n_pos=9, n_neg=1)])
        assert out[1].popularity_score > 60
        assert set(out[1].components) == {"sentiment", "volume"}

    def test_recency_only_used_when_dates_exist(self):
        out = run([RankInput(1, rating=4, rating_count=100, n_reviews=10, n_pos=8), RankInput(2, rating=4, rating_count=100, n_reviews=10, n_pos=8, recent_share=0.9)])
        assert "recency" not in out[1].components and "recency" in out[2].components
        assert any("no dates" in e for e in out[1].explanation)

    def test_explanations_present_and_deterministic(self):
        rows = [RankInput(1, rating=4.0, rating_count=100, n_reviews=10, n_pos=8)]
        assert run(rows)[1].explanation == run(rows)[1].explanation and len(run(rows)[1].explanation) >= 3

    def test_weights_are_configurable(self):
        rows = [RankInput(1, rating=5.0, rating_count=500, n_reviews=20, n_pos=2, n_neg=18),
                RankInput(2, rating=3.0, rating_count=500, n_reviews=20, n_pos=19, n_neg=1)]
        rating_heavy = compute_rankings(rows, Settings(w_rating=1, w_volume=0, w_sentiment=0.01))
        sent_heavy = compute_rankings(rows, Settings(w_rating=0.01, w_volume=0, w_sentiment=1))
        assert rating_heavy[1].popularity_rank == 1 and sent_heavy[2].popularity_rank == 1


class TestHiddenGems:
    def base(self):
        # one famous place (huge visibility) + many mid places so percentiles are meaningful
        rows = [RankInput(100, rating=4.4, rating_count=5000, n_reviews=60, n_pos=45, n_neg=10, n_neu=5)]
        rows += [RankInput(i, rating=3.8, rating_count=100 + 20 * i, n_reviews=15, n_pos=9, n_neg=4, n_neu=2) for i in range(1, 9)]
        return rows

    def test_qualified_gem(self):
        rows = self.base() + [RankInput(200, rating=4.4, rating_count=25, n_reviews=14, n_pos=13, n_neg=1)]
        o = run(rows)[200]
        assert o.gem_status == "qualified" and o.hidden_gem_score > 0
        assert "low review visibility" in o.gem_explanation

    def test_insufficient_evidence_gives_reason_not_score(self):
        o = run(self.base() + [RankInput(201, rating=4.9, rating_count=4, n_reviews=3, n_pos=3)])[201]
        assert o.gem_status == "insufficient_evidence" and o.hidden_gem_score is None
        assert "at least" in o.gem_explanation

    def test_popular_place_is_not_a_hidden_gem(self):
        o = run(self.base())[100]
        assert o.gem_status == "not_low_visibility" and o.hidden_gem_score is None

    def test_mostly_negative_is_not_a_gem(self):
        o = run(self.base() + [RankInput(202, rating=4.0, rating_count=20, n_reviews=12, n_pos=5, n_neg=7)])[202]
        assert o.gem_status == "not_positive_enough"

    def test_more_evidence_scores_higher_than_less_at_same_share(self):
        rows = self.base() + [RankInput(300, rating=4.4, rating_count=25, n_reviews=10, n_pos=9, n_neg=1),
                              RankInput(301, rating=4.4, rating_count=25, n_reviews=40, n_pos=36, n_neg=4)]
        o = run(rows)
        assert o[301].hidden_gem_score > o[300].hidden_gem_score
