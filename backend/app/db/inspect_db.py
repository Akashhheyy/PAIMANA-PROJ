"""Inspect imported database counts (read-only command).

Usage (from the project root):
    python -m backend.app.db.inspect_db
"""

from __future__ import annotations

from sqlalchemy import func, select

from .models import EarlyWarning, ImportSnapshot, Project, RiskResult
from .session import SessionLocal


def main() -> None:
    with SessionLocal() as db:
        projects = db.scalar(select(func.count()).select_from(Project)) or 0
        risks = db.scalar(select(func.count()).select_from(RiskResult)) or 0
        warnings = db.scalar(select(func.count()).select_from(EarlyWarning)) or 0
        snapshots = db.scalars(select(ImportSnapshot)).all()
        null_time = db.scalar(
            select(func.count()).select_from(RiskResult)
            .where(RiskResult.time_overrun_probability.is_(None))) or 0
        missing_progress = db.scalar(
            select(func.count()).select_from(Project)
            .where(Project.physical_progress_pct.is_(None))) or 0
        print("=== PAIMANA database inspection ===")
        print(f"projects          : {projects}")
        print(f"risk_results      : {risks}   (NULL time probability: {null_time})")
        print(f"early_warnings    : {warnings}")
        print(f"projects missing physical progress: {missing_progress}")
        print("snapshots:")
        for snap in snapshots:
            print(f"  - {snap.snapshot_id} [{snap.status}] month={snap.reporting_month} "
                  f"imported_at={snap.imported_at} source={snap.source_dataset}")
            print(f"    summary: {snap.summary_json}")


if __name__ == "__main__":
    main()
