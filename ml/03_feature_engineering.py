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


# --------------------------------------------------------------- reports ----
def feature_dictionary() -> pd.DataFrame:
    """Machine-readable dictionary of every modelled feature."""
    sources = {
        "original_cost_crore": "original_cost_crore",
        "log1p_original_cost": "original_cost_crore",
        "approval_year": "approval_date",
        "approval_month": "approval_date",
        "planned_horizon_months": "approval_date + target_doc",
        "cumulative_expenditure_crore": "cumulative_expenditure_crore",
        "log1p_expenditure": "cumulative_expenditure_crore",
        "expenditure_ratio": "cumulative_expenditure_crore / original_cost_crore",
        "physical_progress_pct": "physical_progress_pct",
        "progress_expenditure_gap": "expenditure_ratio + physical_progress_pct",
        "project_age_months": "start_date (vs report month)",
        "planned_duration_months": "start_date + target_doc",
        "approval_to_start_months": "approval_date + start_date",
        "months_to_target": "target_doc (vs report month)",
        "target_passed": "target_doc (vs report month)",
        "schedule_elapsed_pct": "start_date + target_doc (vs report month)",
        "progress_vs_schedule_pct": "schedule_elapsed_pct + physical_progress_pct",
        "agency": "agency",
        "state": "state",
    }
    descriptions = {
        "original_cost_crore": "Sanctioned cost at approval (crore INR).",
        "log1p_original_cost": "log1p of sanctioned cost (stabilises skew).",
        "approval_year": "Calendar year of sanction.",
        "approval_month": "Calendar month of sanction.",
        "planned_horizon_months": "Planned months from sanction to target completion.",
        "cumulative_expenditure_crore": "Money spent up to April 2026 (STATUS ONLY).",
        "log1p_expenditure": "log1p of cumulative expenditure (STATUS ONLY).",
        "expenditure_ratio": "Spend as fraction of sanctioned cost (STATUS ONLY).",
        "physical_progress_pct": "Reported physical progress % (STATUS ONLY).",
        "progress_expenditure_gap": "Spend% minus progress% (STATUS ONLY).",
        "project_age_months": "Months from start to April 2026 (STATUS ONLY).",
        "planned_duration_months": "Planned months start -> target (STATUS ONLY).",
        "approval_to_start_months": "Actual mobilisation lag (STATUS ONLY).",
        "months_to_target": "Months from April 2026 to target (STATUS ONLY).",
        "target_passed": "1.0 if target completion already passed (STATUS ONLY).",
        "schedule_elapsed_pct": "% of planned window elapsed at April 2026 "
                                "(STATUS ONLY).",
        "progress_vs_schedule_pct": "Progress% minus elapsed schedule% "
                                    "(STATUS ONLY).",
        "agency": "Executing agency (normalised in the audit step).",
        "state": "State / multi-state location.",
    }
    rows = []
    for f in STATUS_FEATURES:
        rows.append({
            "feature": f,
            "experiment": "plan_only + current_status" if f in PLAN_FEATURES
                          else "current_status only",
            "dtype": "categorical" if f in CATEGORICAL_FEATURES else "numeric",
            "source_columns": sources.get(f, ""),
            "description": descriptions.get(f, ""),
        })
    return pd.DataFrame(rows)


def write_leakage_review(df: pd.DataFrame, path: Path) -> str:
    """Write the mandatory leakage / feature-allowance review (Step 4)."""
    cost_ok = int((df["cost_overrun_label"] != -1).sum())
    cost_pos = int((df["cost_overrun_label"] == 1).sum())
    time_ok = int((df["time_overrun_label"] != -1).sum())
    time_pos = int((df["time_overrun_label"] == 1).sum())
    future_start = int((_date(df, "start_date") > REPORT_MONTH).sum())

    L: list[str] = []
    add = L.append
    add("# PAIMANA AI - LEAKAGE REVIEW (Phase 3, Steps 2-4)")
    add("")
    add(f"- generated (UTC): {datetime.now(timezone.utc).isoformat()}")
    add(f"- source data: data/processed/paimana_clean.csv (raw CSV sha256 "
        f"`{sha256_of(ROOT / 'PAIMANA_April_2026_Dataset.csv')}`)")
    add("- snapshot: **April 2026** (single month; report_month is constant)")
    add("")
    add("## 1. Target definitions and class counts")
    add("")
    add("| Target | Definition | Eligible | Positive | Negative | Unknown (-1, excluded) |")
    add("|---|---|---|---|---|---|")
    add(f"| cost_overrun_label | 1 if `revised_cost_crore > original_cost_crore`, "
        f"else 0; **-1** if either cost is missing/invalid (NaN or <= 0) | "
        f"{cost_ok} | {cost_pos} | {cost_ok - cost_pos} | {len(df) - cost_ok} |")
    add(f"| time_overrun_label | 1 if `revised_doc > target_doc`, else 0; **-1** "
        f"if either date is missing/invalid | {time_ok} | {time_pos} | "
        f"{time_ok - time_pos} | {len(df) - time_ok} |")
    add("")
    add("Unknown labels stay at **-1** and are dropped from supervised training; "
        "they are NEVER encoded as class 0 (a missing revised_doc must not be "
        "read as 'no schedule overrun').")
    add("")
    add("## 2. Rejected columns (never used as features)")
    add("")
    add("| FEATURE | MODEL | LEAKAGE RISK | REASON |")
    add("|---|---|---|---|")
    for col, (model, risk, reason) in REJECTED_COLUMNS.items():
        add(f"| `{col}` | {model} | **{risk}** | {reason} |")
    add("")
    add("## 3. Allowed features - COST OVERRUN model")
    add("")
    add("`revised_cost_crore` and anything derived from it are used **only** to "
        "build the label. None of the features below touch it.")
    add("")
    add("| FEATURE | EXPERIMENT | LEAKAGE RISK | REASON |")
    add("|---|---|---|---|")
    for f in PLAN_FEATURES:
        add(f"| `{f}` | plan_only + current_status | NONE | Fixed at sanction "
            "time; contains no post-approval outcome information. |")
    for f in STATUS_EXTRA_FEATURES:
        add(f"| `{f}` | current_status only | LOW-MED (status, not leakage) | "
            "Observed April-2026 state derived from plan/status columns only - "
            "never from revised_cost_crore, so it does not read the label; but "
            "it is measured *after* the project started, so it is allowed only "
            "in the clearly documented current-status experiment. |")
    add("")


    add("## 4. Allowed features - TIME OVERRUN model")
    add("")
    add("`revised_doc` and anything derived from it are used **only** to build "
        "the label; no feature below ever reads it.")
    add("")
    add("| FEATURE | EXPERIMENT | LEAKAGE RISK | REASON |")
    add("|---|---|---|---|")
    for f in PLAN_FEATURES:
        add(f"| `{f}` | plan_only + current_status | NONE | Plan-time fact; "
            "`target_doc` appears only as a planned-duration anchor and is never "
            "compared with `revised_doc`. |")
    for f in STATUS_EXTRA_FEATURES:
        add(f"| `{f}` | current_status only | LOW-MED (status, not leakage) | "
            "Computed from plan/status columns only (`start_date`, `target_doc`, "
            "expenditure, progress vs the constant report month); `revised_doc` "
            "is never read. Deadline-relative fields (`months_to_target`, "
            "`target_passed`) do associate with revision likelihood, but contain "
            "no revised-date information - this is documented confounding, not "
            "leakage. |")
    add("")
    add("## 5. Early-warning suitability assessment (important)")
    add("")
    add("- The **plan_only** experiment uses only information fixed at sanction "
        "(cost, approval timing, planned horizon, agency, state). It is the only "
        "set that may be described as *early prediction*.")
    add("- The **current_status** experiment adds April-2026 expenditure, "
        "physical progress, project age and deadline proximity. These fields "
        "reflect how the project is going *now*.")
    add("- **Using current-status features does NOT prove early predictive "
        "capability.** Strong current-status results only show that the model "
        "can classify present condition from present signals; they cannot show "
        "the model would have flagged an overrun *before* it happened. Such "
        "models are reported strictly as *current-status classifiers*.")
    add(f"- {future_start} rows have `start_date` after the report month, so even "
        "start-derived fields carry current-state information; that is why all "
        "start-derived features live in `current_status only`.")
    add("- This dataset is a **single April 2026 snapshot**. It cannot support "
        "temporal validation or establish future prediction performance. A later "
        "phase must obtain historical monthly snapshots and run temporal "
        "validation before the system may be presented as a validated "
        "forecasting system.")
    add("")
    add("## 6. Structural / split notes")
    add("")
    add("- `report_month` is constant -> rejected as a feature.")
    add("- Identifiers (`sl_no`, `project_code`, `legacy_ocms_code`, `pmgid`) and "
        "`project_name` rejected -> memorisation risk.")
    add("- No duplicate rows and no duplicate `project_code` -> one project "
        "cannot appear in both train and test.")
    add("- Agencies and states are shared across the split, and only one month "
        "exists, so any later train/test split measures *within-snapshot* "
        "generalisation only.")
    add("")
    text = "\n".join(L)
    path.write_text(text, encoding="utf-8")
    return text


# =================================================================== main ====
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FEATURES_CSV.parent.mkdir(parents=True, exist_ok=True)

    # ---- STEP 1: inspect the data before using anything --------------------
    df = pd.read_csv(CLEAN_CSV)
    print("=" * 78)
    print("PAIMANA AI - PHASE 3 - STEP 2/3/4 : TARGETS + FEATURES + LEAKAGE")
    print("=" * 78)
    print(f"input  : {CLEAN_CSV.relative_to(ROOT)}")
    print(f"shape  : {df.shape[0]} rows x {df.shape[1]} columns")

    print("\n[STEP 1] REQUIRED COLUMN CHECK (nothing is assumed):")
    missing = []
    for c in REQUIRED_COLUMNS:
        if c in df.columns:
            print(f"    {c:<32} OK        missing={int(df[c].isna().sum())}")
        else:
            missing.append(c)
            print(f"    {c:<32} MISSING")
    if missing:
        raise RuntimeError(f"Required columns absent from {CLEAN_CSV.name}: "
                           f"{missing}. Fix the cleaning step first.")

    print("\n    dtypes:")
    for c, dt in df.dtypes.items():
        print(f"      {c:<32} {dt}")
    n_dup = int(df.duplicated().sum())
    n_dup_code = int(df["project_code"].duplicated().sum())
    print(f"\n    duplicate rows      : {n_dup}")
    print(f"    duplicate project_code: {n_dup_code}")
    if "report_month" in df.columns:
        print(f"    report_month uniques : {list(df['report_month'].unique())}"
              "  (constant -> rejected as feature)")

    # ---- STEPS 2 & 3: targets ---------------------------------------------
    df = add_targets(df)
    print("\n[STEPS 2-3] TARGET DEFINITIONS AND CLASS COUNTS")
    print("    cost_overrun_label = 1 if revised_cost_crore >  original_cost_crore")
    print("                         0 if revised_cost_crore <= original_cost_crore")
    print("                        -1 if either cost missing/invalid  (EXCLUDED)")
    print("    time_overrun_label = 1 if revised_doc > target_doc")
    print("                         0 if revised_doc <= target_doc")
    print("                        -1 if either date missing/invalid  (EXCLUDED)")
    for name, col in LABELS.items():
        vc = df[col].value_counts().sort_index()
        unk = int(vc.get(-1, 0))
        pos = int(vc.get(1, 0))
        neg = int(vc.get(0, 0))
        print(f"\n    {name}: eligible={pos + neg}  positive={pos} "
              f"({100 * pos / max(pos + neg, 1):.1f}%)  negative={neg}  "
              f"unknown(excluded)={unk}")
        assert unk == int((df[col] == -1).sum())

    # ---- STEP 4: features + leakage guard ---------------------------------
    df = derive_features(df)
    leaked = set(REJECTED_COLUMNS) & set(STATUS_FEATURES)
    assert not leaked, f"Leakage guard failed: {sorted(leaked)}"
    print("\n[STEP 4] LEAKAGE GUARD: rejected columns never appear in the feature "
          f"lists -> {'PASS' if not leaked else 'FAIL'}")
    print(f"    plan_only features      ({len(PLAN_FEATURES)}): {PLAN_FEATURES}")
    print(f"    current_status features ({len(STATUS_FEATURES)}): "
          "plan_only + {status extras}")
    print("    NOTE: current_status features document a CURRENT-STATUS "
          "classifier only;")
    print("          they are NOT evidence of early predictive capability.")

    n_missing_feat = {f: int(df[f].isna().sum()) for f in STATUS_FEATURES
                      if df[f].isna().any()}
    print(f"\n    derived-feature missing values (imputed later in training): "
          f"{n_missing_feat if n_missing_feat else 'none'}")

    # ---- save artifacts ----------------------------------------------------
    df.to_csv(FEATURES_CSV, index=False)
    feature_dictionary().to_csv(OUT_DIR / "feature_dictionary.csv", index=False)
    write_leakage_review(df, OUT_DIR / "leakage_review.md")

    print("\n[OUTPUTS]")
    for p in (FEATURES_CSV, OUT_DIR / "feature_dictionary.csv",
              OUT_DIR / "leakage_review.md"):
        print(f"    saved {p.relative_to(ROOT)}  ({p.stat().st_size} bytes)")
    print(f"\n    original CSV sha256 (must be unchanged): "
          f"{sha256_of(ROOT / 'PAIMANA_April_2026_Dataset.csv')}")
    print("    original CSV opened read-only; neither CSV was modified here.")


if __name__ == "__main__":
    main()






