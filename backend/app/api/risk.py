"""Risk route: GET /api/risk/summary from the existing Phase-5/6 outputs."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..schemas import RiskSummaryResponse
from ..services import risk_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary", response_model=RiskSummaryResponse)
def risk_summary(db: Session = Depends(get_db)):
    """Counts from the persisted artifacts (no new formulas)."""
    try:
        data = risk_service.summary(db)
    except risk_service.RiskServiceError as exc:
        logger.error("risk output error: %s", exc)
        raise HTTPException(
            status_code=500, detail="Risk data is currently unavailable.")
    return RiskSummaryResponse(**data)
