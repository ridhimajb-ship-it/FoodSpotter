import httpx
import pandas as pd
import pytest

from backend.integrations.overpass import OverpassError
from backend.main import app
from backend.services.importer import import_zomato_csv
from backend.services.pipeline import refresh_analytics
from tests.conftest import ADMIN, MIXED, NEGATIVE, POSITIVE, TMP, add_restaurant, zomato_row


def many(texts, n, rating):
    return [(rating, texts[i % len(texts)] + f" Note {i}.") for i in range(n)]


@pytest.fixture()
def data(db):
    """Synthetic fixture world: a famous place, a hidden gem, a weak place, a thin-evidence place, an unmatched one."""
    famous = add_restaurant(db, "Fixture Famous Kitchen", 12.975, 77.640, "indiranagar", "1 Famous Road", "north indian;chinese")
    gem = add_restaurant(db, "Fixture Hidden Gem", 12.978, 77.644, "indiranagar", "2 Gem Lane", "south indian")
    weak = add_restaurant(db, "Fixture Weak Eatery", 12.930, 77.620, "koramangala", "3 Weak Street", "north indian")
    thin = add_restaurant(db, "Fixture Thin Cafe", 12.925, 77.625, "koramangala", "4 Thin Street", "cafe")
    noaddr = add_restaurant(db, "Fixture Unverified Diner", 12.970, 77.650, "indiranagar", None)
    # filler restaurants so visibility percentiles are meaningful
    fillers = []
    words = ["Amber", "Basil", "Cedar", "Dune", "Ember", "Fjord", "Grove", "Harbor"]
    rows = [
        zomato_row("Fixture Famous Kitchen", "1, Famous Road, Indiranagar", "Indiranagar", "4.4/5", 6000, many(POSITIVE, 30, 4.5) + many(NEGATIVE, 8, 2.0) + [(3.0, t) for t in MIXED]),
        zomato_row("Fixture Hidden Gem", "2, Gem Lane, Indiranagar", "Indiranagar", "4.5/5", 30, many(POSITIVE, 12, 4.5)),
        zomato_row("Fixture Weak Eatery", "3, Weak Street, Koramangala", "Koramangala 5th Block", "2.9/5", 700, many(NEGATIVE, 10, 1.5) + many(POSITIVE, 2, 4.0)),
        zomato_row("Fixture Thin Cafe", "4, Thin Street, Koramangala", "Koramangala", "5.0/5", 3, many(POSITIVE, 3, 5.0)),
        zomato_row("Fixture Unverified Diner", "9 Elsewhere", "Indiranagar", "4.1/5", 200, many(POSITIVE, 4, 4.0)),
    ]
    for i in range(8):
        w = words[i]
        f = add_restaurant(db, f"Fixture {w} Tavern", 12.96 + i / 1000, 77.63, "indiranagar", f"{w} Avenue")
        fillers.append(f)
        rows.append(zomato_row(f"Fixture {w} Tavern", f"{w} Avenue, Indiranagar", "Indiranagar", "3.8/5", 150 + 40 * i,
                               many(POSITIVE, 5, 4.0) + many(NEGATIVE, 3, 2.0)))
    p = TMP / "api_fixture.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    import_zomato_csv(db, p)
    refresh_analytics(db)
    return {"famous": famous, "gem": gem, "weak": weak, "thin": thin, "noaddr": noaddr}


class TestPublicApi:
    def test_health_and_meta(self, client, data):
        assert client.get("/api/health").json() == {"status": "ok"}
        m = client.get("/api/meta").json()
        assert m["totals"]["restaurants"] == 13 and any(n["key"] == "indiranagar" for n in m["neighborhoods"])
        assert m["features"]["google_live_reviews"] is False

    def test_list_filters_sort_and_pagination(self, client, data):
        all_ = client.get("/api/restaurants?limit=5").json()
        assert all_["total"] == 13 and len(all_["items"]) == 5
        assert client.get("/api/restaurants?neighborhood=koramangala").json()["total"] == 2
        assert client.get("/api/restaurants?cuisine=south indian").json()["items"][0]["name"] == "Fixture Hidden Gem"
        assert client.get("/api/restaurants?q=famous").json()["total"] == 1
        assert client.get("/api/restaurants?min_rating=4.4").json()["total"] == 3  # famous 4.4, gem 4.5, thin 5.0
        assert client.get("/api/restaurants?hidden_gems_only=true").json()["items"][0]["name"] == "Fixture Hidden Gem"
        names = [r["name"] for r in client.get("/api/restaurants?sort=name&limit=3").json()["items"]]
        assert names == sorted(names, key=str.lower)

    def test_unverified_diner_has_coordinates_but_no_attributed_reviews(self, client, data):
        d = client.get(f"/api/restaurants/{data['noaddr'].id}").json()
        assert d["review_count"] == 0 and d["rating"] is None
        assert client.get(f"/api/restaurants/{data['noaddr'].id}/reviews").json()["total"] == 0

    @pytest.mark.parametrize("bad", ["limit=0", "limit=99999", "offset=-1", "min_rating=9", "sort=bogus"])
    def test_validation(self, client, data, bad):
        assert client.get(f"/api/restaurants?{bad}").status_code == 422

    def test_like_wildcards_are_escaped(self, client, data):
        assert client.get("/api/restaurants?q=%25").json()["total"] == 0

    def test_search_suggestions(self, client, data):
        s = client.get("/api/restaurants/search?q=fixture hid").json()["suggestions"]
        assert s[0]["type"] == "restaurant" and s[0]["label"] == "Fixture Hidden Gem"
        types = {x["type"] for x in client.get("/api/restaurants/search?q=indira").json()["suggestions"]}
        assert "neighborhood" in types

    def test_detail_fields(self, client, data):
        d = client.get(f"/api/restaurants/{data['famous'].id}").json()
        assert d["rating"] == 4.4 and d["rating_count"] == 6000 and d["rating_source"] == "zomato_kaggle"
        assert "historical" in d["rating_note"] and d["directions_url"].startswith("https://www.google.com/maps/dir/?api=1&destination=12.975")
        assert d["source_attribution"] == "© OpenStreetMap contributors" and d["ranking_explanation"]
        assert d["opening_date"] is None
        assert client.get("/api/restaurants/999999").status_code == 404

    def test_reviews_carry_source_and_no_fabricated_dates(self, client, data):
        r = client.get(f"/api/restaurants/{data['famous'].id}/reviews?limit=5").json()
        assert r["total"] == 39 and r["items"][0]["reviewed_at"] is None and "not provided" in r["items"][0]["date_note"]
        assert "historical" in r["items"][0]["source_label"] and r["items"][0]["sentiment"]["label"]
        neg = client.get(f"/api/restaurants/{data['famous'].id}/reviews?sentiment=negative").json()
        assert neg["total"] >= 1 and all(i["sentiment"]["label"] == "negative" for i in neg["items"])

    def test_sentiment_endpoint(self, client, data):
        s = client.get(f"/api/restaurants/{data['famous'].id}/sentiment").json()
        assert s["available"] and s["analysed_reviews"] == 39 and abs(sum(s["share"].values()) - 1) < 0.01
        assert s["distribution"]["positive"] > s["distribution"]["negative"]
        assert sum(h["count"] for h in s["histogram"]) == 39
        assert not client.get(f"/api/restaurants/{data['noaddr'].id}/sentiment").json()["available"]

    def test_aspects_only_flagged_displayable_with_evidence(self, client, data):
        famous = client.get(f"/api/restaurants/{data['famous'].id}/aspects").json()
        by = {a["aspect"]: a for a in famous["aspects"]}
        assert by["food"]["sufficient_evidence"] and by["food"]["score"] > 0
        assert famous["summary"]["text"] and "food" in famous["summary"]["text"]
        thin = {a["aspect"]: a for a in client.get(f"/api/restaurants/{data['thin'].id}/aspects").json()["aspects"]}
        assert not any(a["sufficient_evidence"] for a in thin.values())  # only 3 reviews
        assert client.get(f"/api/restaurants/{data['thin'].id}/aspects").json()["summary"]["text"] is None

    def test_popular_never_claims_trending_without_dates(self, client, data):
        p = client.get("/api/restaurants/popular").json()
        assert p["label"] == "Popular Restaurants" and p["trending_available"] is False and p["time_trend"] == []
        names = [i["name"] for i in p["items"]]
        assert names.index("Fixture Famous Kitchen") < names.index("Fixture Thin Cafe")  # tiny sample does not win
        assert [i["popularity_rank"] for i in p["items"]] == sorted(i["popularity_rank"] for i in p["items"])

    def test_hidden_gems(self, client, data):
        g = client.get("/api/restaurants/hidden-gems").json()
        assert [i["name"] for i in g["items"]] == ["Fixture Hidden Gem"]
        assert "low review visibility" in g["items"][0]["gem_explanation"]
        assert g["insufficient_evidence_count"] >= 1 and g["criteria"]["min_analysed_reviews"] == 8
        assert client.get(f"/api/restaurants/{data['thin'].id}").json()["gem_status"] == "insufficient_evidence"

    def test_newly_discovered_empty_before_any_refresh(self, client, data):
        n = client.get("/api/restaurants/newly-discovered").json()
        assert n["items"] == [] and n["baseline_established"] is False and "NOT mean" in n["note"]

    def test_compare(self, client, data):
        ids = [data["famous"].id, data["weak"].id, data["gem"].id]
        c = client.post("/api/restaurants/compare", json={"ids": ids}).json()
        assert [i["id"] for i in c["items"]] == ids
        assert c["items"][0]["sentiment"]["distribution_share"]["positive"] > c["items"][1]["sentiment"]["distribution_share"]["positive"]
        assert "food" in c["items"][0]["aspects"]
        assert client.post("/api/restaurants/compare", json={"ids": [1]}).status_code == 422
        assert client.post("/api/restaurants/compare", json={"ids": [1, 1]}).status_code == 422
        assert client.post("/api/restaurants/compare", json={"ids": [1, 2, 3, 4]}).status_code == 422
        assert client.post("/api/restaurants/compare", json={"ids": [1, 999999]}).status_code == 404

    def test_analytics(self, client, data):
        o = client.get("/api/analytics/overview").json()
        assert o["restaurants"]["total"] == 13 and not o["empty"]
        assert o["reviews"]["analysed"] == 39 + 12 + 12 + 3 + 8 * 8
        assert o["reviews"]["by_match_status"].get("needs_review", 0) == 4  # unverified diner kept apart
        assert o["reviews"]["excluded_from_analytics"] == 4 and o["reviews"]["dated_reviews"] == 0
        assert sum(o["sentiment_distribution"].values()) == o["reviews"]["analysed"]
        cu = client.get("/api/analytics/cuisines?min_restaurants=1").json()
        assert any(c["cuisine"] == "North Indian" and c["restaurants"] == 10 for c in cu["distribution"])
        hoods = {h["neighborhood"]: h for h in client.get("/api/analytics/neighborhoods").json()["items"]}
        assert hoods["koramangala"]["restaurants"] == 2
        kw = client.get("/api/analytics/keywords").json()
        assert kw["basis"]["reviews"] == o["reviews"]["analysed"] and kw["overall"]

    def test_hotspot_metrics_are_distinct_and_described(self, client, data):
        d, r, p = (client.get(f"/api/analytics/hotspots?metric={m}").json() for m in ("density", "reviews", "popularity"))
        assert d["n_points"] == 13 and all(pt[2] == 1.0 for pt in d["points"])
        assert r["n_points"] == 12 and p["n_points"] == 12  # unverified diner has no weight for reviews/popularity
        assert len({d["description"], r["description"], p["description"]}) == 3 and "nothing about" in d["description"]
        assert client.get("/api/analytics/hotspots?metric=bogus").status_code == 422

    def test_live_reviews_disabled_without_key(self, client, data):
        r = client.get(f"/api/restaurants/{data['famous'].id}/live-reviews").json()
        assert r["configured"] is False and r["reviews"] == [] and r["stored"] is False

    def test_evaluation_endpoint_without_results(self, client, data, monkeypatch):
        from backend.api import meta
        monkeypatch.setattr(meta, "ROOT", TMP)
        assert client.get("/api/evaluation/latest").json()["available"] is False


class TestEmptyDatabase:
    def test_everything_degrades_gracefully(self, client):
        assert client.get("/api/restaurants").json()["items"] == []
        assert client.get("/api/analytics/overview").json()["empty"] is True
        assert client.get("/api/restaurants/popular").json()["items"] == []
        assert client.get("/api/restaurants/hidden-gems").json()["items"] == []
        assert client.get("/api/analytics/hotspots").json()["points"] == []
        assert client.get("/api/analytics/keywords").json()["overall"] == []


class TestAdmin:
    def test_requires_token(self, client, data):
        assert client.post("/api/admin/recompute").status_code == 401
        assert client.post("/api/admin/recompute", headers={"X-Admin-Token": "wrong"}).status_code == 401
        assert client.post("/api/admin/recompute", headers=ADMIN).status_code == 200
        assert client.get("/api/admin/runs").status_code == 401

    def test_disabled_when_no_token_configured(self, client, monkeypatch):
        from backend.config import get_settings
        monkeypatch.setattr(get_settings(), "admin_token", "")
        assert client.post("/api/admin/recompute", headers=ADMIN).status_code == 503

    def test_import_endpoint_rejects_paths_and_missing_files(self, client, data):
        for fn in ("../etc/passwd.csv", "sub/x.csv", "notes.txt"):
            assert client.post("/api/admin/import-dataset", headers=ADMIN, json={"filename": fn}).status_code == 400
        r = client.post("/api/admin/import-dataset", headers=ADMIN, json={"filename": "nope.csv"})
        assert r.status_code == 404 and "Kaggle" in r.json()["detail"]

    def test_import_endpoint_end_to_end(self, client, db):
        add_restaurant(db, "Fixture Hidden Gem", 12.978, 77.644, "indiranagar", "2 Gem Lane")
        pd.DataFrame([zomato_row("Fixture Hidden Gem", "2, Gem Lane, Indiranagar", "Indiranagar", "4.5/5", 30, many(POSITIVE, 5, 4.5))]).to_csv(TMP / "zomato.csv", index=False)
        r = client.post("/api/admin/import-dataset", headers=ADMIN, json={"filename": "zomato.csv"})
        assert r.status_code == 200 and r.json()["report"]["valid_reviews_imported"] == 5 and r.json()["analytics"]["reviews_analysed"] == 5

    def test_import_endpoint_reports_bad_schema(self, client, db):
        pd.DataFrame([{"foo": 1}]).to_csv(TMP / "bad_schema.csv", index=False)
        r = client.post("/api/admin/import-dataset", headers=ADMIN, json={"filename": "bad_schema.csv"})
        assert r.status_code == 422 and "reviews_list" in r.json()["detail"]

    def test_refresh_validation(self, client, db):
        assert client.post("/api/admin/refresh-restaurants", headers=ADMIN, json={"source": "bing"}).status_code == 422
        assert client.post("/api/admin/refresh-restaurants", headers=ADMIN, json={"neighborhoods": ["atlantis"]}).status_code == 422
        r = client.post("/api/admin/refresh-restaurants", headers=ADMIN, json={"source": "google"})
        assert r.status_code == 400 and "not configured" in r.json()["detail"]

    def test_refresh_flow_baseline_then_new(self, client, db):
        from tests.test_discovery_google import FakeOverpass, el
        state = {"docs": {"indiranagar": [el(1, "Fixture A"), el(2, "Fixture B", lat=12.98)]}}
        app.state.overpass_factory = lambda: FakeOverpass({"indiranagar": state["docs"]["indiranagar"], **{k: [] for k in
            ("koramangala", "jayanagar", "jp-nagar", "malleshwaram", "whitefield", "hsr-layout", "mg-road", "church-street")}})
        r = client.post("/api/admin/refresh-restaurants", headers=ADMIN, json={})
        assert r.status_code == 202 and r.json()["is_baseline"] is True
        n = client.get("/api/restaurants/newly-discovered").json()
        assert n["baseline_established"] and n["items"] == [] and n["last_run"]["status"] == "success" and n["last_run"]["found"] == 2
        assert client.get("/api/restaurants").json()["total"] == 2

        state["docs"]["indiranagar"].append(el(3, "Fixture Newcomer", lat=12.972))
        assert client.post("/api/admin/refresh-restaurants", headers=ADMIN, json={}).json()["is_baseline"] is False
        n = client.get("/api/restaurants/newly-discovered").json()
        assert [i["name"] for i in n["items"]] == ["Fixture Newcomer"] and n["items"][0]["first_discovered_at"].endswith("Z")

    def test_refresh_failure_is_recorded_not_stuck(self, client, db):
        class Down:
            def fetch_bbox(self, *a, **k):
                raise OverpassError("Overpass unavailable")
        app.state.overpass_factory = lambda: Down()
        assert client.post("/api/admin/refresh-restaurants", headers=ADMIN, json={"neighborhoods": ["indiranagar"]}).status_code == 202
        n = client.get("/api/restaurants/newly-discovered").json()
        assert n["last_run"]["status"] == "failed" and n["refresh_running"] is False and "Overpass unavailable" in n["last_run"]["errors"][0]
        assert client.post("/api/admin/refresh-restaurants", headers=ADMIN, json={"neighborhoods": ["indiranagar"]}).status_code == 202  # not blocked

    def test_live_reviews_with_mocked_google(self, client, data, monkeypatch):
        from backend.api import restaurants as R
        from backend.config import get_settings
        monkeypatch.setattr(get_settings(), "google_places_api_key", "k")
        real = R.GooglePlacesClient

        def handler(req):
            if req.url.path.endswith(":searchText"):
                return httpx.Response(200, json={"places": [{"id": "pid1", "displayName": {"text": "Fixture Famous Kitchen"}, "location": {"latitude": 12.975, "longitude": 77.640}}]})
            return httpx.Response(200, json={"id": "pid1", "rating": 4.2, "userRatingCount": 10, "googleMapsUri": "https://maps.google.com/?cid=1",
                                             "reviews": [{"rating": 5, "text": {"text": "Delicious food, lovely staff"}, "authorAttribution": {"displayName": "A. User"}}] * 7})
        monkeypatch.setattr(R, "GooglePlacesClient", lambda key, min_interval=0: real(key, httpx.Client(transport=httpx.MockTransport(handler)), min_interval=0, sleep=lambda s: None))
        r = client.get(f"/api/restaurants/{data['famous'].id}/live-reviews").json()
        assert r["configured"] and len(r["reviews"]) == 5 and r["stored"] is False  # capped at five
        assert r["reviews"][0]["sentiment"]["label"] == "positive" and "Google" in r["attribution"]
        # only the place id was persisted; review text was not
        assert client.get(f"/api/restaurants/{data['famous'].id}").json()["has_google_place_id"] is True
        assert client.get(f"/api/restaurants/{data['famous'].id}/reviews?limit=100").json()["total"] == 39
