"""Phase 8 ORM models: projects, risk results, early warnings, snapshots.

Schema notes:
* `projects.project_code` is the stable source identifier (unique, indexed).
* Risk results and warnings reference the project by `project_code` and are
  unique per (project_code, report_month) so future monthly snapshots cannot
  create duplicates for the same reporting period.
* `time_overrun_probability` is NULLable on purpose: 354 April-2026 rows
  have an unknown time label and MUST remain NULL, never zero.
* No infrastructure-sector column exists in the source, so none is stored
  (nothing is invented).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (Date, DateTime, Float, ForeignKey, Integer, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Project(Base):
    """One row per project per reporting snapshot (CSV row order kept)."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[int] = mapped_column(Integer, unique=True, nullable=False,
                                              index=True)
    project_name: Mapped[str] = mapped_column(String, nullable=False)
    agency: Mapped[str] = mapped_column(String, nullable=False, index=True)
    state: Mapped[str] = mapped_column(String, nullable=False, index=True)
    report_month: Mapped[str] = mapped_column(String, nullable=False, index=True)
    approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_doc: Mapped[date | None] = mapped_column(Date, nullable=True)
    revised_doc: Mapped[date | None] = mapped_column(Date, nullable=True)
    original_cost_crore: Mapped[float | None] = mapped_column(Float, nullable=True)
    revised_cost_crore: Mapped[float | None] = mapped_column(Float, nullable=True)
    cumulative_expenditure_crore: Mapped[float | None] = mapped_column(Float,
                                                                       nullable=True)
    physical_progress_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class RiskResult(Base):
    """Existing Phase-5 model output persisted per project+snapshot."""

    __tablename__ = "risk_results"
    __table_args__ = (
        UniqueConstraint("project_code", "report_month",
                         name="uq_risk_project_snapshot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.project_code"), nullable=False, index=True)
    report_month: Mapped[str] = mapped_column(String, nullable=False, index=True)
    cost_overrun_probability: Mapped[float] = mapped_column(Float, nullable=False)
    # NULL (not 0) when the time label was unknown - Phase-5 partial score:
    time_overrun_probability: Mapped[float | None] = mapped_column(Float,
                                                                   nullable=True)
    combined_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    score_status: Mapped[str] = mapped_column(String, nullable=False)
    missing_component: Mapped[str] = mapped_column(String, nullable=False)
    scoring_formula_version: Mapped[str | None] = mapped_column(String, nullable=True)


class EarlyWarning(Base):
    """Existing Phase-6 warning output per project+snapshot.

    Project identity fields are NOT duplicated here - they are read from
    `projects`; probabilities/scores are read from `risk_results`."""

    __tablename__ = "early_warnings"
    __table_args__ = (
        UniqueConstraint("project_code", "report_month",
                         name="uq_warning_project_snapshot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_code: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.project_code"), nullable=False, index=True)
    report_month: Mapped[str] = mapped_column(String, nullable=False, index=True)
    warning_type: Mapped[str] = mapped_column(String, nullable=False)
    warning_priority: Mapped[str] = mapped_column(String, nullable=False, index=True)
    warning_priority_label: Mapped[str] = mapped_column(String, nullable=False)
    warning_message: Mapped[str] = mapped_column(Text, nullable=False)
    risk_indicators: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_method: Mapped[str | None] = mapped_column(String, nullable=True)


class ImportSnapshot(Base):
    """Data-provenance record for each imported reporting snapshot."""

    __tablename__ = "import_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    source_dataset: Mapped[str] = mapped_column(String, nullable=False)
    reporting_month: Mapped[str] = mapped_column(String, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
