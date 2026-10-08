"""Schemas for early-warning list responses."""

from __future__ import annotations

from pydantic import BaseModel


class EarlyWarningItem(BaseModel):
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


class EarlyWarningListResponse(BaseModel):
    items: list[EarlyWarningItem]
    page: int
    page_size: int
    total: int
    risk_category: str | None = None
    warning_type: str | None = None
