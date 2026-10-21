"""Historical review dataset importer (Kaggle "Zomato Bangalore Restaurants").

Dataset facts we rely on (and verify at runtime by inspecting the columns):
* one row per restaurant *listing*; the same restaurant can appear several times (one per `listed_in(type)`)
* `reviews_list` is a *Python-literal* string: "[('Rated 4.0', 'RATED\\n  text...'), ...]"
* there are NO coordinates and NO review dates -> reviews get `reviewed_at = NULL`; places are located only via OSM
* the dataset is a historical scrape (not current). The UI labels it as such.

Reviews are attributed to a restaurant only after `matching.match_source_record` finds name + area + address
corroboration. Everything else is flagged (`needs_review`/`ambiguous`) and excluded from analytics.
"""
from __future__ import annotations

import ast
import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.base import utcnow
from backend.models import ImportHistory, Restaurant, Review
from backend.nlp.preprocess import clean_text
from backend.services.matching import Candidate, match_source_record, normalize_name
from backend.services.neighborhoods import neighborhood_from_free_text

SOURCE = "zomato_kaggle"
REQUIRED_COLUMNS = ["name", "address", "location", "reviews_list"]
OPTIONAL_COLUMNS = ["url", "rate", "votes", "cuisines", "approx_cost(for two people)", "rest_type", "listed_in(city)"]


class DatasetError(ValueError):
    pass


# ---------------------------------------------------------------- parsing helpers
def parse_rating(value: Any) -> Optional[float]:
    """'4.1/5' -> 4.1 ; 'NEW', '-', '' -> None"""
    if value is None:
        return None
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(?:/\s*5)?\s*$", str(value))
    if not m:
        return None
    v = float(m.group(1))
    return v if 0 <= v <= 5 else None


def parse_votes(value: Any) -> Optional[int]:
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return int(digits) if digits else None


def parse_reviews_list(raw: Any) -> tuple[list[tuple[Optional[float], str]], int]:
    """Safely parse the serialized list. Returns ([(rating, cleaned_text)], malformed_count).

    Uses ast.literal_eval (never eval) so a malicious CSV cannot execute code.
    """
    if raw is None or not str(raw).strip() or str(raw).strip() == "[]":
        return [], 0
    try:
        data = ast.literal_eval(str(raw))
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return [], 1
    if not isinstance(data, (list, tuple)):
        return [], 1
    out, bad = [], 0
    for item in data:
        if not (isinstance(item, (list, tuple)) and len(item) == 2):
            bad += 1
            continue
        rating_raw, text_raw = item
        text = clean_text(text_raw)
        if text is None:
            bad += 1
            continue
        out.append((parse_rating(re.sub(r"(?i)rated", "", str(rating_raw))), text))
    return out, bad


def content_hash(key: str, text: str, rating: Optional[float]) -> str:
    base = f"{normalize_name(key)}|{re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()}|{rating}"
    return hashlib.sha256(base.encode()).hexdigest()


# ---------------------------------------------------------------- main entry
def import_zomato_csv(
    db: Session,
    path: str | Path,
    max_reviews: Optional[int] = None,
    store_unresolved: bool = True,
) -> ImportHistory:
    path = Path(path)
    history = ImportHistory(source=SOURCE, filename=str(path.name), status="running")
    db.add(history)
    db.commit()

    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8", encoding_errors="replace", on_bad_lines="skip")
    except Exception as e:  # unreadable file
        history.status, history.finished_at = "failed", utcnow()
        history.report = {"error": f"Could not read CSV: {e}"}
        db.commit()
        raise DatasetError(f"Could not read CSV: {e}") from e

    columns = list(df.columns)
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    report: dict[str, Any] = {
        "columns_found": columns,
        "missing_required_columns": missing,
        "optional_columns_present": [c for c in OPTIONAL_COLUMNS if c in columns],
        "rows_read": int(len(df)),
        "dataset_note": "Historical dataset – not current. No review dates are available in this source.",
    }
    if missing:
        history.status, history.finished_at, history.report = "failed", utcnow(), report
        db.commit()
        raise DatasetError(f"CSV is missing required columns: {missing}. Found: {columns}")

    # one entry per restaurant listing
    key_col = "url" if "url" in df.columns else None
    df["_key"] = df[key_col] if key_col else (df["name"].astype(str) + "|" + df["address"].astype(str))
    before = len(df)
    df = df.drop_duplicates(subset="_key")
    report["duplicate_listing_rows_removed"] = int(before - len(df))

    # candidate restaurants from OSM discovery
    cands_by_hood: dict[str, list[Candidate]] = {}
    for r in db.scalars(select(Restaurant).where(Restaurant.primary_source == "osm")):
        cands_by_hood.setdefault(r.neighborhood or "", []).append(Candidate(r.id, r.name, r.address, r.neighborhood))
    report["osm_restaurants_available_for_matching"] = sum(len(v) for v in cands_by_hood.values())

    existing_hashes = set(db.scalars(select(Review.content_hash)))
    counts: Counter = Counter()
    unmatched_samples: list[dict] = []
    matched_restaurants: set[int] = set()
    stop = False

    for row in df.to_dict("records"):
        name = str(row.get("name", "")).strip()
        address = str(row.get("address", "")).strip()
        hood = neighborhood_from_free_text(str(row.get("location", "")))
        key = str(row["_key"])

        if not name:
            counts["rows_without_name"] += 1
            continue
        if hood is None:
            counts["rows_outside_focus_areas"] += 1
            continue
        counts["rows_in_focus_areas"] += 1

        match = match_source_record(name, address, hood, cands_by_hood.get(hood, []))
        counts[f"match_{match.status}"] += 1
        if match.status == "no_candidate":
            # Not stored (no OSM record to place them on the map), but counted so the report shows the real loss.
            counts["reviews_unmatched_no_osm_record"] += len(parse_reviews_list(row.get("reviews_list", ""))[0])
            if len(unmatched_samples) < 50:
                unmatched_samples.append({"name": name, "address": address, "area": hood, "reason": match.evidence.get("reason")})
            continue  # not stored: no OSM counterpart => cannot be placed on the map
        if match.status in ("needs_review", "ambiguous") and not store_unresolved:
            continue

        reviews, malformed = parse_reviews_list(row.get("reviews_list", ""))
        counts["malformed_review_entries"] += malformed
        counts["review_entries_parsed"] += len(reviews)

        if match.status == "matched":
            matched_restaurants.add(match.restaurant_id)
            _attach_listing_metadata(db, match.restaurant_id, row)

        for rating, text in reviews:
            if max_reviews is not None and counts["reviews_imported_matched"] >= max_reviews and match.status == "matched":
                stop = True
                break
            h = content_hash(key, text, rating)
            if h in existing_hashes:
                counts["duplicate_reviews_skipped"] += 1
                continue
            existing_hashes.add(h)
            db.add(Review(
                restaurant_id=match.restaurant_id if match.status == "matched" else None,
                candidate_restaurant_id=match.candidate_id,
                match_status=match.status, match_confidence=match.confidence,
                match_evidence={**match.evidence, "source_name": name, "source_address": address},
                source=SOURCE, source_restaurant_key=key, source_restaurant_name=name,
                text=text, rating=rating, reviewed_at=None, content_hash=h, import_id=history.id,
            ))
            counts["reviews_imported_matched" if match.status == "matched" else "reviews_stored_unresolved"] += 1
        if stop:
            break

    db.commit()
    report.update(dict(counts))
    report["restaurants_with_verified_reviews"] = len(matched_restaurants)
    report["unmatched_restaurant_samples"] = unmatched_samples
    report["valid_reviews_imported"] = counts["reviews_imported_matched"]
    history.report, history.status, history.finished_at = report, "success", utcnow()
    db.commit()
    return history


def _attach_listing_metadata(db: Session, restaurant_id: int, row: dict) -> None:
    """Copy rating / vote count / price / cuisines from the matched listing, tagged with their source."""
    r = db.get(Restaurant, restaurant_id)
    rating = parse_rating(row.get("rate"))
    votes = parse_votes(row.get("votes"))
    if rating is not None:
        r.rating, r.rating_count, r.rating_source = rating, votes, SOURCE
    cost = re.sub(r"[^\d]", "", str(row.get("approx_cost(for two people)", "") or ""))
    if cost and not r.price_info:
        r.price_info, r.price_source, r.price_for_two = f"\u20b9{int(cost)} for two (historical)", SOURCE, int(cost)
    cuisines = str(row.get("cuisines", "") or "").strip()
    if cuisines and not r.cuisines:
        r.cuisines = ";".join(c.strip().lower() for c in cuisines.split(",") if c.strip())
        r.cuisine_source = SOURCE


def apply_verified_matches(db: Session, csv_path: str | Path) -> dict:
    """Apply manual verification. CSV columns: source_restaurant_key, restaurant_id, confirm (yes/no)."""
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    for col in ("source_restaurant_key", "restaurant_id", "confirm"):
        if col not in df.columns:
            raise DatasetError(f"verification file needs a '{col}' column")
    confirmed = rejected = reviews_updated = 0
    for row in df.itertuples(index=False):
        decision = str(row.confirm).strip().lower()
        if decision not in ("yes", "no"):
            continue
        q = select(Review).where(Review.source_restaurant_key == row.source_restaurant_key,
                                 Review.match_status.in_(("needs_review", "ambiguous")))
        revs = list(db.scalars(q))
        if decision == "yes":
            rid = int(row.restaurant_id)
            if db.get(Restaurant, rid) is None:
                continue
            for rv in revs:
                rv.restaurant_id, rv.match_status, rv.match_confidence = rid, "verified_manual", 1.0
            confirmed += 1
        else:
            for rv in revs:
                rv.match_status, rv.restaurant_id = "rejected", None
            rejected += 1
        reviews_updated += len(revs)
    db.commit()
    return {"confirmed_restaurants": confirmed, "rejected_restaurants": rejected, "reviews_updated": reviews_updated}
