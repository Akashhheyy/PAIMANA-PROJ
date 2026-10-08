"""Project routes: list (paginated/searchable), detail, and single risk."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..schemas import (ProjectDetail, ProjectListResponse, ProjectRiskResponse,
                       ProjectSummary)
from ..services import project_service, risk_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=ProjectListResponse)
def list_projects(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(20, ge=1, le=100, description="items per page"),
    search: str | None = Query(None, min_length=1, max_length=200,
                                description="match name/state/agency/code"),
):
    """Paginated project list from the existing generated project data."""
    try:
        items, total = project_service.list_projects(page, page_size, search)
    except project_service.ProjectServiceError as exc:
        logger.error("project dataset error: %s", exc)
        raise HTTPException(
            status_code=500, detail="Project data is currently unavailable.")
    return ProjectListResponse(items=items, page=page, page_size=page_size,
                               total=total)


@router.get("/{project_code}/risk", response_model=ProjectRiskResponse)
def project_risk(project_code: str):
    """Existing Phase-5 risk score + Phase-6 warning for one project."""
    try:
        data = risk_service.get_project_risk(_as_code(project_code))
    except risk_service.RiskServiceError as exc:
        logger.error("risk output error: %s", exc)
        raise HTTPException(
            status_code=500, detail="Risk data is currently unavailable.")
    if data is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectRiskResponse(**data)


@router.get("/{project_code}", response_model=ProjectDetail)
def project_detail(project_code: str):
    """Detail for one project (404 when the identifier is unknown)."""
    try:
        data = project_service.get_project(project_code)
    except project_service.ProjectServiceError as exc:
        logger.error("project dataset error: %s", exc)
        raise HTTPException(
            status_code=500, detail="Project data is currently unavailable.")
    if data is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectDetail(**data)


def _as_code(project_code: str) -> int:
    """Map an unknown/non-numeric code to -1 so lookups 404 cleanly."""
    try:
        return int(str(project_code).strip())
    except (TypeError, ValueError):
        return -1
