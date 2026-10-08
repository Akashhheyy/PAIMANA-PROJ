"""Prediction route: POST /api/predict using the existing trained models."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..schemas import PredictionResponse, PredictRequest
from ..services import model_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=PredictionResponse)
def predict(request: PredictRequest):
    """Cost/time overrun probabilities from the Phase-4 plan-only models.

    Validation (422) happens in the schema: required fields are mandatory,
    costs must be > 0, months 1-12 - nothing is silently defaulted.
    Model failures return a clean 500/503 without stack traces."""
    features = {
        "original_cost_crore": request.original_cost_crore,
        "log1p_original_cost": (
            request.log1p_original_cost
            if request.log1p_original_cost is not None
            else model_service.derive_log1p_cost(request.original_cost_crore)),
        "approval_year": float(request.approval_year),
        "approval_month": float(request.approval_month),
        "planned_horizon_months": request.planned_horizon_months,
        "agency": request.agency,
        "state": request.state,
    }
    try:
        result = model_service.predict_plan_only(features)
    except model_service.ModelServiceError as exc:
        logger.error("model service error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Model service is unavailable: trained models could not "
                   "be loaded.")
    except ValueError as exc:               # schema mismatch inside pipeline
        logger.warning("prediction input rejected: %s", exc)
        raise HTTPException(
            status_code=422,
            detail="Request does not match the required model feature schema.")
    except HTTPException:
        raise
    except Exception as exc:                # unexpected -> clean 500
        logger.exception("unexpected prediction failure: %s", exc)
        raise HTTPException(
            status_code=500, detail="Prediction failed due to an internal "
                                    "model error.")
    return PredictionResponse(**result)
