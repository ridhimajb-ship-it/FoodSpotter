from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.services.filters import Filters, filter_params
from backend.services.insights import build_insights, pipeline_summary
from backend.services.sentiment_view import engine_info

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/insights", summary="All overview statistics and chart data for the filtered scope")
def insights(f: Filters = Depends(filter_params), db: Session = Depends(get_db)):
    return build_insights(db, f)


@router.get("/analytics/pipeline", summary="Whole-database WSMA pipeline counts: import, matching, coverage, engine")
def pipeline(db: Session = Depends(get_db)):
    return pipeline_summary(db)


@router.get("/analytics/sentiment-engine", summary="Which sentiment model is active, BERT coverage and model card")
def sentiment_engine(db: Session = Depends(get_db)):
    return engine_info(db)
