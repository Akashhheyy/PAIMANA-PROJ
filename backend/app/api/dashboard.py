"""Dashboard route: physical-progress distribution (Phase 7.4, Graph 1).

Aggregates the existing cached project dataframe only. No model inference,
no risk formula, no warning threshold is duplicated or changed.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..schemas import ProgressDistributionResponse
from ..services import project_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/progress-distribution",
            response_model=ProgressDistributionResponse)
def progress_distribution(
    agency: str | None = Query(
        None, min_length=1, max_length=200,
        description="optional exact-match agency filter"),
    state: str | None = Query(
        None, min_length=1, max_length=200,
        description="optional exact-match state filter"),
    db: Session = Depends(get_db),
):
    """April-2026 physical-progress distribution (10 inclusive bins).

    Served by SQL aggregation over the database; every eligible project
    lands in exactly one bin (0%..100% including exactly 100%), missing
    progress is excluded from bins and reported, never zero-filled."""
    try:
        return project_service.progress_distribution(
            db=db, agency=agency, state=state)
    except project_service.ProjectServiceError as exc:
        logger.error("project dataset error: %s", exc)
        raise HTTPException(
            status_code=500, detail="Project data is currently unavailable.")
