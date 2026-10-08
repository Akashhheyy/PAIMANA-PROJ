"""Schemas for risk summary and single-project risk responses."""

from __future__ import annotations

from pydantic import BaseModel


class RiskSummaryResponse(BaseModel):
    total_projects: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    partial_incomplete_count: int
    cost_warning_count: int
    time_warning_count: int
    combined_high_risk_warning_count: int


class ProjectRiskResponse(BaseModel):
    project_code: int
    project_name: str
    state: str
    agency: str
    report_month: str | None = None
    cost_overrun_probability: float | None = None
    time_overrun_probability: float | None = None
    combined_risk_score: float | None = None
    risk_category: str
    score_status: str
    missing_component: str
    warning_type: str
    warning_priority: str
    warning_priority_label: str
    warning_message: str
    risk_indicators: str
    recommended_action: str
