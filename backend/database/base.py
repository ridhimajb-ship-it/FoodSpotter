from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Naive UTC timestamp (portable across SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    """ISO-8601 with an explicit UTC marker. Stored timestamps are naive UTC; without the 'Z' browsers read them as local time."""
    return None if dt is None else (dt.isoformat() + "Z" if dt.tzinfo is None else dt.isoformat())
