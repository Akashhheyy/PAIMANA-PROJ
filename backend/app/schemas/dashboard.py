"""Schemas for dashboard graph data (Phase 7.4 - Graph 1).

GET /api/dashboard/progress-distribution serves the April-2026 physical
progress distribution for the general dashboard. Read-only aggregation of
the existing project data - no model inference, no risk formulas.
"""

from __future__ import annotations

from pydantic import BaseModel


class ProgressBin(BaseModel):
    """One progress range bucket."""

    label: str          # e.g. "0-10", "90-100"
    count: int


class ProgressDistributionResponse(BaseModel):
    snapshot_label: str                 # "April 2026"
    total_projects: int                 # rows matching the filter
    projects_included: int              # rows with usable progress (binned)
    projects_missing_progress: int      # excluded from bins, never zero-filled
    bins: list[ProgressBin]             # 10 bins, [0,10] ... (90,100]
    mean_progress: float | None         # over included rows; None if empty
    median_progress: float | None
    agency_filter: str | None = None    # echo of applied filters
    state_filter: str | None = None
