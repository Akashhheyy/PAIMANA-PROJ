"""Project service - SQLite-backed (Phase 8), same response contracts.

- Reads projects (and their Phase-5 risk category) from the database with
  SQL pagination/search - never loads the whole dataset per request.
- `progress_distribution` aggregates with SQL (bins 0..100 inclusive of
  exactly 100%); an optional `frame` argument is retained purely as a
  unit-test hook for synthetic boundary data.
- Query failures are wrapped in ProjectServiceError so routes can return a
  clean 500 without exposing SQL, paths or stack traces.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import String, and_, cast, case, func, or_, select
from sqlalchemy.orm import Session

from ..db.models import Project, RiskResult


class ProjectServiceError(RuntimeError):
    """Raised when project data cannot be read (clean message)."""


# ---------------------------------------------------------------------------
# Progress binning constants (Phase 7.4 contract: [0,10], (10,20], ... (90,100])
# ---------------------------------------------------------------------------
PROGRESS_BIN_EDGES = list(range(0, 101, 10))
PROGRESS_BIN_LABELS = [f"{PROGRESS_BIN_EDGES[i]}-{PROGRESS_BIN_EDGES[i + 1]}"
                       for i in range(len(PROGRESS_BIN_EDGES) - 1)]
SNAPSHOT_LABEL = "April 2026"


def _iso(value) -> str | None:
    return None if value is None else value.isoformat()


def _summary(p: Project, risk_category: str | None) -> dict:
    return {
        "project_code": int(p.project_code),
        "project_name": str(p.project_name),
        "state": str(p.state),
        "agency": str(p.agency),
        "report_month": str(p.report_month),
        "risk_category": (None if risk_category is None
                          else str(risk_category)),
    }


def _detail(p: Project) -> dict:
    return {
        "project_code": int(p.project_code),
        "project_name": str(p.project_name),
        "state": str(p.state),
        "agency": str(p.agency),
        "report_month": str(p.report_month),
        "approval_date": _iso(p.approval_date),
        "start_date": _iso(p.start_date),
        "target_doc": _iso(p.target_doc),
        "revised_doc": _iso(p.revised_doc),
        "original_cost_crore": p.original_cost_crore,
        "revised_cost_crore": p.revised_cost_crore,
        "cumulative_expenditure_crore": p.cumulative_expenditure_crore,
        "physical_progress_pct": p.physical_progress_pct,
        "planned_horizon_months": None,   # filled by caller when computable
    }


def list_projects(db: Session, page: int, page_size: int,
                  search: str | None) -> tuple[list[dict], int]:
    """Paginated list; search matches name/state/agency/code (LIKE)."""
    try:
        query = select(Project, RiskResult.risk_category).outerjoin(
            RiskResult,
            and_(RiskResult.project_code == Project.project_code,
                 RiskResult.report_month == Project.report_month))
        count_query = select(func.count()).select_from(Project)
        if search:
            like = f"%{search.strip()}%"
            cond = or_(
                Project.project_name.ilike(like),
                Project.state.ilike(like),
                Project.agency.ilike(like),
                cast(Project.project_code, String).ilike(like))
            query = query.where(cond)
            count_query = count_query.where(cond)
        total = int(db.scalar(count_query) or 0)
        rows = db.execute(
            query.order_by(Project.id)          # CSV import order preserved
            .offset((page - 1) * page_size).limit(page_size)).all()
        return [_summary(p, rc) for p, rc in rows], total
    except Exception:
        raise ProjectServiceError("project data could not be read") from None


def get_project(db: Session, project_code: str) -> dict | None:
    """Detail for one project; None when the code is unknown/non-numeric."""
    try:
        code = int(str(project_code).strip())
    except (TypeError, ValueError):
        return None
    try:
        p = db.scalar(select(Project).where(Project.project_code == code))
        if p is None:
            return None
        detail = _detail(p)
        # planned_horizon_months kept identical to the pre-DB contract:
        if p.start_date and p.target_doc:
            detail["planned_horizon_months"] = float(
                (p.target_doc.year * 12 + p.target_doc.month)
                - (p.start_date.year * 12 + p.start_date.month))
        return detail
    except Exception:
        raise ProjectServiceError("project data could not be read") from None


def _bins_from_pandas(included: pd.Series) -> list[dict]:
    counts = (pd.cut(included, bins=PROGRESS_BIN_EDGES, right=True,
                     include_lowest=True, labels=PROGRESS_BIN_LABELS)
              .value_counts().reindex(PROGRESS_BIN_LABELS, fill_value=0))
    return [{"label": lab, "count": int(counts[lab])}
            for lab in PROGRESS_BIN_LABELS]


def progress_distribution(db: Session | None = None,
                          agency: str | None = None,
                          state: str | None = None,
                          frame: pd.DataFrame | None = None) -> dict:
    """Physical-progress histogram for the dashboard (Graph 1).

    Bins: [0,10], (10,20], ..., (90,100] - the last bin INCLUDES exactly
    100% (verified pitfall: 97 projects at 100.0). Missing progress is
    excluded from the bins and counted, never zero-filled. `frame` is a
    unit-test hook (synthetic boundary data); production uses SQL only.
    """
    if frame is not None:                      # pure-pandas test path
        total = int(len(frame))
        raw = (frame["physical_progress_pct"]
               if "physical_progress_pct" in frame.columns
               else pd.Series(np.nan, index=frame.index))
        progress = pd.to_numeric(raw, errors="coerce")
        included = progress[progress.notna()]
        missing = total - int(len(included))
        bins = _bins_from_pandas(included)
        mean = (round(float(included.mean()), 2) if len(included) else None)
        median = (round(float(included.median()), 2) if len(included) else None)
    else:
        if db is None:
            raise ProjectServiceError("database session is required")
        try:
            p = Project.physical_progress_pct
            conds = []
            if agency:
                conds.append(Project.agency == agency.strip())
            if state:
                conds.append(Project.state == state.strip())
            bin_conds = []
            for i, (lo, hi) in enumerate(zip(PROGRESS_BIN_EDGES[:-1],
                                             PROGRESS_BIN_EDGES[1:])):
                bin_conds.append((p >= lo if i == 0 else p > lo, p <= hi))
            row = db.execute(
                select(func.count(), func.count().filter(p.is_(None)),
                       *[func.count().filter(and_(*bc)) for bc in bin_conds],
                       func.avg(p)).select_from(Project).where(*conds)).one()
            total, missing, avg = int(row[0]), int(row[1]), row[-1]
            bin_counts = [int(c) for c in row[2:-1]]
            included = total - missing
            if sum(bin_counts) != included:
                raise ProjectServiceError(
                    "progress binning failed range validation")
            bins = [{"label": lab, "count": cnt}
                    for lab, cnt in zip(PROGRESS_BIN_LABELS, bin_counts)]
            mean = round(float(avg), 2) if avg is not None else None
            median = None
            if included:
                ordered = select(p).where(*conds, p.isnot(None)).order_by(p)
                n = included
                lo = int(db.scalar(ordered.offset((n - 1) // 2).limit(1)))
                hi = int(db.scalar(ordered.offset(n // 2).limit(1)))
                median = round((lo + hi) / 2, 2)
        except ProjectServiceError:
            raise
        except Exception:
            raise ProjectServiceError(
                "project progress could not be read") from None

    expected_included = (int(pd.to_numeric(
        frame["physical_progress_pct"], errors="coerce").notna().sum())
        if frame is not None else included)
    assert sum(b["count"] for b in bins) == expected_included, \
        "every eligible project must belong to exactly one bin"
    return {
        "snapshot_label": SNAPSHOT_LABEL,
        "total_projects": total,
        "projects_included": int(expected_included),
        "projects_missing_progress": missing,
        "bins": bins,
        "mean_progress": mean,
        "median_progress": median,
        "agency_filter": agency,
        "state_filter": state,
    }


def project_exists(db: Session, project_code: str) -> bool:
    return get_project(db, project_code) is not None

