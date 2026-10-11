"""Dashboard route: physical-progress distribution (Phase 7.4, Graph 1).

Aggregates the existing cached project dataframe only. No model inference,
no risk formula, no warning threshold is duplicated or changed.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..schemas import ProgressDistributionResponse
from ..services import project_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/progress-distribution", response_model=ProgressDistributionResponse)
def progress_distribution(
    agency: str | None = Query(
        None, min_length=1, max_length=200,
        description="optional exact-match agency filter"),
    state: str | None = Query(
        None, min_length=1, max_length=200,
        description="optional exact-match state filter"),
):
    """April-2026 physical-progress distribution (10 inclusive bins).

    Every eligible project lands in exactly one bin (bins cover 0%..100%
    including values of exactly 100%); projects with missing progress are
    excluded from the bins and reported in `projects_missing_progress`.
    An empty filtered result returns zeros/None safely (not an error)."""
    try:
        return project_service.progress_distribution(
            agency=agency, state=state)
    except project_service.ProjectServiceError as exc:
        logger.error("project dataset error: %s", exc)
        raise HTTPException(
            status_code=500, detail="Project data is currently unavailable.")
