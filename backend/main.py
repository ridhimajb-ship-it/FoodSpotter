"""FoodSpotter API – FastAPI application entry point.

Run:  uvicorn backend.main:app --reload
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import admin, analytics, insights, meta, restaurants
from backend.config import ROOT, get_settings
from backend.database.db import SessionLocal, init_db

log = logging.getLogger("foodspotter")
DIST = ROOT / "frontend" / "dist"


def _scheduled_refresh() -> None:  # pragma: no cover - exercised only with ENABLE_SCHEDULER=true
    from backend.integrations.overpass import OverpassClient
    from backend.services.discovery import run_osm_discovery, start_run
    from backend.services.neighborhoods import NEIGHBORHOODS
    from backend.services.pipeline import refresh_analytics

    db = SessionLocal()
    try:
        run = start_run(db, "osm", [n.key for n in NEIGHBORHOODS])
        run_osm_discovery(db, run, OverpassClient())
        refresh_analytics(db)
    except Exception:
        log.exception("Scheduled discovery failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    s = get_settings()
    scheduler = None
    if s.enable_scheduler:  # pragma: no cover
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()
        scheduler.add_job(_scheduled_refresh, "interval", hours=s.discovery_interval_hours, id="osm-discovery", max_instances=1, coalesce=True)
        scheduler.start()
        log.info("Discovery scheduler started (every %s h)", s.discovery_interval_hours)
    yield
    if scheduler:  # pragma: no cover
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="FoodSpotter API",
    version="0.1.0",
    description=(
        "Geospatial restaurant discovery with review sentiment, aspect analysis and confidence-aware ranking.\n\n"
        "Restaurant locations © OpenStreetMap contributors. Historical reviews come from the Kaggle Zomato Bangalore "
        "dataset (a past snapshot). Admin endpoints need the `X-Admin-Token` header."
    ),
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list, allow_methods=["GET", "POST"], allow_headers=["*"])
app.state.session_factory = SessionLocal

for r in (meta.router, restaurants.router, analytics.router, insights.router, admin.router):
    app.include_router(r)

# Serve the built frontend (single-process deployment). In development use `npm run dev` instead.
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = (DIST / path).resolve()
        if path and DIST.resolve() in f.parents and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
