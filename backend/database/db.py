from __future__ import annotations

from typing import Iterator

import re

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import get_settings
from backend.database.base import Base

settings = get_settings()
_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    future=True,
)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
    if dbapi_conn.__class__.__module__.startswith("sqlite3"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(bind: Engine | None = None) -> None:
    from backend import models  # noqa: F401  (register tables)

    target = bind or engine
    Base.metadata.create_all(target)  # also creates tables added in later versions (e.g. bert_sentiment_results)
    _upgrade_existing(target)


def _upgrade_existing(target: Engine) -> None:
    """create_all never alters existing tables, so add columns introduced after a database was first created."""
    insp = inspect(target)
    if "restaurants" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("restaurants")}
    with target.begin() as conn:
        if "price_for_two" not in cols:
            conn.execute(text("ALTER TABLE restaurants ADD COLUMN price_for_two INTEGER"))
        rows = conn.execute(text("SELECT id, price_info FROM restaurants WHERE price_for_two IS NULL AND price_info IS NOT NULL")).all()
        for rid, info in rows:  # backfill from the historical "₹800 for two" text
            m = re.search(r"(\d[\d,]*)", info or "")
            if m:
                conn.execute(text("UPDATE restaurants SET price_for_two = :v WHERE id = :i"), {"v": int(m.group(1).replace(",", "")), "i": rid})


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
