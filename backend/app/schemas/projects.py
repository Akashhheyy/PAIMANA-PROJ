"""Schemas for project list/detail responses."""

from __future__ import annotations

from pydantic import BaseModel


class ProjectSummary(BaseModel):
    project_code: int
    project_name: str
    state: str
    agency: str
    report_month: str
    risk_category: str | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]
    page: int
    page_size: int
    total: int


class ProjectDetail(BaseModel):
    project_code: int
    project_name: str
    state: str
    agency: str
    report_month: str
    risk_category: str | None = None
    approval_date: str | None = None
    start_date: str | None = None
    target_doc: str | None = None
    revised_doc: str | None = None
    original_cost_crore: float | None = None
    revised_cost_crore: float | None = None
    cumulative_expenditure_crore: float | None = None
    physical_progress_pct: float | None = None
    planned_horizon_months: float | None = None
