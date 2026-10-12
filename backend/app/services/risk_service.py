"""Risk service - serves the EXISTING Phase-5/6 outputs from SQLite.

- Counts and rows come from the persisted risk_results/early_warnings tables
  (identical semantics to the Phase-5/6 CSV artifacts).
- Warning-type names and thresholds come from the ML modules (ml/06/ml/07
  via model_service), so API counts can never drift from the ML layer.
- Query failures are wrapped in RiskServiceError -> clean 500 responses.
"""

from __future__ import annotations

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from ..db.models import EarlyWarning, Project, RiskResult
from .model_service import rs06, rs07


class RiskServiceError(RuntimeError):
    """Raised when risk/warning data cannot be read (clean message)."""


VALID_RISK_CATEGORIES = {"Low", "Medium", "High", "Unknown"}
VALID_WARNING_TYPES = set(rs07.WARNING_ORDER)

_WARNING_RISK_JOIN = and_(
    EarlyWarning.project_code == RiskResult.project_code,
    EarlyWarning.report_month == RiskResult.report_month)
_WARNING_PROJECT_JOIN = and_(
    EarlyWarning.project_code == Project.project_code,
    EarlyWarning.report_month == Project.report_month)


def summary(db: Session) -> dict:
    """GET /api/risk/summary - counts from the persisted artifacts."""
    try:
        cat_rows = db.execute(
            select(RiskResult.risk_category, func.count())
            .group_by(RiskResult.risk_category)).all()
        cat = {name: int(n) for name, n in cat_rows}
        partial = int(db.scalar(
            select(func.count()).select_from(RiskResult)
            .where(RiskResult.score_status == "partial")) or 0)
        token_row = db.execute(select(*[
            func.coalesce(func.sum(case(
                (EarlyWarning.warning_type.like(f"%{token}%"), 1), else_=0)),
                0)
            for token in (rs07.COST_WARNING, rs07.TIME_WARNING,
                          rs07.COMBINED_HIGH_RISK_WARNING)])).one()
        total = int(db.scalar(
            select(func.count()).select_from(RiskResult)) or 0)
        return {
            "total_projects": total,
            "high_risk_count": cat.get("High", 0),
            "medium_risk_count": cat.get("Medium", 0),
            "low_risk_count": cat.get("Low", 0),
            "partial_incomplete_count": partial,
            "cost_warning_count": int(token_row[0]),
            "time_warning_count": int(token_row[1]),
            "combined_high_risk_warning_count": int(token_row[2]),
        }
    except Exception:
        raise RiskServiceError("risk data could not be read") from None


def _row(project: Project, risk: RiskResult, warn: EarlyWarning) -> dict:
    return {
        "project_code": int(project.project_code),
        "project_name": str(project.project_name),
        "state": str(project.state),
        "agency": str(project.agency),
        "report_month": str(project.report_month),
        "cost_overrun_probability": float(risk.cost_overrun_probability),
        # NULL (never 0) for the 354 unknown-time-label projects:
        "time_overrun_probability": (None if risk.time_overrun_probability
                                     is None
                                     else float(risk.time_overrun_probability)),
        "combined_risk_score": (None if risk.combined_risk_score is None
                                else float(risk.combined_risk_score)),
        "risk_category": str(risk.risk_category),
        "score_status": str(risk.score_status),
        "missing_component": str(risk.missing_component),
        "warning_type": str(warn.warning_type),
        "warning_priority": str(warn.warning_priority),
        "warning_priority_label": str(warn.warning_priority_label),
        "warning_message": str(warn.warning_message),
        "risk_indicators": str(warn.risk_indicators),
        "recommended_action": str(warn.recommended_action),
    }


def get_project_risk(db: Session, project_code: int) -> dict | None:
    """GET /api/projects/{code}/risk - persisted Phase-5 + Phase-6 data."""
    try:
        project = db.scalar(select(Project).where(
            Project.project_code == project_code))
        risk = db.scalar(select(RiskResult).where(
            RiskResult.project_code == project_code))
        warn = db.scalar(select(EarlyWarning).where(
            EarlyWarning.project_code == project_code))
        if project is None or risk is None or warn is None:
            return None
        return _row(project, risk, warn)
    except Exception:
        raise RiskServiceError("risk data could not be read") from None


def list_warnings(db: Session, risk_category: str | None,
                  warning_type: str | None, page: int,
                  page_size: int) -> tuple[list[dict], int]:
    """GET /api/early-warnings with filters + pagination (SQL)."""
    try:
        query = (select(EarlyWarning, RiskResult, Project)
                 .join(RiskResult, _WARNING_RISK_JOIN)
                 .join(Project, _WARNING_PROJECT_JOIN))
        count_query = (select(func.count()).select_from(EarlyWarning)
                       .join(RiskResult, _WARNING_RISK_JOIN)
                       .join(Project, _WARNING_PROJECT_JOIN))
        if risk_category:
            cond = RiskResult.risk_category == risk_category
            query = query.where(cond)
            count_query = count_query.where(cond)
        if warning_type:
            cond = EarlyWarning.warning_type.like(f"%{warning_type}%")
            query = query.where(cond)
            count_query = count_query.where(cond)
        total = int(db.scalar(count_query) or 0)
        rows = db.execute(
            query.order_by(EarlyWarning.id)   # import order preserved
            .offset((page - 1) * page_size).limit(page_size)).all()
        return [_row(p, r, w) for w, r, p in rows], total
    except Exception:
        raise RiskServiceError("early-warning data could not be read") from None


def check_threshold_consistency() -> bool:
    """Guard: Phase-5 thresholds unchanged (0.35 / 0.65)."""
    return (rs06.LOW_MAX, rs06.HIGH_MIN) == (0.35, 0.65)

