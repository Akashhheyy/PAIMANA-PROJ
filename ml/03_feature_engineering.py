"""
PAIMANA AI - PHASE 3 - STEP 2/3/4 (TARGETS, FEATURES, LEAKAGE REVIEW)
=====================================================================
Project : PAIMANA AI - Predictive Infrastructure Risk Monitoring and Early Warning System
Scope   : two individual binary models only (cost overrun, time overrun).
          NO risk engine, dashboard, API, database, LLM, RAG or deployment.

Reads  : data/processed/paimana_clean.csv   (produced by ml/01_data_audit.py)
Writes : data/processed/paimana_features.csv
         outputs/models/feature_dictionary.csv
         outputs/models/leakage_review.md

TARGET DEFINITIONS (documented, derived only from observed columns)
-------------------------------------------------------------------
cost_overrun_label = 1  if revised_cost_crore >  original_cost_crore
                   = 0  if revised_cost_crore <= original_cost_crore
                   = -1 (UNKNOWN -> excluded from training) if either cost is
                        missing or invalid (NaN or <= 0)

time_overrun_label = 1  if revised_doc > target_doc   (later completion date)
                   = 0  if revised_doc <= target_doc
                   = -1 (UNKNOWN -> excluded from training) if either date is
                        missing/invalid. 354 rows have no revised_doc; they are
                        NEVER treated as non-overruns.

LEAKAGE RULES
-------------
* No feature may be computed from revised_cost_crore (cost model) or from
  revised_doc (time model); those columns exist only to BUILD the labels.
* report_month is constant -> rejected.
* Identifiers / free text rejected: sl_no, project_code, legacy_ocms_code,
  pmgid, project_name.
* Two documented feature experiments:
    plan_only      -> information fixed at sanction time (early-warning-oriented)
    current_status -> plan_only + April-2026 status (expenditure, progress,
                      age vs plan). Explicitly a CURRENT-STATUS classifier,
                      not claimed as early warning.

Run:  python ml/03_feature_engineering.py
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN_CSV = ROOT / "data" / "processed" / "paimana_clean.csv"
FEATURES_CSV = ROOT / "data" / "processed" / "paimana_features.csv"
OUT_DIR = ROOT / "outputs" / "models"

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

REPORT_MONTH = pd.Timestamp("2026-04-01")  # snapshot reference "now"

# Columns whose presence is verified (never assumed) before use.
REQUIRED_COLUMNS = [
    "original_cost_crore", "revised_cost_crore", "cumulative_expenditure_crore",
    "physical_progress_pct", "approval_date", "start_date", "target_doc",
    "revised_doc", "agency", "state",
]
DATE_COLUMNS = ["approval_date", "start_date", "target_doc", "revised_doc"]

# Columns that are outcome/identity/constant -> never features.
REJECTED_COLUMNS = {
    "revised_cost_crore": ("cost_overrun", "LEAKAGE",
        "The cost label is defined directly as revised > original cost; any "
        "feature derived from it would read the answer."),
    "revised_doc": ("time_overrun", "LEAKAGE",
        "The time label is defined directly as revised_doc > target_doc; using "
        "revised_doc (or anything derived from it) would read the answer."),
    "cost_overrun_label": ("cost_overrun", "LEAKAGE", "The target itself."),
    "time_overrun_label": ("time_overrun", "LEAKAGE", "The target itself."),
    "report_month": ("both", "CONSTANT",
        "April 2026 for every row -> zero variance, no predictive value; it is "
        "the snapshot date, not a project attribute."),
    "sl_no": ("both", "IDENTIFIER", "Row serial number, unique per record."),
    "project_code": ("both", "IDENTIFIER",
        "Unique per project; would only let the model memorise rows."),
    "legacy_ocms_code": ("both", "IDENTIFIER",
        "Legacy id, mostly '-'; unique where populated."),
    "pmgid": ("both", "IDENTIFIER", "PMG id, mostly '-'; unique where populated."),
    "project_name": ("both", "IDENTIFIER/TEXT",
        "Free text unique per row (1981 distinct names); no text model in this "
        "phase, and it would act as a row identifier."),
}

PLAN_FEATURES = [
    "original_cost_crore",      # numeric, sanctioned cost (plan-time)
    "log1p_original_cost",      # numeric, size stabiliser for linear models
    "approval_year",            # from approval_date (plan-time)
    "approval_month",           # from approval_date (plan-time)
    "planned_horizon_months",   # target_doc - approval_date (planned duration)
    "agency",                   # categorical (plan-time)
    "state",                    # categorical (plan-time)
]
STATUS_EXTRA_FEATURES = [
    "cumulative_expenditure_crore",  # April-2026 status
    "log1p_expenditure",
    "expenditure_ratio",             # expenditure / original cost
    "physical_progress_pct",         # April-2026 status
    "progress_expenditure_gap",      # spend% - progress%
    "project_age_months",            # start_date-derived (status)
    "planned_duration_months",       # target_doc - start_date
    "approval_to_start_months",      # start_date-derived (status)
    "months_to_target",              # deadline distance vs April 2026
    "target_passed",                 # deadline already passed?
    "schedule_elapsed_pct",          # elapsed vs planned window
    "progress_vs_schedule_pct",      # physical progress - elapsed schedule
]
STATUS_FEATURES = PLAN_FEATURES + STATUS_EXTRA_FEATURES
CATEGORICAL_FEATURES = ["agency", "state"]
NUMERIC_FEATURES = [f for f in STATUS_FEATURES if f not in CATEGORICAL_FEATURES]

LABELS = {"cost_overrun": "cost_overrun_label", "time_overrun": "time_overrun_label"}


# ---------------------------------------------------------------- helpers ---
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ym(x) -> object:
    """year*12+month for a Series or a single Timestamp (NaN -> NaN)."""
    if isinstance(x, pd.Series):
        return x.dt.year * 12 + x.dt.month
    if pd.isna(x):
        return np.nan
    return x.year * 12 + x.month


def months_between(a, b) -> pd.Series:
    """Signed whole months from a to b (b - a); missing dates -> NaN."""
    return _ym(b) - _ym(a)


def _num(df: pd.DataFrame, name: str) -> pd.Series:
    """Numeric column, created as NaN when the source column is absent."""
    return pd.to_numeric(df[name], errors="coerce") if name in df.columns \
        else pd.Series(np.nan, index=df.index, dtype="float64")


def _date(df: pd.DataFrame, name: str) -> pd.Series:
    """Datetime column, created as NaT when the source column is absent."""
    if name not in df.columns:
        return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    return pd.to_datetime(df[name], errors="coerce")


# ------------------------------------------------------------ target logic ---
def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Attach cost_overrun_label / time_overrun_label (-1 = unknown)."""
    out = df.copy()
    orig = _num(out, "original_cost_crore")
    rev = _num(out, "revised_cost_crore")
    cost_ok = orig.notna() & rev.notna() & (orig > 0) & (rev > 0)
    out["cost_overrun_label"] = np.where(
        cost_ok, (rev > orig).astype("int64"), -1).astype("int64")

    tgt = _date(out, "target_doc")
    rdoc = _date(out, "revised_doc")
    time_ok = tgt.notna() & rdoc.notna()
    out["time_overrun_label"] = np.where(
        time_ok, (rdoc > tgt).astype("int64"), -1).astype("int64")
    return out


# ---------------------------------------------------------- feature logic ----
def derive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add every modelled feature. Uses ONLY plan columns + April-2026 status
    columns. NEVER reads revised_cost_crore or revised_doc (label sources).

    Robust to a single record with missing/absent source columns (used by the
    prediction loader)."""
    out = df.copy()
    approval = _date(out, "approval_date")
    start = _date(out, "start_date")
    target = _date(out, "target_doc")

    cost = _num(out, "original_cost_crore")
    spend = _num(out, "cumulative_expenditure_crore")
    progress = _num(out, "physical_progress_pct")

    # plan-only features -----------------------------------------------------
    out["original_cost_crore"] = cost
    out["log1p_original_cost"] = np.log1p(cost.where(cost > 0))
    out["approval_year"] = approval.dt.year.astype("float64")
    out["approval_month"] = approval.dt.month.astype("float64")
    out["planned_horizon_months"] = months_between(approval, target).astype("float64")

    # current-status features (April 2026 snapshot) --------------------------
    out["cumulative_expenditure_crore"] = spend
    out["log1p_expenditure"] = np.log1p(spend.where(spend >= 0))
    ratio = np.where(cost > 0, spend / cost, np.nan)
    out["expenditure_ratio"] = ratio
    out["physical_progress_pct"] = progress
    out["progress_expenditure_gap"] = np.where(
        np.isfinite(ratio), ratio * 100.0 - progress, np.nan)
    out["project_age_months"] = months_between(start, REPORT_MONTH).astype("float64")
    out["planned_duration_months"] = months_between(start, target).astype("float64")
    out["approval_to_start_months"] = months_between(
        approval, start).astype("float64")
    out["months_to_target"] = months_between(REPORT_MONTH, target).astype("float64")
    out["target_passed"] = (target < REPORT_MONTH).astype("float64")

    window = months_between(start, target).astype("float64")
    elapsed = months_between(start, REPORT_MONTH).astype("float64")
    elapsed_pct = np.where(window > 0, elapsed / window * 100.0, np.nan)
    out["schedule_elapsed_pct"] = elapsed_pct
    out["progress_vs_schedule_pct"] = np.where(
        np.isfinite(elapsed_pct), progress - elapsed_pct, np.nan)

    # categorical features must exist even for a sparse input record ---------
    for col in CATEGORICAL_FEATURES:
        if col not in out.columns:
            out[col] = np.nan
        else:
            out[col] = out[col].replace({"": np.nan}).astype("object")

    # guarantee every modelled feature column exists -------------------------
    for col in NUMERIC_FEATURES:
        if col not in out.columns:
            out[col] = np.nan
    return out


# END_PART_2


