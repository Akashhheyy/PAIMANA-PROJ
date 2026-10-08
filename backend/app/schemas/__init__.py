"""Pydantic response/request models for the API.

Phase 7.1: root + health shapes.
Phase 7.2: project, prediction, risk and early-warning shapes.
"""

from __future__ import annotations

from pydantic import BaseModel

from .predictions import PredictionResponse, PredictRequest
from .projects import ProjectDetail, ProjectListResponse, ProjectSummary
from .risk import ProjectRiskResponse, RiskSummaryResponse
from .warnings import EarlyWarningItem, EarlyWarningListResponse

__all__ = [
    "RootResponse",
    "HealthResponse",
    "ProjectSummary",
    "ProjectListResponse",
    "ProjectDetail",
    "PredictRequest",
    "PredictionResponse",
    "RiskSummaryResponse",
    "ProjectRiskResponse",
    "EarlyWarningItem",
    "EarlyWarningListResponse",
]


class RootResponse(BaseModel):
    """Response model for GET / (API information)."""

    service: str
    version: str
    environment: str
    description: str
    endpoints: list[str]
    phase: str


class HealthResponse(BaseModel):
    """Response model for GET /health."""

    status: str
    service: str
    version: str
