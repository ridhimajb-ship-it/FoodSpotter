# FoodSpotter

Geospatial restaurant discovery for Bengaluru with review sentiment, aspect-based analysis, confidence-aware popularity ranking, hidden-gem discovery and newly-discovered tracking. WSMA mini project.

**No fabricated data.** Restaurants/coordinates come from OpenStreetMap; reviews from the historical Kaggle Zomato dataset you download; Google Places is optional. With no data loaded the app shows labelled empty states with import instructions.

## Quick start

> **Windows / VS Code (no `make`):** follow [docs/WINDOWS_SETUP.md](docs/WINDOWS_SETUP.md).


```bash
make setup                       # venv + pip + npm install
cp .env.example .env             # set ADMIN_TOKEN (admin endpoints are disabled without it)

# 1. restaurants from OpenStreetMap (nine neighbourhoods; ~1 min with polite rate limiting)
make discover                    # or: python scripts/discover_restaurants.py --only indiranagar

# 2. historical reviews: download the Kaggle CSV, save as data/zomato.csv
#    https://www.kaggle.com/datasets/himanshupoddar/zomato-bangalore-restaurants
make import                      # parses, matches, de-duplicates, runs NLP, ranks; prints the import report

# 3. run
make build && make backend       # UI + API on http://localhost:8000   (API docs: /docs)
#   or dev mode: `make backend` and `make frontend` (UI on :5173, proxies /api)
```

Admin actions are also available over HTTP (header `X-Admin-Token`): `POST /api/admin/import-dataset`, `/refresh-restaurants`, `/recompute`, `GET /api/admin/runs`.
Optional: `GOOGLE_PLACES_API_KEY` (live reviews, closure checks) and `ENABLE_SCHEDULER=true` (periodic discovery).

## Sentiment engines: VADER baseline and BERT (optional)

FoodSpotter ships two sentiment engines and always labels which one produced a number:

* **VADER baseline** (+ a small restaurant word list) – always available, the default.
* **BERT** – `nlptown/bert-base-multilingual-uncased-sentiment` (1–5 star probabilities, mapped by FoodSpotter to negative 1–2★ / neutral 3★ / positive 4–5★; confidence = probability of the winning class). It was fine-tuned on *product* reviews, so its accuracy on restaurant text is **unmeasured** until you evaluate it on labelled data. Aspect findings stay rule-based.

```bash
pip install -r backend/requirements-bert.txt     # transformers + PyTorch (large; CPU is fine)
python scripts/run_bert.py                       # downloads the model once, scores matched reviews (resumable)
```
`SENTIMENT_ENGINE=auto` (default) switches the whole app to BERT only when it has scored ≥95% of matched reviews; engines are never mixed in one chart. Force with `SENTIMENT_ENGINE=bert|vader`. `ENABLE_BERT=true` also runs BERT after each refresh; pin `BERT_MODEL_REVISION` for reproducible results. `evaluate_models.py run` compares stored BERT labels with the VADER baseline (star-rating proxy and your manual labels) and labels both honestly.

## Frontend pages

Overview (`/`), Explore Map, Hidden Gems, Sentiment Insights, Popular, Newly Discovered, Compare, Methodology & Data, and a restaurant detail page. Search + filters (cuisine, area, price, rating, dominant sentiment, aspect, minimum reviews) live in the URL and drive the map layers, charts, KPIs and rankings together. Everything shown is computed from the database via `/api/insights`, `/api/analytics/pipeline` and `/api/analytics/sentiment-engine`; nothing is placeholder data, and an empty database shows an instruction screen instead of numbers.

## Tests and evaluation

```bash
make test                        # pytest (backend) + vitest (frontend)
python scripts/evaluate_models.py export-templates   # annotation sheets -> docs/annotation/
python scripts/evaluate_models.py run                # metrics -> docs/evaluation_results.json (+ Methodology page)
```
Tests use an isolated temp DB with clearly fictional "Fixture …" data. The evaluator reports metrics only where ground truth exists: a star-rating *proxy* check is always labelled as such; accuracy/P/R/F1/confusion matrix, aspect P/R, ranking-vs-rating-baseline (Spearman, nDCG@10) and match precision require **your manual annotations**.

## Architecture

```
frontend/  React + TS + Tailwind, React-Router, Recharts, React-Leaflet (+markercluster, heat)
backend/   FastAPI · SQLAlchemy (SQLite, Postgres-portable) · api/ services/ nlp/ integrations/ models/
scripts/   discover_restaurants.py · import_reviews.py · evaluate_models.py
docs/      DATA_SOURCES.md, evaluation output, annotation sheets
```

* **NLP** – cleaning → tokenise → stop-words (negations kept) → lemmatise (WordNet if installed, rule-based fallback); VADER baseline + transparent domain-lexicon extension; rule-based clause-level aspect analysis (food, service, ambience, affordability, hygiene, waiting time); aspect scores shown only with ≥5 mentions; summaries generated strictly from aggregates.
* **Popularity** – weighted mean of Bayesian-shrunk rating, log vote volume, small-sample-shrunk positive share, and recency (only when dated reviews exist); weights in `config.py`/env, renormalised over available components; per-restaurant explanation shown in the UI.
* **Hidden gems** – ≥8 analysed reviews, Wilson lower bound of positive share ≥0.55, adjusted rating ≥3.8, below the 50th visibility percentile; otherwise a stated reason.
* **Heatmap** – three separate metrics (density / review coverage / popularity), each described so density is never read as popularity.

## Known limitations
* The Kaggle data is a historical snapshot with no review dates or coordinates: "trending" is never shown, recency is unused, and only restaurants matched to OSM records (name + area + address) carry reviews. Coverage will be partial.
* Aspect extraction is keyword/rule based (precision over recall); no transformer comparison is implemented yet.
* OSM cuisine/address tags are sparse; Overpass can rate-limit (handled with cache, back-off, mirrors).
* Google review content is never stored (provider terms) and never ranked.
* Single-process, no user accounts; admin is a shared token.
