"""Early-warning route: GET /api/early-warnings (existing Phase-6 rows)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..schemas import EarlyWarningListResponse
from ..services import risk_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=EarlyWarningListResponse)
def list_early_warnings(
    risk_category: str | None = Query(
        None, description="Low | Medium | High | Unknown"),
    warning_type: str | None = Query(
        None, description="COST_WARNING | TIME_WARNING | "
                          "COMBINED_HIGH_RISK_WARNING | MEDIUM_RISK_WARNING | "
                          "DATA_COMPLETENESS_WARNING"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Existing early warnings with optional filters + pagination.
    No new warning rules are created here - rows are returned as generated
    by the Phase-6 engine."""
    if risk_category and risk_category not in risk_service.VALID_RISK_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid risk_category; use one of "
                   f"{sorted(risk_service.VALID_RISK_CATEGORIES)}")
    if warning_type and warning_type not in risk_service.VALID_WARNING_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid warning_type; use one of "
                   f"{sorted(risk_service.VALID_WARNING_TYPES)}")
    try:
        items, total = risk_service.list_warnings(
            risk_category, warning_type, page, page_size)
    except risk_service.RiskServiceError as exc:
        logger.error("early-warning output error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Early-warning data is currently unavailable.")
    return EarlyWarningListResponse(
        items=items, page=page, page_size=page_size, total=total,
        risk_category=risk_category, warning_type=warning_type)
