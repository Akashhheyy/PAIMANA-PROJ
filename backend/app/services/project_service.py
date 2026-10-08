"""Project service - reads the EXISTING generated project data.

* Primary record source: data/processed/paimana_features.csv (Phase 3),
  loaded ONCE (lru_cache); risk_category joined from the Phase-5 output.
* Lookup by project_code (the existing unique identifier).
* Read-only: the CSV is never modified, and pagination/search happens
  in pandas over the single in-memory frame (not per-request disk loads).
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from ..config import get_settings
from . import risk_service


class ProjectServiceError(RuntimeError):
    """Raised when the project dataset cannot be read (clean message)."""


@lru_cache(maxsize=1)
def projects_frame() -> pd.DataFrame:
    """paimana_features.csv loaded once, with risk_category attached."""
    path = get_settings().features_csv
    if not path.exists():
        raise ProjectServiceError("project dataset is unavailable")
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise ProjectServiceError("project dataset could not be read") from exc
    # attach existing Phase-5 category (no recomputation)
    risk = risk_service.risk_frame()[["project_code", "risk_category"]]
    df = df.merge(risk, on="project_code", how="left")
    return df


def _summary(row: pd.Series) -> dict:
    return {
        "project_code": int(row["project_code"]),
        "project_name": str(row["project_name"]),
        "state": str(row["state"]),
        "agency": str(row["agency"]),
        "report_month": str(row.get("report_month", "")),
        "risk_category": (None if pd.isna(row.get("risk_category"))
                          else str(row["risk_category"])),
    }


def _detail(row: pd.Series) -> dict:
    def s(col):
        v = row.get(col)
        return None if pd.isna(v) else str(v)

    def f(col):
        v = row.get(col)
        return None if pd.isna(v) else float(v)

    return {
        **_summary(row),
        "approval_date": s("approval_date"),
        "start_date": s("start_date"),
        "target_doc": s("target_doc"),
        "revised_doc": s("revised_doc"),
        "original_cost_crore": f("original_cost_crore"),
        "revised_cost_crore": f("revised_cost_crore"),
        "cumulative_expenditure_crore": f("cumulative_expenditure_crore"),
        "physical_progress_pct": f("physical_progress_pct"),
        "planned_horizon_months": f("planned_horizon_months"),
    }


def list_projects(page: int, page_size: int, search: str | None
                  ) -> tuple[list[dict], int]:
    """Paginated project list; `search` matches name/state/agency/code."""
    df = projects_frame()
    if search:
        needle = search.lower().strip()
        mask = (
            df["project_name"].str.lower().str.contains(needle, na=False)
            | df["state"].str.lower().str.contains(needle, na=False)
            | df["agency"].str.lower().str.contains(needle, na=False)
            | df["project_code"].astype(str).str.contains(needle, na=False)
        )
        df = df[mask]
    total = int(len(df))
    start = (page - 1) * page_size
    page_rows = df.iloc[start:start + page_size]
    return [_summary(r) for _, r in page_rows.iterrows()], total


def get_project(project_code: str) -> dict | None:
    """Detail for one project; None when the code is unknown/non-numeric."""
    try:
        code = int(str(project_code).strip())
    except (TypeError, ValueError):
        return None
    df = projects_frame()
    rows = df[df["project_code"] == code]
    if rows.empty:
        return None
    return _detail(rows.iloc[0])


def project_exists(project_code: str) -> bool:
    return get_project(project_code) is not None
