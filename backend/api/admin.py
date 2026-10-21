from __future__ import annotations

from pathlib import Path

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import require_admin, session_factory
from backend.config import get_settings
from backend.database.base import iso
from backend.database.db import get_db
from backend.integrations.google_places import GooglePlacesClient
from backend.integrations.overpass import OverpassClient
from backend.models import DiscoveryHistory, ImportHistory
from backend.schemas import ImportRequest, RefreshRequest
from backend.services.discovery import run_osm_discovery, start_run
from backend.services.google_verify import run_google_verification
from backend.services.importer import DatasetError, import_zomato_csv
from backend.services.neighborhoods import BY_KEY, NEIGHBORHOODS
from backend.nlp.bert import availability
from backend.services.pipeline import refresh_analytics, run_bert
from backend.services.ranking import recompute_rankings
from backend.services.sentiment_view import JOB

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/import-dataset", summary="Import the historical Zomato Bangalore CSV from the server's data/ directory")
def import_dataset(body: ImportRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    if Path(body.filename).name != body.filename or not body.filename.lower().endswith(".csv"):
        raise HTTPException(400, "filename must be a plain .csv file name located in the server's data/ directory")
    path = Path(settings.data_dir) / body.filename
    if not path.is_file():
        raise HTTPException(404, f"{body.filename} not found in data/. Download the Kaggle CSV and place it there.")
    try:
        hist = import_zomato_csv(db, path, max_reviews=body.max_reviews, store_unresolved=body.store_unresolved)
    except DatasetError as e:
        raise HTTPException(422, str(e)) from e
    analytics = refresh_analytics(db)
    return {"import_id": hist.id, "status": hist.status, "report": hist.report, "analytics": analytics}


def _discovery_job(factory, run_id: int, req: RefreshRequest, osm_factory, google_factory) -> None:
    db = factory()
    try:
        run = db.get(DiscoveryHistory, run_id)
        try:
            if req.source == "osm":
                hoods = [BY_KEY[k] for k in req.neighborhoods] if req.neighborhoods else None
                run_osm_discovery(db, run, client=osm_factory(), neighborhoods=hoods, use_cache=req.use_cache)
            else:
                run_google_verification(db, run, google_factory(), limit=req.google_limit)
        except Exception as e:  # never leave a run stuck in "running"
            from backend.database.base import utcnow

            db.rollback()
            run = db.get(DiscoveryHistory, run_id)
            run.status, run.finished_at, run.errors = "failed", utcnow(), [f"Unexpected error: {type(e).__name__}: {e}"]
            db.commit()
        refresh_analytics(db)
    finally:
        db.close()


@router.post("/refresh-restaurants", status_code=202, summary="Start a restaurant discovery refresh (runs in the background)")
def refresh_restaurants(body: RefreshRequest, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    settings = get_settings()
    if body.neighborhoods:
        bad = [k for k in body.neighborhoods if k not in BY_KEY]
        if bad:
            raise HTTPException(422, f"Unknown neighbourhood key(s): {bad}. Valid: {[n.key for n in NEIGHBORHOODS]}")
    if body.source == "google" and not settings.google_places_api_key:
        raise HTTPException(400, "Google Places is not configured (GOOGLE_PLACES_API_KEY). OpenStreetMap discovery remains available.")
    if db.scalar(select(DiscoveryHistory.id).where(DiscoveryHistory.status == "running").limit(1)):
        raise HTTPException(409, "A refresh is already running.")
    run = start_run(db, body.source, body.neighborhoods or [n.key for n in NEIGHBORHOODS])
    osm_factory = getattr(request.app.state, "overpass_factory", OverpassClient)
    google_factory = getattr(request.app.state, "google_factory", lambda: GooglePlacesClient(settings.google_places_api_key, min_interval=settings.google_min_interval_seconds))
    background.add_task(_discovery_job, session_factory(request), run.id, body, osm_factory, google_factory)
    return {"run_id": run.id, "status": "running", "is_baseline": run.is_baseline,
            "message": "Refresh started. Poll /api/restaurants/newly-discovered for status."}


@router.post("/recompute", summary="Re-run NLP (optionally from scratch) and recompute rankings")
def recompute(force_nlp: bool = False, db: Session = Depends(get_db)):
    return refresh_analytics(db, force_nlp=force_nlp)


@router.get("/runs", summary="Recent discovery and import runs")
def runs(db: Session = Depends(get_db)):
    d = db.scalars(select(DiscoveryHistory).order_by(DiscoveryHistory.id.desc()).limit(20)).all()
    i = db.scalars(select(ImportHistory).order_by(ImportHistory.id.desc()).limit(20)).all()
    return {
        "discovery": [{"id": x.id, "source": x.source, "status": x.status, "baseline": x.is_baseline, "found": x.found_count, "new": x.new_count,
                       "flagged": x.flagged_count, "errors": x.errors, "started_at": iso(x.started_at), "finished_at": iso(x.finished_at)} for x in d],
        "imports": [{"id": x.id, "filename": x.filename, "status": x.status, "started_at": iso(x.started_at), "finished_at": iso(x.finished_at), "report": x.report} for x in i],
    }


def _bert_job(factory, force: bool, limit: Optional[int], model_factory) -> None:
    db = factory()
    try:
        JOB["running"] = True
        try:
            res = run_bert(db, model=model_factory(), force=force, limit=limit)
            recompute_rankings(db)  # rankings follow the active engine
        except Exception as e:  # never leave the job flagged as running
            res = {"status": "failed", "reason": f"{type(e).__name__}: {e}", "reviews_analysed": 0}
        JOB["last"] = res
    finally:
        JOB["running"] = False
        db.close()


@router.post("/run-bert", status_code=202, summary="Run the BERT sentiment model over matched reviews (background)")
def run_bert_endpoint(request: Request, background: BackgroundTasks, force: bool = False, limit: Optional[int] = Query(None, ge=1, le=1_000_000)):
    avail = availability()
    model_factory = getattr(request.app.state, "bert_factory", None)
    if model_factory is None:
        if not avail["packages_installed"]:
            raise HTTPException(400, avail["reason"])
        from backend.nlp.bert import BertSentimentModel

        model_factory = BertSentimentModel
    if JOB["running"]:
        raise HTTPException(409, "A BERT run is already in progress.")
    JOB["running"] = True
    background.add_task(_bert_job, session_factory(request), force, limit, model_factory)
    return {"status": "running", "message": "BERT run started. Poll /api/analytics/sentiment-engine for progress (coverage) and the result."}
