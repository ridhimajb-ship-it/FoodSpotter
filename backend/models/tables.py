"""SQLAlchemy models. Portable to PostgreSQL (generic types, JSON columns, no SQLite-only features)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base, utcnow


class DiscoveryHistory(Base):
    __tablename__ = "discovery_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # osm | google
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|partial|failed
    # The first successful run only establishes a baseline: everything it finds is
    # "already existing", so it must not be advertised as "newly discovered".
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    neighborhoods: Mapped[Optional[list]] = mapped_column(JSON)
    found_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    merged_count: Mapped[int] = mapped_column(Integer, default=0)
    flagged_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[Optional[list]] = mapped_column(JSON)
    notes: Mapped[Optional[dict]] = mapped_column(JSON)


class ImportHistory(Base):
    __tablename__ = "import_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(512))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="running")
    report: Mapped[Optional[dict]] = mapped_column(JSON)


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    name_normalized: Mapped[str] = mapped_column(String(300), index=True)
    address: Mapped[Optional[str]] = mapped_column(Text)
    neighborhood: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    cuisines: Mapped[Optional[str]] = mapped_column(Text)  # ';'-joined, lower-case
    cuisine_source: Mapped[Optional[str]] = mapped_column(String(32))
    amenity: Mapped[Optional[str]] = mapped_column(String(32))

    rating: Mapped[Optional[float]] = mapped_column(Float)
    rating_count: Mapped[Optional[int]] = mapped_column(Integer)
    rating_source: Mapped[Optional[str]] = mapped_column(String(64))
    price_info: Mapped[Optional[str]] = mapped_column(String(128))
    price_for_two: Mapped[Optional[int]] = mapped_column(Integer, index=True)  # numeric, historical, INR
    price_source: Mapped[Optional[str]] = mapped_column(String(64))

    primary_source: Mapped[str] = mapped_column(String(32), default="osm")
    source_url: Mapped[Optional[str]] = mapped_column(String(512))
    first_discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    discovery_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("discovery_history.id"))
    needs_recheck: Mapped[bool] = mapped_column(Boolean, default=False)
    recheck_reason: Mapped[Optional[str]] = mapped_column(String(200))
    # Only ever filled from an independently verified source. Currently always NULL.
    opening_date: Mapped[Optional[date]] = mapped_column(Date)

    location: Mapped["Location"] = relationship(back_populates="restaurant", uselist=False, cascade="all, delete-orphan")
    source_ids: Mapped[list["RestaurantSourceId"]] = relationship(back_populates="restaurant", cascade="all, delete-orphan")
    reviews: Mapped[list["Review"]] = relationship(back_populates="restaurant", foreign_keys="Review.restaurant_id")
    ranking: Mapped[Optional["RestaurantRanking"]] = relationship(back_populates="restaurant", uselist=False, cascade="all, delete-orphan")
    discovery_run: Mapped[Optional[DiscoveryHistory]] = relationship()


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), unique=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32))  # where the coordinates came from
    verified_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    restaurant: Mapped[Restaurant] = relationship(back_populates="location")

    __table_args__ = (Index("ix_locations_latlon", "latitude", "longitude"),)


class RestaurantSourceId(Base):
    __tablename__ = "restaurant_source_ids"

    id: Mapped[int] = mapped_column(primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32))  # osm | google_place_id
    source_id: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="primary")  # primary | alias
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    restaurant: Mapped[Restaurant] = relationship(back_populates="source_ids")

    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_source_identifier"),)


class Review(Base):
    """A review from the *historical* dataset. Live Google reviews are never stored (provider terms)."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Verified owner. NULL while the match is unresolved.
    restaurant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("restaurants.id", ondelete="SET NULL"), index=True)
    candidate_restaurant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("restaurants.id", ondelete="SET NULL"))
    match_status: Mapped[str] = mapped_column(String(20), index=True)
    # matched | verified_manual | needs_review | ambiguous | rejected
    match_confidence: Mapped[Optional[float]] = mapped_column(Float)
    match_evidence: Mapped[Optional[dict]] = mapped_column(JSON)

    source: Mapped[str] = mapped_column(String(48))  # zomato_kaggle
    source_restaurant_key: Mapped[Optional[str]] = mapped_column(String(512), index=True)
    source_restaurant_name: Mapped[Optional[str]] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    rating: Mapped[Optional[float]] = mapped_column(Float)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)  # NULL when the source gives no date
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    import_id: Mapped[Optional[int]] = mapped_column(ForeignKey("import_history.id"))
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    restaurant: Mapped[Optional[Restaurant]] = relationship(back_populates="reviews", foreign_keys=[restaurant_id])
    sentiment: Mapped[Optional["SentimentResult"]] = relationship(back_populates="review", uselist=False, cascade="all, delete-orphan")
    aspects: Mapped[list["AspectSentiment"]] = relationship(back_populates="review", cascade="all, delete-orphan")
    bert: Mapped[Optional["BertSentimentResult"]] = relationship(back_populates="review", uselist=False, cascade="all, delete-orphan")


class SentimentResult(Base):
    __tablename__ = "sentiment_results"

    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), primary_key=True)
    compound: Mapped[float] = mapped_column(Float)
    pos: Mapped[float] = mapped_column(Float)
    neu: Mapped[float] = mapped_column(Float)
    neg: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(10), index=True)  # positive|negative|neutral
    model: Mapped[str] = mapped_column(String(48))
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    review: Mapped[Review] = relationship(back_populates="sentiment")


class BertSentimentResult(Base):
    """Output of the BERT sentiment model. Kept separate from the VADER baseline so the two can be compared."""

    __tablename__ = "bert_sentiment_results"

    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), primary_key=True)
    label: Mapped[str] = mapped_column(String(10), index=True)  # positive|negative|neutral (1-2 stars / 3 / 4-5 stars)
    confidence: Mapped[float] = mapped_column(Float)  # probability mass of the winning three-way class
    p_negative: Mapped[float] = mapped_column(Float)
    p_neutral: Mapped[float] = mapped_column(Float)
    p_positive: Mapped[float] = mapped_column(Float)
    polarity: Mapped[float] = mapped_column(Float)  # p_positive - p_negative, in [-1, 1]
    star_probs: Mapped[list] = mapped_column(JSON)  # [P(1 star) .. P(5 stars)] exactly as predicted
    expected_stars: Mapped[float] = mapped_column(Float)
    predicted_stars: Mapped[int] = mapped_column(Integer)
    truncated: Mapped[Optional[bool]] = mapped_column(Boolean)  # review longer than the model's token limit; NULL = unknown
    model_id: Mapped[str] = mapped_column(String(200))
    model_revision: Mapped[Optional[str]] = mapped_column(String(64))
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    review: Mapped[Review] = relationship(back_populates="bert")


class AspectSentiment(Base):
    __tablename__ = "aspect_sentiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), index=True)
    aspect: Mapped[str] = mapped_column(String(24), index=True)
    label: Mapped[str] = mapped_column(String(10))
    score: Mapped[float] = mapped_column(Float)
    evidence: Mapped[Optional[str]] = mapped_column(Text)  # the clause that triggered the aspect

    review: Mapped[Review] = relationship(back_populates="aspects")

    __table_args__ = (UniqueConstraint("review_id", "aspect", name="uq_review_aspect"),)


class RestaurantRanking(Base):
    __tablename__ = "restaurant_rankings"

    restaurant_id: Mapped[int] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"), primary_key=True)
    popularity_score: Mapped[Optional[float]] = mapped_column(Float)
    popularity_rank: Mapped[Optional[int]] = mapped_column(Integer)
    hidden_gem_score: Mapped[Optional[float]] = mapped_column(Float)
    gem_status: Mapped[str] = mapped_column(String(32), default="insufficient_evidence")
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    visibility_percentile: Mapped[Optional[float]] = mapped_column(Float)
    components: Mapped[Optional[dict]] = mapped_column(JSON)
    explanation: Mapped[Optional[list]] = mapped_column(JSON)
    gem_explanation: Mapped[Optional[str]] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    restaurant: Mapped[Restaurant] = relationship(back_populates="ranking")
