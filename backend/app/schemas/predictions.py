"""Schemas for POST /api/predict (Phase-4 plan-only schema)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Exactly the Phase-4 plan-only feature schema (from model metadata).

    All model-required fields are mandatory: missing/invalid values produce
    a 422 validation error - nothing is silently filled with defaults.
    `log1p_original_cost` may be omitted and is then derived with the exact
    Phase-3 formula np.log1p(original_cost_crore)."""

    original_cost_crore: float = Field(..., gt=0,
        description="Sanctioned cost at approval (crore INR) - must be > 0")
    log1p_original_cost: float | None = Field(None,
        description="Optional; derived from original_cost_crore when omitted")
    approval_year: int = Field(..., ge=1900, le=2100)
    approval_month: int = Field(..., ge=1, le=12)
    planned_horizon_months: float = Field(..., ge=-1200, le=2400,
        description="Planned months from sanction to target completion")
    agency: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)


class PredictionResponse(BaseModel):
    cost_overrun_probability: float = Field(..., ge=0, le=1)
    time_overrun_probability: float = Field(..., ge=0, le=1)
    cost_probability_available: bool
    time_probability_available: bool
    combined_risk_score: float | None = Field(None, ge=0, le=1)
    score_status: str
    missing_component: str
    risk_category: str | None = None
