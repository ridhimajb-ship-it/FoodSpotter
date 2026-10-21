import json

import httpx
import pytest
from sqlalchemy import select

from backend.config import Settings
from backend.integrations.google_places import GooglePlacesClient, GooglePlacesError
from backend.integrations.overpass import OverpassClient, OverpassError, build_query, parse_element
from backend.models import DiscoveryHistory, Restaurant, RestaurantSourceId
from backend.services.discovery import run_osm_discovery, start_run
from backend.services.google_verify import run_google_verification
from backend.services.neighborhoods import BY_KEY, neighborhood_for_point, neighborhood_from_free_text
from tests.conftest import TMP, add_restaurant

HOOD = [BY_KEY["indiranagar"]]


def el(i, name, lat=12.975, lon=77.64, etype="node", **tags):
    base = {"type": etype, "id": i, "tags": {"name": name, "amenity": "restaurant", **tags}}
    if etype == "node":
        base.update(lat=lat, lon=lon)
    else:
        base["center"] = {"lat": lat, "lon": lon}
    return base


class FakeOverpass:
    """Stands in for the network client; `docs` maps neighbourhood key -> elements, or raises."""

    def __init__(self, docs):
        self.docs = docs

    def fetch_bbox(self, key, bbox, use_cache=True):
        d = self.docs[key]
        if isinstance(d, Exception):
            raise d
        return {"elements": d, "fetched_at": "x", "from_cache": False}


def discover(db, docs, hoods=HOOD):
    run = start_run(db, "osm", [h.key for h in hoods])
    return run_osm_discovery(db, run, FakeOverpass(docs), neighborhoods=hoods)


class TestParse:
    def test_node_and_way_center(self):
        a = parse_element(el(1, "Fixture One", **{"addr:housenumber": "5", "addr:street": "Test Rd", "cuisine": "indian;north_indian"}))
        assert a["source_id"] == "node/1" and a["address"] == "5 Test Rd" and a["cuisines"] == ["indian", "north indian"]
        assert parse_element(el(2, "Fixture Way", etype="way"))["source_id"] == "way/2"

    def test_rejects_unnamed_and_coordinate_less(self):
        assert parse_element({"type": "node", "id": 3, "lat": 1, "lon": 1, "tags": {"amenity": "cafe"}}) is None
        assert parse_element({"type": "node", "id": 4, "tags": {"name": "No Coords"}}) is None
        assert parse_element({"type": "way", "id": 5, "tags": {"name": "No Center"}}) is None

    def test_query_is_bounded(self):
        q = build_query((12.9, 77.6, 13.0, 77.7))
        assert "12.9,77.6,13.0,77.7" in q and "out center tags" in q

    def test_smallest_box_wins_for_overlaps(self):
        assert neighborhood_for_point(12.975, 77.606).key == "church-street"
        assert neighborhood_from_free_text("Koramangala 5th Block") == "koramangala"
        assert neighborhood_from_free_text("Yelahanka") is None


class TestDiscovery:
    def test_baseline_then_new_discovery(self, db):
        r1 = discover(db, {"indiranagar": [el(1, "Fixture A"), el(2, "Fixture B", lat=12.98)]})
        assert r1.is_baseline and r1.new_count == 2 and r1.status == "success"
        r2 = discover(db, {"indiranagar": [el(1, "Fixture A"), el(2, "Fixture B", lat=12.98), el(3, "Fixture C", lat=12.97)]})
        assert not r2.is_baseline and r2.new_count == 1 and r2.updated_count == 2
        c = db.scalar(select(Restaurant).where(Restaurant.name == "Fixture C"))
        assert c.discovery_run_id == r2.id and c.opening_date is None
        a = db.scalar(select(Restaurant).where(Restaurant.name == "Fixture A"))
        assert a.discovery_run_id == r1.id  # baseline finds are not "new"

    def test_same_name_different_branch_stays_separate(self, db):
        discover(db, {"indiranagar": [el(1, "Fixture Chain", lat=12.970), el(2, "Fixture Chain", lat=12.985)]})
        assert db.query(Restaurant).count() == 2

    def test_node_plus_building_outline_merge_into_one_restaurant(self, db):
        r = discover(db, {"indiranagar": [el(1, "Fixture Dup", lat=12.9750, lon=77.6400), el(2, "Fixture Dup", lat=12.97505, lon=77.64003, etype="way")]})
        assert db.query(Restaurant).count() == 1 and r.merged_count == 1
        assert db.query(RestaurantSourceId).filter_by(role="alias").count() == 1

    def test_missing_restaurant_is_flagged_not_deleted(self, db):
        discover(db, {"indiranagar": [el(1, "Fixture A"), el(2, "Fixture B", lat=12.98)]})
        r2 = discover(db, {"indiranagar": [el(1, "Fixture A")]})
        b = db.scalar(select(Restaurant).where(Restaurant.name == "Fixture B"))
        assert r2.flagged_count == 1 and b.needs_recheck and "Not returned" in b.recheck_reason
        r3 = discover(db, {"indiranagar": [el(1, "Fixture A"), el(2, "Fixture B", lat=12.98)]})
        db.refresh(b)
        assert not b.needs_recheck and r3.new_count == 0

    def test_failed_neighbourhood_does_not_flag_its_restaurants(self, db):
        discover(db, {"indiranagar": [el(1, "Fixture A")]})
        r = discover(db, {"indiranagar": OverpassError("boom")})
        a = db.scalar(select(Restaurant))
        assert r.status == "failed" and not a.needs_recheck and r.errors

    def test_partial_failure_keeps_other_results(self, db):
        hoods = [BY_KEY["indiranagar"], BY_KEY["koramangala"]]
        r = discover(db, {"indiranagar": [el(1, "Fixture A")], "koramangala": OverpassError("timeout")}, hoods)
        assert r.status == "partial" and r.new_count == 1

    def test_failed_first_run_does_not_consume_the_baseline(self, db):
        discover(db, {"indiranagar": OverpassError("down")})
        ok = discover(db, {"indiranagar": [el(1, "Fixture A")]})
        assert ok.is_baseline


class TestOverpassClient:
    def settings(self, **kw):
        return Settings(data_dir=TMP, overpass_min_interval_seconds=0, overpass_urls="https://a.invalid/api,https://b.invalid/api", **kw)

    def client(self, handler, **kw):
        return OverpassClient(self.settings(**kw), httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)

    def test_fetch_and_cache(self):
        calls = []

        def handler(req):
            calls.append(str(req.url))
            return httpx.Response(200, json={"elements": [el(1, "Fixture A")]})

        c = self.client(handler)
        first = c.fetch_bbox("cachetest", (1, 1, 2, 2), use_cache=False)
        second = c.fetch_bbox("cachetest", (1, 1, 2, 2))
        assert not first["from_cache"] and second["from_cache"] and len(calls) == 1

    def test_falls_back_to_mirror_and_retries(self):
        seen = []

        def handler(req):
            seen.append(req.url.host)
            return httpx.Response(429) if req.url.host == "a.invalid" else httpx.Response(200, json={"elements": []})

        assert self.client(handler).fetch_bbox("fallback", (1, 1, 2, 2), use_cache=False)["elements"] == []
        assert seen.count("a.invalid") == 3 and seen[-1] == "b.invalid"

    def test_all_servers_down_raises(self):
        with pytest.raises(OverpassError):
            self.client(lambda req: httpx.Response(504)).fetch_bbox("down", (1, 1, 2, 2), use_cache=False)


class TestGoogle:
    def client(self, handler):
        return GooglePlacesClient("SECRET-KEY-123", httpx.Client(transport=httpx.MockTransport(handler)), min_interval=0, sleep=lambda s: None)

    def place(self, pid, name, lat, lon, status="OPERATIONAL"):
        return {"id": pid, "displayName": {"text": name}, "location": {"latitude": lat, "longitude": lon}, "businessStatus": status}

    def test_requires_key(self):
        with pytest.raises(GooglePlacesError):
            GooglePlacesClient("")

    def test_match_requires_name_and_location_agreement(self):
        def handler(req):
            return httpx.Response(200, json={"places": [
                self.place("far", "Fixture Bistro", 12.99, 77.70),            # same name, too far
                self.place("near-wrong-name", "Totally Different", 12.9750, 77.6400),
                self.place("good", "Fixture Bistro", 12.97505, 77.64003),
            ]})
        assert self.client(handler).find_matching_place("Fixture Bistro", 12.975, 77.64)["id"] == "good"

    def test_no_match_returns_none(self):
        c = self.client(lambda req: httpx.Response(200, json={"places": [self.place("far", "Fixture Bistro", 13.1, 77.9)]}))
        assert c.find_matching_place("Fixture Bistro", 12.975, 77.64) is None

    def test_quota_error_flagged_and_key_not_leaked(self):
        c = self.client(lambda req: httpx.Response(429, json={"error": {"message": "Quota exceeded"}}))
        with pytest.raises(GooglePlacesError) as e:
            c.search_text("x", 1, 1)
        assert e.value.quota and "SECRET-KEY-123" not in str(e.value)

    def test_key_sent_in_header_not_url(self):
        captured = {}

        def handler(req):
            captured["url"], captured["key"] = str(req.url), req.headers.get("x-goog-api-key")
            return httpx.Response(200, json={"places": []})

        self.client(handler).search_text("x", 1, 1)
        assert captured["key"] == "SECRET-KEY-123" and "SECRET" not in captured["url"]

    def test_verification_pass_links_ids_flags_closed_and_stops_on_quota(self, db):
        add_restaurant(db, "Fixture Open", 12.975, 77.640)
        add_restaurant(db, "Fixture Closed", 12.980, 77.645)
        state = {"n": 0}

        def handler(req):
            body = json.loads(req.content)
            name = body["textQuery"]
            lat = body["locationBias"]["circle"]["center"]["latitude"]
            lon = body["locationBias"]["circle"]["center"]["longitude"]
            status = "CLOSED_PERMANENTLY" if "Closed" in name else "OPERATIONAL"
            return httpx.Response(200, json={"places": [self.place("pid-" + name.split()[-1], name, lat, lon, status)]})

        run = start_run(db, "google", [])
        run_google_verification(db, run, self.client(handler))
        closed = db.scalar(select(Restaurant).where(Restaurant.name == "Fixture Closed"))
        opened = db.scalar(select(Restaurant).where(Restaurant.name == "Fixture Open"))
        assert closed.needs_recheck and "closed permanently" in closed.recheck_reason and not opened.needs_recheck
        assert db.query(RestaurantSourceId).filter_by(source="google_place_id").count() == 2

        # quota exhaustion stops the run immediately
        db2_run = start_run(db, "google", [])
        quota_client = self.client(lambda req: httpx.Response(429))
        r = run_google_verification(db, db2_run, quota_client)
        assert r.notes["quota_exceeded"] and len(r.errors) == 1
