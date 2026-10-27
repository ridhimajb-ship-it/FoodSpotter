# Data sources, licensing and what is stored

| Data | Source | Stored? | Notes |
|---|---|---|---|
| Restaurant names, coordinates, addresses, cuisine tags | OpenStreetMap via Overpass API | Yes (cached 24 h on disk + DB) | ODbL – attribution "© OpenStreetMap contributors" shown in UI. Bounded per-neighbourhood queries, ≥5 s spacing, mirror fallback. |
| Historical reviews, star ratings, vote counts, price for two | Kaggle "Zomato Bangalore Restaurants" (user downloads it) | Yes | Historical snapshot; **no review dates and no coordinates** in this dataset, so `reviewed_at` stays NULL and recency is never used. Check the dataset licence before redistributing. |
| Live reviews / ratings | Google Places API (New), optional | **No** – only the Place ID is stored | Max 5 reviews per place (not bypassed). Shown with attribution, only in the details panel, never as map markers, never used in rankings. |
| Demo fixtures | tests/ only | Temp DB only | Fictional "Fixture …" names; never loaded into the real database. |

Not used: scraping of Google Maps, Zomato or any other restricted service.

## Identity matching rules
A review is attributed to a restaurant only when **name (≥0.92 similarity) + neighbourhood + address overlap (≥50 % of OSM address tokens)** all agree.
Name+area without address evidence → `needs_review`; several equally good branches → `ambiguous`; no same-area name match → not stored.
Unresolved reviews have `restaurant_id = NULL` and are excluded from every metric. Resolve them with `scripts/import_reviews.py --verify decisions.csv`.
Same-name restaurants >30 m apart remain separate branches.

## Duplicate reviews
Every row of the Kaggle file has a different URL only because of a per-row `?context=` tracking parameter: the 51,717 rows
cover 12,453 Zomato pages, and rows of the same page repeat its reviews. Rows are kept (some carry extra reviews), but each
review is stored once per restaurant (verified matches) or once per page URL without the query (unresolved reviews), keyed on
normalised text + star rating. Databases imported before this rule are repaired with
`python scripts/import_reviews.py --dedupe-only`; every import also runs this repair first.

## "Newly discovered"
First successful run per source = baseline (nothing is "new"). Later runs mark unseen identifiers as newly discovered **by FoodSpotter**; opening dates are never inferred. Restaurants missing from a later successful query are flagged `needs_recheck`, never deleted.
