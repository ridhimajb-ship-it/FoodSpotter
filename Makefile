.PHONY: bert setup backend frontend build test discover import evaluate
setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements.txt && cd frontend && npm install
backend:
	. .venv/bin/activate && uvicorn backend.main:app --reload --port 8000
frontend:
	cd frontend && npm run dev
build:
	cd frontend && npm run build        # then `make backend` serves UI + API on :8000
test:
	. .venv/bin/activate && python -m pytest -q && cd frontend && npx vitest run
discover:
	. .venv/bin/activate && python scripts/discover_restaurants.py
import:
	. .venv/bin/activate && python scripts/import_reviews.py data/zomato.csv
evaluate:
	. .venv/bin/activate && python scripts/evaluate_models.py run

bert:
	. .venv/bin/activate && pip install -r backend/requirements-bert.txt && python scripts/run_bert.py
