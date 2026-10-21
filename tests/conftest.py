"""Test configuration.

⚠ FIXTURE DATA: every restaurant and review created here is a synthetic, clearly fictional test fixture
("Fixture Bistro ..."). It exists only to exercise code paths in an isolated temporary database and must never be
presented as real production data. The real application database (data/foodspotter.db) is never touched.
"""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="foodspotter-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["DATA_DIR"] = str(_TMP)
os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["GOOGLE_PLACES_API_KEY"] = ""
os.environ["OVERPASS_MIN_INTERVAL_SECONDS"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.database.base import Base, utcnow  # noqa: E402
from backend.database.db import SessionLocal, engine  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import Location, Restaurant, RestaurantSourceId  # noqa: E402
from backend.services.matching import normalize_name  # noqa: E402

TMP = _TMP
ADMIN = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    app.state.session_factory = SessionLocal
    for attr in ("overpass_factory", "google_factory"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    return TestClient(app)


def add_restaurant(db, name, lat, lon, hood="indiranagar", address=None, cuisines=None, osm_id=None):
    r = Restaurant(
        name=name, name_normalized=normalize_name(name), address=address, neighborhood=hood,
        cuisines=cuisines, cuisine_source="osm" if cuisines else None, primary_source="osm",
        source_url=f"https://www.openstreetmap.org/{osm_id or 'node/%d' % abs(hash(name) % 10**8)}",
        first_discovered_at=utcnow(), last_verified_at=utcnow(),
    )
    r.location = Location(latitude=lat, longitude=lon, source="osm")
    r.source_ids.append(RestaurantSourceId(source="osm", source_id=osm_id or f"node/{abs(hash(name) % 10**8)}", role="primary"))
    db.add(r)
    db.commit()
    return r


POSITIVE = [
    "The food was delicious and the staff were friendly. Great ambience too!",
    "Loved the biryani, really tasty and the prices were reasonable.",
    "Excellent service, very attentive waiters and a cozy atmosphere.",
    "Amazing flavours, fresh ingredients and the place was spotless and clean.",
    "Superb dishes, quick service and good value for money.",
    "Wonderful experience, delicious pasta and lovely decor.",
    "Best dosa in the area, polite staff and affordable prices.",
    "Fantastic food, friendly service and a great vibe.",
    "Really good meal, tasty starters and the washrooms were clean.",
    "Great place, awesome food and reasonable bill.",
]
NEGATIVE = [
    "The food was bland and the service was slow. Overpriced for what you get.",
    "Terrible experience, rude staff and a dirty washroom.",
    "We waited forever for a table and the food was cold.",
    "Very expensive and the portions were tiny, not worth it.",
    "The ambience was noisy and cramped, will not return.",
]
MIXED = ["The pizza was delicious, but the service was slow and the prices were high."]


def zomato_row(name, address, location, rate, votes, reviews, url=None):
    """A row shaped like the Kaggle Zomato Bangalore file (reviews_list is a serialized Python list)."""
    return {
        "url": url or f"https://fixture.invalid/{normalize_name(name).replace(' ', '-')}",
        "address": address, "name": name, "online_order": "Yes", "book_table": "No", "rate": rate, "votes": str(votes),
        "phone": "", "location": location, "rest_type": "Casual Dining", "dish_liked": "", "cuisines": "North Indian, Chinese",
        "approx_cost(for two people)": "800", "reviews_list": repr([(f"Rated {r}", f"RATED\n  {t}") for r, t in reviews]),
        "menu_item": "[]", "listed_in(type)": "Delivery", "listed_in(city)": "Indiranagar",
    }
