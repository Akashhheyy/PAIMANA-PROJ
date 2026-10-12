"""Import the April 2026 snapshot into SQLite (explicit CLI command).

Usage (from the project root):
    python -m backend.app.db.init_db          # schema first
    python -m backend.app.db.import_snapshot  # then import

Guarantees:
* Reads the existing CSV artifacts (features, risk, early-warning) with
  EXPLICIT column mapping; never writes to them.
* Verifies the three sources share the same project_code values before
  touching the database - relationships are never guessed.
* Idempotent: rerunning updates the same (project_code, report_month) rows
  (unique constraints + update-or-insert) - no duplicates.
* Transactional: any failure rolls the whole import back with a clear
  error (no partial data, no table drops).
* NULL stays NULL (354 unknown time-overrun probabilities stay NULL).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from .models import EarlyWarning, ImportSnapshot, Project, RiskResult

FEATURE_COLUMNS = [  # explicit source -> model mapping (features CSV)
    "project_code", "project_name", "agency", "state", "report_month",
    "approval_date", "start_date", "target_doc", "revised_doc",
    "original_cost_crore", "revised_cost_crore",
    "cumulative_expenditure_crore", "physical_progress_pct",
]
RISK_COLUMNS = [
    "project_code", "report_month", "cost_overrun_probability",
    "time_overrun_probability", "combined_risk_score", "risk_category",
    "score_status", "missing_component", "scoring_formula_version",
]
WARNING_COLUMNS = [
    "project_code", "report_month", "warning_type", "warning_priority",
    "warning_priority_label", "warning_message", "risk_indicators",
    "recommended_action", "explanation_method",
]


class ImportValidationError(Exception):
    """Raised before any database write when the snapshot fails validation."""


def load_snapshot_frames(project_root: Path) -> dict[str, pd.DataFrame]:
    """Read the three existing CSV artifacts with explicit columns."""
    return {
        "features": pd.read_csv(
            project_root / "data" / "processed" / "paimana_features.csv",
            usecols=FEATURE_COLUMNS),
        "risk": pd.read_csv(
            project_root / "outputs" / "risk" / "project_risk_scores.csv",
            usecols=RISK_COLUMNS),
        "warnings": pd.read_csv(
            project_root / "outputs" / "risk" / "early_warning_results.csv",
            usecols=WARNING_COLUMNS),
    }


def validate_frames(frames: dict[str, pd.DataFrame]) -> dict:
    """Fail loudly (before writes) on count/identifier/range problems."""
    fe, rk, wn = frames["features"], frames["risk"], frames["warnings"]
    problems: list[str] = []
    if not (len(fe) == len(rk) == len(wn)):
        problems.append(f"row counts differ: features={len(fe)} risk={len(rk)} "
                        f"warnings={len(wn)}")
    codes = {name: set(df["project_code"].astype(int)) for name, df in
             (("features", fe), ("risk", rk), ("warnings", wn))}
    if not (codes["features"] == codes["risk"] == codes["warnings"]):
        problems.append("project_code sets differ between the three sources")
    progress = pd.to_numeric(fe["physical_progress_pct"], errors="coerce")
    bad_progress = int((progress.notna()
                        & ((progress < 0) | (progress > 100))).sum())
    if bad_progress:
        problems.append(
            f"{bad_progress} physical_progress_pct values outside [0,100]")
    if any(df["project_code"].duplicated().any()
           for df in (fe, rk, wn)):
        problems.append("duplicate project_code within a source file")
    if problems:
        raise ImportValidationError("; ".join(problems))
    months = set(fe["report_month"].unique()) | set(rk["report_month"].unique())
    reporting_month = sorted(months)[0]
    snapshot_id = datetime.strptime(reporting_month, "%B %Y").strftime("%Y-%m")
    return {"projects": int(len(fe)), "risk_records": int(len(rk)),
            "warning_records": int(len(wn)),
            "null_time_probability": int(
                rk["time_overrun_probability"].isna().sum()),
            "reporting_month": reporting_month, "snapshot_id": snapshot_id}


def _clean(value, cast=float):
    """Pandas NaN/NaT -> None (NULL); everything else cast."""
    if value is None or pd.isna(value):
        return None
    return cast(value)


def _clean_date(value):
    """ISO string / Timestamp -> datetime.date, or None when missing."""
    if value is None or pd.isna(value):
        return None
    return pd.to_datetime(value, errors="raise").date()


def import_snapshot(db: Session, frames: dict[str, pd.DataFrame]) -> dict:
    """Idempotent, transactional import. Commits on success; rolls back the
    ENTIRE import on any failure and re-raises a clear error."""
    summary = validate_frames(frames)
    fe, rk, wn = frames["features"], frames["risk"], frames["warnings"]
    source = ("paimana_features.csv + project_risk_scores.csv + "
              "early_warning_results.csv")
    try:
        existing_projects = {p.project_code: p
                             for p in db.scalars(select(Project)).all()}
        existing_risks = {r.project_code: r
                          for r in db.scalars(select(RiskResult)).all()}
        existing_warnings = {w.project_code: w
                             for w in db.scalars(select(EarlyWarning)).all()}

        n_proj_new = n_risk_new = n_warn_new = 0
        for row in fe.itertuples(index=False):   # CSV order preserved (id)
            code = int(row.project_code)
            proj = existing_projects.get(code)
            if proj is None:
                proj = Project(project_code=code)
                db.add(proj)
                existing_projects[code] = proj
                n_proj_new += 1
            proj.project_name = str(row.project_name)
            proj.agency = str(row.agency)
            proj.state = str(row.state)
            proj.report_month = str(row.report_month)
            proj.approval_date = _clean_date(row.approval_date)
            proj.start_date = _clean_date(row.start_date)
            proj.target_doc = _clean_date(row.target_doc)
            proj.revised_doc = _clean_date(row.revised_doc)
            proj.original_cost_crore = _clean(row.original_cost_crore)
            proj.revised_cost_crore = _clean(row.revised_cost_crore)
            proj.cumulative_expenditure_crore = _clean(
                row.cumulative_expenditure_crore)
            proj.physical_progress_pct = _clean(row.physical_progress_pct)
        db.flush()   # projects must exist before FK-referencing inserts

        for row in rk.itertuples(index=False):
            code = int(row.project_code)
            risk = existing_risks.get(code)
            if risk is None:
                risk = RiskResult(project_code=code,
                                  report_month=str(row.report_month))
                db.add(risk)
                existing_risks[code] = risk
                n_risk_new += 1
            risk.cost_overrun_probability = float(row.cost_overrun_probability)
            risk.time_overrun_probability = _clean(row.time_overrun_probability)
            risk.combined_risk_score = _clean(row.combined_risk_score)
            risk.risk_category = str(row.risk_category)
            risk.score_status = str(row.score_status)
            risk.missing_component = str(row.missing_component)
            risk.scoring_formula_version = _clean(row.scoring_formula_version, str)
        db.flush()   # risk rows before warnings (same-truth ordering)

        for row in wn.itertuples(index=False):
            code = int(row.project_code)
            warn = existing_warnings.get(code)
            if warn is None:
                warn = EarlyWarning(project_code=code,
                                    report_month=str(row.report_month))
                db.add(warn)
                existing_warnings[code] = warn
                n_warn_new += 1
            warn.warning_type = str(row.warning_type)
            warn.warning_priority = str(row.warning_priority)
            warn.warning_priority_label = str(row.warning_priority_label)
            warn.warning_message = str(row.warning_message)
            warn.risk_indicators = str(row.risk_indicators)
            warn.recommended_action = str(row.recommended_action)
            warn.explanation_method = _clean(row.explanation_method, str)

        snap = db.scalar(select(ImportSnapshot).where(
            ImportSnapshot.snapshot_id == summary["snapshot_id"]))
        if snap is None:
            snap = ImportSnapshot(snapshot_id=summary["snapshot_id"])
            db.add(snap)
        snap.source_dataset = source
        snap.reporting_month = summary["reporting_month"]
        snap.imported_at = datetime.now(timezone.utc).replace(tzinfo=None)
        snap.status = "completed"
        snap.summary_json = json.dumps(
            {**summary, "projects_new": n_proj_new, "risk_new": n_risk_new,
             "warnings_new": n_warn_new})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise RuntimeError(
            f"snapshot import failed and was rolled back: {exc}") from None
    return summary


def main() -> int:
    root = get_settings().project_root
    from .session import SessionLocal
    try:
        frames = load_snapshot_frames(root)
        with SessionLocal() as db:
            summary = import_snapshot(db, frames)
        print("import completed successfully")
        for key, value in summary.items():
            print(f"  {key}: {value}")
        with SessionLocal() as db:
            for label, model in (("projects", Project),
                                 ("risk_results", RiskResult),
                                 ("early_warnings", EarlyWarning)):
                count = db.scalar(select(func.count()).select_from(model))
                print(f"  db count {label}: {count}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

