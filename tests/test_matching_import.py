import ast

import pandas as pd
import pytest
from sqlalchemy import select

from backend.models import Restaurant, Review, SentimentResult
from backend.services.importer import (
    DatasetError, apply_verified_matches, canonical_listing_key, dedupe_existing_reviews, import_zomato_csv, parse_rating,
    parse_reviews_list, parse_votes,
)
from backend.services.pipeline import refresh_analytics
from backend.services.matching import Candidate, address_score, match_source_record, name_similarity, normalize_name
from tests.conftest import TMP, POSITIVE, add_restaurant, zomato_row


class TestMatching:
    def test_normalisation(self):
        assert normalize_name("The Fixture  Café & Grill!") == "fixture cafe and grill"

    def test_similar_but_different_names_do_not_match_by_name_alone(self):
        assert name_similarity("Fixture Bistro Alpha", "Fixture Bistro Beta") < 0.92

    def test_numbered_outlets_are_different_restaurants(self):
        assert name_similarity("Fixture Filler 0", "Fixture Filler 1") <= 0.5
        cands = [Candidate(1, "Fixture Outlet 1", "5 Same Road", "indiranagar")]
        assert match_source_record("Fixture Outlet 2", "5 Same Road", "indiranagar", cands).status == "no_candidate"

    def test_matched_requires_address_corroboration(self):
        cands = [Candidate(1, "Fixture Bistro Alpha", "12 Fixture Lane, Indiranagar", "indiranagar")]
        r = match_source_record("Fixture Bistro Alpha", "12, Fixture Lane, Indiranagar, Bangalore", "indiranagar", cands)
        assert r.status == "matched" and r.restaurant_id == 1

    def test_name_and_area_without_address_evidence_is_needs_review_not_matched(self):
        cands = [Candidate(1, "Fixture Bistro Alpha", None, "indiranagar")]
        r = match_source_record("Fixture Bistro Alpha", "12 Fixture Lane", "indiranagar", cands)
        assert r.status == "needs_review" and r.restaurant_id is None and r.candidate_id == 1

    def test_branches_in_different_areas_never_match(self):
        cands = [Candidate(1, "Fixture Bistro Alpha", "12 Fixture Lane", "koramangala")]
        assert match_source_record("Fixture Bistro Alpha", "12 Fixture Lane", "indiranagar", cands).status == "no_candidate"

    def test_two_same_name_branches_without_distinguishing_address_are_ambiguous(self):
        cands = [Candidate(1, "Fixture Chain", None, "indiranagar"), Candidate(2, "Fixture Chain", None, "indiranagar")]
        r = match_source_record("Fixture Chain", "5 Some Road", "indiranagar", cands)
        assert r.status == "ambiguous" and r.restaurant_id is None

    def test_address_picks_the_right_branch(self):
        cands = [Candidate(1, "Fixture Chain", "10 Alpha Road", "indiranagar"), Candidate(2, "Fixture Chain", "22 Beta Street", "indiranagar")]
        r = match_source_record("Fixture Chain", "22, Beta Street, Indiranagar", "indiranagar", cands)
        assert r.status == "matched" and r.restaurant_id == 2

    def test_address_score_none_without_evidence(self):
        assert address_score("anything", None) is None


class TestParsing:
    def test_parse_reviews_list_valid(self):
        raw = repr([("Rated 4.0", "RATED\n  Lovely food"), ("Rated 2.5", "RATED\n  Meh service")])
        reviews, bad = parse_reviews_list(raw)
        assert reviews == [(4.0, "Lovely food"), (2.5, "Meh service")] and bad == 0

    @pytest.mark.parametrize("raw", ["", "[]", None])
    def test_empty_inputs(self, raw):
        assert parse_reviews_list(raw) == ([], 0)

    def test_malformed_is_counted_not_raised(self):
        assert parse_reviews_list("[('Rated 4.0', 'unterminated")[1] == 1
        assert parse_reviews_list("{'a': 1}")[1] == 1
        reviews, bad = parse_reviews_list(repr([("Rated 4.0", "RATED\n  "), ("only-one",), ("Rated 3", "ok fine")]))
        assert len(reviews) == 1 and bad == 2

    def test_literal_eval_is_safe_against_code(self, tmp_path):
        marker = tmp_path / "pwned"
        parse_reviews_list(f"[__import__('pathlib').Path('{marker}').touch()]")
        assert not marker.exists()

    def test_rating_and_votes(self):
        assert parse_rating("4.1/5") == 4.1 and parse_rating("NEW") is None and parse_rating("-") is None and parse_rating("9/5") is None
        assert parse_votes("1,204") == 1204 and parse_votes("") is None


def write_csv(rows, name="fixture.csv", drop=()):
    df = pd.DataFrame(rows).drop(columns=list(drop))
    p = TMP / name
    df.to_csv(p, index=False)
    return p


def reviews(n, rating=4.0):
    return [(rating, POSITIVE[i % len(POSITIVE)] + f" Visit number {i}.") for i in range(n)]


class TestImport:
    def _setup(self, db):
        a = add_restaurant(db, "Fixture Bistro Alpha", 12.97, 77.64, "indiranagar", "12 Fixture Lane")
        add_restaurant(db, "Fixture Grill Gamma", 12.971, 77.641, "indiranagar", None)  # no address -> needs_review
        return a

    def rows(self):
        return [
            zomato_row("Fixture Bistro Alpha", "12, Fixture Lane, Indiranagar, Bangalore", "Indiranagar", "4.2/5", 900, reviews(6)),
            zomato_row("Fixture Bistro Alpha", "12, Fixture Lane, Indiranagar, Bangalore", "Indiranagar", "4.2/5", 900, reviews(6)),  # duplicate listing
            zomato_row("Fixture Grill Gamma", "7 Other Road", "Indiranagar", "3.9/5", 120, reviews(3)),
            zomato_row("Unknown Place Delta", "1 Nowhere", "Indiranagar", "4.0/5", 50, reviews(2)),
            zomato_row("Fixture Faraway", "9 Far Road", "Yelahanka", "4.0/5", 10, reviews(2)),
        ]

    def test_import_counts_and_attribution(self, db):
        alpha = self._setup(db)
        hist = import_zomato_csv(db, write_csv(self.rows()))
        rep = hist.report
        assert hist.status == "success"
        assert rep["valid_reviews_imported"] == 6
        assert rep["duplicate_listing_rows_removed"] == 1
        assert rep["rows_outside_focus_areas"] == 1
        assert rep["match_no_candidate"] == 1 and rep["match_needs_review"] == 1 and rep["match_matched"] == 1
        # verified reviews belong to Alpha only
        owned = db.scalars(select(Review).where(Review.restaurant_id == alpha.id)).all()
        assert len(owned) == 6 and all(r.match_status == "matched" and r.reviewed_at is None for r in owned)
        # unresolved reviews are stored but attached to NO restaurant
        unresolved = db.scalars(select(Review).where(Review.match_status == "needs_review")).all()
        assert len(unresolved) == 3 and all(r.restaurant_id is None and r.candidate_restaurant_id for r in unresolved)
        # rating metadata copied with provenance, only for the verified match
        db.refresh(alpha)
        assert (alpha.rating, alpha.rating_count, alpha.rating_source) == (4.2, 900, "zomato_kaggle")
        gamma = db.scalar(select(Restaurant).where(Restaurant.name == "Fixture Grill Gamma"))
        assert gamma.rating is None

    def test_reimport_is_idempotent(self, db):
        self._setup(db)
        p = write_csv(self.rows())
        import_zomato_csv(db, p)
        again = import_zomato_csv(db, p)
        assert again.report["valid_reviews_imported"] == 0 and again.report["duplicate_reviews_skipped"] == 9
        assert db.query(Review).count() == 9

    def test_max_reviews_cap(self, db):
        self._setup(db)
        assert import_zomato_csv(db, write_csv(self.rows(), "cap.csv"), max_reviews=4).report["valid_reviews_imported"] == 4

    def test_store_unresolved_false(self, db):
        self._setup(db)
        import_zomato_csv(db, write_csv(self.rows(), "nores.csv"), store_unresolved=False)
        assert db.query(Review).filter(Review.match_status == "needs_review").count() == 0

    def test_missing_columns_fail_loudly(self, db):
        with pytest.raises(DatasetError, match="reviews_list"):
            import_zomato_csv(db, write_csv(self.rows(), "bad.csv", drop=["reviews_list"]))

    def test_malformed_reviews_are_reported(self, db):
        self._setup(db)
        rows = self.rows()[:1]
        rows[0]["reviews_list"] = "[('Rated 4.0', 'RATED\\n  fine place'), ('broken',)]"
        rep = import_zomato_csv(db, write_csv(rows, "mal.csv")).report
        assert rep["malformed_review_entries"] == 1 and rep["valid_reviews_imported"] == 1

    def test_manual_verification_promotes_reviews(self, db):
        self._setup(db)
        import_zomato_csv(db, write_csv(self.rows()))
        gamma = db.scalar(select(Restaurant).where(Restaurant.name == "Fixture Grill Gamma"))
        key = db.scalar(select(Review.source_restaurant_key).where(Review.match_status == "needs_review"))
        v = TMP / "verify.csv"
        pd.DataFrame([{"source_restaurant_key": key, "restaurant_id": gamma.id, "confirm": "yes"}]).to_csv(v, index=False)
        out = apply_verified_matches(db, v)
        assert out["confirmed_restaurants"] == 1
        assert db.query(Review).filter(Review.restaurant_id == gamma.id, Review.match_status == "verified_manual").count() == 3


class TestDuplicateReviews:
    """The Kaggle file repeats one Zomato page under many URLs that differ only in a `?context=` tracking query."""

    URL = "https://www.zomato.com/bangalore/fixture-bistro-alpha-indiranagar"

    def _alpha(self, db):
        return add_restaurant(db, "Fixture Bistro Alpha", 12.97, 77.64, "indiranagar", "12 Fixture Lane")

    def _row(self, n, ctx, url=None):
        return zomato_row("Fixture Bistro Alpha", "12, Fixture Lane, Indiranagar, Bangalore", "Indiranagar", "4.2/5", 900,
                          reviews(n), url=f"{url or self.URL}?context={ctx}")

    def test_canonical_listing_key_drops_the_tracking_query(self):
        assert canonical_listing_key(self.URL + "?context=abc#top") == self.URL
        assert canonical_listing_key("Fixture Name|Fixture Address") == "Fixture Name|Fixture Address"

    def test_same_page_under_different_urls_is_stored_once(self, db):
        alpha = self._alpha(db)
        # three rows of one page: two repeat the same 6 reviews, the third carries 2 extra reviews that must be kept
        rep = import_zomato_csv(db, write_csv([self._row(6, "AAA"), self._row(6, "BBB"), self._row(8, "CCC")], "dup.csv")).report
        assert rep["duplicate_listing_rows_removed"] == 0
        assert rep["valid_reviews_imported"] == 8 and rep["duplicate_reviews_skipped"] == 12
        owned = db.scalars(select(Review).where(Review.restaurant_id == alpha.id)).all()
        assert len(owned) == 8 and len({r.text for r in owned}) == 8
        assert {r.source_restaurant_key for r in owned} == {self.URL}

    def test_different_pages_matched_to_one_restaurant_share_their_reviews(self, db):
        alpha = self._alpha(db)
        import_zomato_csv(db, write_csv([self._row(6, "A"), self._row(6, "B", url=self.URL + "-2")], "pages.csv"))
        assert db.query(Review).filter(Review.restaurant_id == alpha.id).count() == 6

    def test_unmatched_reviews_are_counted_once_per_page(self, db):
        self._alpha(db)
        rows = [zomato_row("Unknown Place Delta", "1 Nowhere", "Indiranagar", "4.0/5", 50, reviews(3),
                           url=f"https://www.zomato.com/bangalore/delta?context={c}") for c in ("A", "B")]
        rep = import_zomato_csv(db, write_csv(rows, "unm.csv")).report
        assert rep["review_entries_unmatched_no_osm_record"] == 6 and rep["reviews_unmatched_no_osm_record"] == 3

    def test_dedupe_existing_reviews_repairs_older_imports(self, db):
        alpha = self._alpha(db)
        import_zomato_csv(db, write_csv([self._row(4, "AAA")], "old.csv"))
        # what the previous importer did: the same reviews stored again under another listing URL
        for i, rv in enumerate(db.scalars(select(Review)).all()):
            db.add(Review(restaurant_id=alpha.id, match_status="matched", source="zomato_kaggle",
                          source_restaurant_key=self.URL + "?context=OLD", text=rv.text, rating=rv.rating, content_hash=f"legacy-{i}"))
        db.commit()
        refresh_analytics(db)
        assert db.query(Review).count() == 8 and db.query(SentimentResult).count() == 8
        assert dedupe_existing_reviews(db)["duplicate_reviews_removed"] == 4
        assert db.query(Review).count() == 4 and db.query(SentimentResult).count() == 4  # analysis rows cascade
        assert db.query(Review).filter(Review.source_restaurant_key != self.URL).count() == 0
        assert dedupe_existing_reviews(db)["duplicate_reviews_removed"] == 0  # idempotent

    def test_manual_verification_does_not_duplicate_a_matched_review(self, db):
        alpha = self._alpha(db)
        elsewhere = "https://www.zomato.com/bangalore/fixture-bistro-alpha-elsewhere?context=Z"
        unresolved = zomato_row("Fixture Bistro Alpha", "99 Unrelated Street", "Indiranagar", "4.2/5", 900, reviews(4), url=elsewhere)
        import_zomato_csv(db, write_csv([self._row(3, "AAA"), unresolved], "ver.csv"))
        assert db.query(Review).filter(Review.match_status == "needs_review").count() == 4
        v = TMP / "verify-dup.csv"
        pd.DataFrame([{"source_restaurant_key": elsewhere, "restaurant_id": alpha.id, "confirm": "yes"}]).to_csv(v, index=False)
        assert apply_verified_matches(db, v)["duplicates_not_promoted"] == 3
        assert db.query(Review).filter(Review.restaurant_id == alpha.id).count() == 4
        assert db.query(Review).filter(Review.match_status == "duplicate").count() == 3
