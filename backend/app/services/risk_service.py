"""Risk service - reads the EXISTING Phase-5 and Phase-6 outputs.

Rules honoured here:
* Reads project_risk_scores.csv (Phase 5) and early_warning_results.csv
  (Phase 6) - both loaded ONCE (lru_cache), never re-derived with new maths.
* Thresholds/warning-type names come from the ML modules (ml/06, ml/07),
  so API counts can never drift from the existing implementation.
* No file is ever written; nothing under outputs/risk/ is modified.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from ..config import get_settings
from .model_service import rs06, rs07


class RiskServiceError(RuntimeError):
    """Raised when existing risk/warning outputs cannot be read (clean msg)."""


@lru_cache(maxsize=1)
def risk_frame() -> pd.DataFrame:
    """Phase-5 project risk scores (1,981 rows), loaded once."""
    path = get_settings().risk_output_dir / "project_risk_scores.csv"
    if not path.exists():
        raise RiskServiceError("Phase-5 risk output is unavailable")
    try:
        return pd.read_csv(path)
    except Exception as exc:
        raise RiskServiceError("Phase-5 risk output could not be read") from exc


@lru_cache(maxsize=1)
def warnings_frame() -> pd.DataFrame:
    """Phase-6 early-warning results (Phase-5 columns + warning columns)."""
    path = get_settings().risk_output_dir / "early_warning_results.csv"
    if not path.exists():
        raise RiskServiceError("Phase-6 early-warning output is unavailable")
    try:
        return pd.read_csv(path)
    except Exception as exc:
        raise RiskServiceError(
            "Phase-6 early-warning output could not be read") from exc


def _count_warning(df: pd.DataFrame, warning_name: str) -> int:
    """Count rows carrying a warning type - same token logic as Phase 6
    (warning_type is a '|'-joined list of triggered types)."""
    return int(df["warning_type"].str.split("|").apply(
        lambda xs: warning_name in xs).sum())


def _none(value):
    """NaN/NaT -> None so responses stay valid JSON (354 partial rows)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if pd.isna(value):
        return None
    return value


def summary() -> dict:
    """GET /api/risk/summary - counts straight from the existing outputs."""
    risk = risk_frame()
    warns = warnings_frame()
    cat = risk["risk_category"].value_counts()   # Phase-5 categories, as-is
    return {
        "total_projects": int(len(risk)),
        "high_risk_count": int(cat.get("High", 0)),
        "medium_risk_count": int(cat.get("Medium", 0)),
        "low_risk_count": int(cat.get("Low", 0)),
        "partial_incomplete_count": int(
            (risk["score_status"] == "partial").sum()),
        "cost_warning_count": _count_warning(warns, rs07.COST_WARNING),
        "time_warning_count": _count_warning(warns, rs07.TIME_WARNING),
        "combined_high_risk_warning_count": _count_warning(
            warns, rs07.COMBINED_HIGH_RISK_WARNING),
    }


def _warning_row(row: pd.Series) -> dict:
    return {
        "project_code": int(row["project_code"]),
        "project_name": str(row["project_name"]),
        "state": str(row["state"]),
        "agency": str(row["agency"]),
        "report_month": _none(row.get("report_month")),
        "cost_overrun_probability": _none(row["cost_overrun_probability"]),
        "time_overrun_probability": _none(row["time_overrun_probability"]),
        "combined_risk_score": _none(row["combined_risk_score"]),
        "risk_category": str(row["risk_category"]),
        "score_status": str(row["score_status"]),
        "missing_component": str(row["missing_component"]),
        "warning_type": str(row["warning_type"]),
        "warning_priority": str(row["warning_priority"]),
        "warning_priority_label": str(row["warning_priority_label"]),
        "warning_message": str(row["warning_message"]),
        "risk_indicators": str(row["risk_indicators"]),
        "recommended_action": str(row["recommended_action"]),
    }


def get_project_risk(project_code: int) -> dict | None:
    """GET /api/projects/{code}/risk - Phase-5 risk + Phase-6 warning row."""
    df = warnings_frame()
    rows = df[df["project_code"] == project_code]
    if rows.empty:
        return None
    return _warning_row(rows.iloc[0])


def list_warnings(risk_category: str | None, warning_type: str | None,
                  page: int, page_size: int) -> tuple[list[dict], int]:
    """GET /api/early-warnings with filters + pagination."""
    df = warnings_frame()
    if risk_category:
        df = df[df["risk_category"] == risk_category]
    if warning_type:
        df = df[df["warning_type"].str.split("|").apply(
            lambda xs: warning_type in xs)]
    total = int(len(df))
    start = (page - 1) * page_size
    page_rows = df.iloc[start:start + page_size]
    return [_warning_row(r) for _, r in page_rows.iterrows()], total


VALID_RISK_CATEGORIES = {"Low", "Medium", "High", "Unknown"}
VALID_WARNING_TYPES = set(rs07.WARNING_ORDER)


def check_threshold_consistency() -> bool:
    """Guard: API-side thresholds are the Phase-5 values (0.35/0.65)."""
    return (rs06.LOW_MAX, rs06.HIGH_MIN) == (0.35, 0.65)
