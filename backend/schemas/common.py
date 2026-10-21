from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

T = TypeVar("T")


def _iso(d: datetime) -> str:
    return d.isoformat() + "Z" if d.tzinfo is None else d.isoformat()


UTCDatetime = Annotated[datetime, PlainSerializer(_iso, return_type=str, when_used="json")]


class RestaurantSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    address: Optional[str] = None
    neighborhood: Optional[str] = None
    neighborhood_label: Optional[str] = None
    cuisines: list[str] = []
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    rating_source: Optional[str] = None
    price_info: Optional[str] = None
    review_count: int = 0
    positive_share: Optional[float] = None
    popularity_score: Optional[float] = None
    popularity_rank: Optional[int] = None
    hidden_gem_score: Optional[float] = None
    gem_status: str = "insufficient_evidence"
    confidence: Optional[float] = None
    needs_recheck: bool = False
    first_discovered_at: Optional[UTCDatetime] = None


class RestaurantDetail(RestaurantSummary):
    source: Optional[str] = None
    source_url: Optional[str] = None
    source_attribution: Optional[str] = None
    rating_note: Optional[str] = None
    price_source: Optional[str] = None
    last_verified_at: Optional[UTCDatetime] = None
    recheck_reason: Optional[str] = None
    opening_date: Optional[str] = None
    ranking_explanation: list[str] = []
    ranking_components: dict = {}
    gem_explanation: Optional[str] = None
    visibility_percentile: Optional[float] = None
    directions_url: Optional[str] = None
    has_google_place_id: bool = False


class Page(BaseModel, Generic[T]):
    total: int
    limit: int
    offset: int
    items: list[T]


class CompareRequest(BaseModel):
    ids: list[int] = Field(min_length=2, max_length=3)

    @field_validator("ids")
    @classmethod
    def unique(cls, v: list[int]) -> list[int]:
        if len(set(v)) != len(v):
            raise ValueError("restaurant ids must be distinct")
        return v


class ImportRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255, description="CSV file inside the server's data/ directory")
    max_reviews: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    store_unresolved: bool = True


class RefreshRequest(BaseModel):
    source: str = Field(default="osm", pattern="^(osm|google)$")
    neighborhoods: Optional[list[str]] = None
    use_cache: bool = True
    google_limit: int = Field(default=50, ge=1, le=500)
