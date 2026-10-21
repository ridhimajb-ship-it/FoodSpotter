"""Application settings. All values can be overridden via environment variables or .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # --- storage ---
    database_url: str = f"sqlite:///{(ROOT / 'data' / 'foodspotter.db').as_posix()}"
    data_dir: Path = ROOT / "data"

    # --- security ---
    # Admin endpoints are DISABLED (503) until ADMIN_TOKEN is set.
    admin_token: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- external sources ---
    google_places_api_key: str = ""  # optional; never sent to the frontend
    overpass_urls: str = (
        "https://overpass-api.de/api/interpreter,"
        "https://overpass.kumi.systems/api/interpreter"
    )
    overpass_min_interval_seconds: float = 5.0  # polite spacing between requests
    overpass_cache_hours: int = 24
    overpass_user_agent: str = "FoodSpotter/0.1 (academic WSMA mini project)"
    google_min_interval_seconds: float = 0.2

    # --- scheduler ---
    enable_scheduler: bool = False
    discovery_interval_hours: int = 168

    # --- ranking (configurable weights; renormalised over available components) ---
    w_rating: float = 0.35
    w_volume: float = 0.25
    w_sentiment: float = 0.30
    w_recency: float = 0.10
    rating_prior_strength: float = 50.0  # m in the Bayesian average
    sentiment_prior_strength: float = 5.0
    recency_window_days: int = 365

    # --- hidden gems ---
    gem_min_reviews: int = 8
    gem_min_wilson_lb: float = 0.55
    gem_max_visibility_pct: float = 0.50
    gem_min_rating: float = 3.8

    # --- sentiment engine ---
    # "auto": use BERT once it covers >= bert_auto_min_coverage of the matched reviews, else the VADER baseline.
    sentiment_engine: str = "auto"  # auto | bert | vader
    enable_bert: bool = False  # run BERT inside refresh_analytics (needs requirements-bert.txt and a one-off model download)
    bert_model_id: str = "nlptown/bert-base-multilingual-uncased-sentiment"
    bert_model_revision: str = ""  # pin a Hugging Face commit hash for reproducible results
    bert_batch_size: int = 16
    bert_max_length: int = 512
    bert_auto_min_coverage: float = 0.95

    # --- NLP ---
    sentiment_pos_threshold: float = 0.05
    sentiment_neg_threshold: float = -0.05
    aspect_label_threshold: float = 0.25
    min_aspect_mentions: int = 5  # evidence needed before an aspect score is displayed
    min_summary_reviews: int = 3

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def overpass_url_list(self) -> list[str]:
        return [u.strip() for u in self.overpass_urls.split(",") if u.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    (s.data_dir / "cache").mkdir(parents=True, exist_ok=True)
    return s
