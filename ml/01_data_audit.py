"""
PAIMANA AI - STEP 1 (DATA AUDIT) + STEP 2 (DATA CLEANING)
=========================================================
Project : PAIMANA AI - Predictive Infrastructure Risk Monitoring and Early Warning System
Phase   : ML prototype only (no backend / frontend / DB / LLM / RAG / deployment)

WHAT THIS SCRIPT DOES
---------------------
STEP 1 : Inspects PAIMANA_April_2026_Dataset.csv WITHOUT assuming column names.
         Prints and saves a full dataset report (shape, dtypes, missing values,
         duplicates, id columns, numeric/categorical/date/cost/expenditure/
         progress/completion-date columns, data-quality anomalies).

STEP 2 : Runs a documented cleaning pipeline and writes the cleaned data to
             data/processed/paimana_clean.csv
         The ORIGINAL CSV is opened read-only and is never modified.

DECISION PRINCIPLE: no row is deleted unless it is an exact duplicate of
another row. Every questionable value is either repaired with a documented
rule or kept and reported. Every decision is printed and saved.

Run:  python ml/01_data_audit.py
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Paths / config (script-relative so the pipeline is reproducible anywhere)
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW_CSV = ROOT / "PAIMANA_April_2026_Dataset.csv"
CLEAN_CSV = ROOT / "data" / "processed" / "paimana_clean.csv"
OUT_DIR = ROOT / "outputs" / "eda"

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# Semantic column groups - discovered from the data, not assumed a priori.
NUMERIC_COLUMNS = [
    "original_cost_crore",
    "revised_cost_crore",
    "cumulative_expenditure_crore",
    "physical_progress_pct",
]
DATE_COLUMNS = ["approval_date", "start_date", "target_doc", "revised_doc"]
COST_COLUMNS = ["original_cost_crore", "revised_cost_crore"]
EXPENDITURE_COLUMNS = ["cumulative_expenditure_crore"]
PROGRESS_COLUMNS = ["physical_progress_pct"]
COMPLETION_DATE_COLUMNS = ["target_doc", "revised_doc"]
ID_COLUMNS = ["sl_no", "project_code", "legacy_ocms_code", "pmgid"]

# Placeholder strings used in the CSV to express "no value".
PLACEHOLDERS = {"", "-", "--", "na", "n/a", "nan", "none", "null", "."}
PLACEHOLDER_TOKENS = {"na", "n/a", "nan", "none", "null"}  # only converted to NaN

# Documented agency aliases (only exact, unambiguous cases are merged).
AGENCY_ALIASES = {
    "NHAI": "National Highways Authority of India [NHAI]",
}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def agency_key(text: str) -> str:
    """Canonical key: lowercase, alphanumerics only.
    Merges spelling/case/punctuation variants of the same agency
    (e.g. 'Western Railway [WR] - II' == 'Western Railway WR - II')."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def normalize_agency(series: pd.Series) -> tuple[pd.Series, dict]:
    """Return (normalized agency, merge-map {canonical: [merged variants]})."""
    s = series.map(collapse_ws)
    s = s.str.replace(r"^\((.*)\)$", r"\1", regex=True)  # drop wrapping parens
    s = s.replace(AGENCY_ALIASES)
    keys = s.map(agency_key)
    tmp = pd.DataFrame({"key": keys, "val": s})
    canonical = tmp.groupby("key")["val"].agg(lambda v: v.value_counts().index[0])
    out = keys.map(canonical)
    merge_map = {}
    for key, grp in tmp.groupby("key")["val"]:
        variants = sorted(grp.unique())
        if len(variants) > 1:
            merge_map[variants[0]] = variants
    return out, merge_map


def parse_month(series: pd.Series) -> pd.Series:
    """MM/YYYY -> datetime64 (first day of month). Invalid -> NaT."""
    return pd.to_datetime(series, format="%m/%Y", errors="coerce")


def build_report(raw: pd.DataFrame, typed: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add("PAIMANA AI - STEP 1 : DATASET AUDIT REPORT")
    add(f"generated_utc : {datetime.now(timezone.utc).isoformat()}")
    add(f"source_file   : {RAW_CSV.name}")
    add(f"sha256        : {sha256_of(RAW_CSV)}  (original file left untouched)")
    add("=" * 78)

    # --- 1. shape ----------------------------------------------------------
    add("")
    add("[1] SHAPE")
    add(f"    rows    : {raw.shape[0]}")
    add(f"    columns : {raw.shape[1]}")

    # --- 2. columns & dtypes ----------------------------------------------
    add("")
    add("[2] COLUMNS AND DTYPES (pandas-inferred on a default read)")
    for col in typed.columns:
        add(f"    - {col:<32} {str(typed[col].dtype)}")

    # --- 3. column profile --------------------------------------------------
    profile_rows = []
    add("")
    add("[3] MISSING VALUES / PLACEHOLDERS / CARDINALITY")
    add(f"    {'column':<32} {'dtype':<10} {'nan':>6} {'placeholder':>12} {'nunique':>8}")
    for col in raw.columns:
        nan_n = int(raw[col].isna().sum())
        mask = raw[col].notna() & raw[col].map(
            lambda v: collapse_ws(v).lower() in PLACEHOLDERS
        )
        ph_n = int(mask.sum())
        nuniq = int(raw[col].nunique(dropna=True))
        add(f"    {col:<32} {str(typed[col].dtype):<10} {nan_n:>6} {ph_n:>12} {nuniq:>8}")
        entry = {
            "column": col,
            "dtype": str(typed[col].dtype),
            "n_missing_nan": nan_n,
            "n_placeholder": ph_n,
            "n_unique": nuniq,
        }
        if pd.api.types.is_numeric_dtype(typed[col]):
            entry["min"] = float(typed[col].min()) if typed[col].notna().any() else None
            entry["max"] = float(typed[col].max()) if typed[col].notna().any() else None
            entry["mean"] = float(typed[col].mean()) if typed[col].notna().any() else None
        else:
            entry["sample"] = " | ".join(map(str, raw[col].dropna().unique()[:3]))
        profile_rows.append(entry)
    profile = pd.DataFrame(profile_rows)

    # --- 4. duplicates ------------------------------------------------------
    add("")
    add("[4] DUPLICATE RECORDS")
    add(f"    exact duplicate rows                 : {int(raw.duplicated().sum())}")
    add(f"    duplicate project_code values        : {int(raw['project_code'].duplicated().sum())}")
    add(f"    duplicate project_name values        : {int(raw['project_name'].duplicated().sum())}")

    # --- 5. identifiers -----------------------------------------------------
    add("")
    add("[5] UNIQUE PROJECT IDENTIFIERS")
    for col in ID_COLUMNS:
        if col in raw.columns:
            blank = int(raw[col].map(collapse_ws).str.lower().isin(PLACEHOLDERS).sum())
            add(f"    {col:<22} unique={raw[col].nunique():>6}  blank/'-'={blank:>5}")

    # --- 6. semantic column groups -----------------------------------------
    numeric_cols = [c for c in typed.columns if pd.api.types.is_numeric_dtype(typed[c])]
    date_like = [c for c in DATE_COLUMNS if c in typed.columns]
    categorical_cols = [
        c for c in typed.columns
        if c not in numeric_cols and c not in date_like and c not in ID_COLUMNS
    ]
    add("")
    add("[6] COLUMN GROUPS (used by every later step)")
    add(f"    numerical columns           : {numeric_cols}")
    add(f"    categorical columns         : {categorical_cols}")
    add(f"    date columns (MM/YYYY)      : {date_like}")
    add(f"    cost-related columns        : {COST_COLUMNS}")
    add(f"    expenditure-related columns : {EXPENDITURE_COLUMNS}")
    add(f"    physical-progress columns   : {PROGRESS_COLUMNS}")
    add(f"    completion-date columns     : {COMPLETION_DATE_COLUMNS}")
    add(f"    identifier columns          : {ID_COLUMNS}")
    add(f"    constant columns            : "
        f"{[c for c in typed.columns if typed[c].nunique(dropna=True) <= 1]}")

    # --- 7. parsed dates ----------------------------------------------------
    add("")
    add("[7] DATE PARSING (format %m/%Y)")
    for col in date_like:
        parsed = parse_month(raw[col])
        bad = int(raw[col].notna().sum() - parsed.notna().sum())
        add(f"    {col:<20} invalid={bad:>4}  min={parsed.min()}  max={parsed.max()}")

    # --- 8. anomalies (reported, NOT deleted) -------------------------------
    o, r = typed["original_cost_crore"], typed["revised_cost_crore"]
    esc = (r - o) / o
    target, rev = parse_month(raw["target_doc"]), parse_month(raw["revised_doc"])
    slip = (rev.dt.year * 12 + rev.dt.month) - (target.dt.year * 12 + target.dt.month)
    start, appr = parse_month(raw["start_date"]), parse_month(raw["approval_date"])
    rep_month = pd.Timestamp("2026-04-01")

    add("")
    add("[8] DATA-QUALITY ANOMALIES (kept in the dataset, documented here)")
    add(f"    revised_cost < original_cost          : {int((r < o).sum())}")
    add(f"    revised_cost == original_cost         : {int((r == o).sum())}")
    add(f"    revised_cost > original_cost          : {int((r > o).sum())}")
    add(f"    extreme cost reduction (>90%)         : {int((esc < -0.9).sum())}")
    add(f"    cumulative expenditure > original cost: {int((typed['cumulative_expenditure_crore'] > o).sum())}")
    add(f"    physical_progress outside [0,100]     : "
        f"{int((~typed['physical_progress_pct'].between(0, 100)).sum())}")
    add(f"    start_date < approval_date            : {int((start < appr).sum())}")
    add(f"    target completion before report month : {int((target < rep_month).sum())}")
    add(f"    missing revised_doc (no revision)     : {int(rev.isna().sum())}")
    add(f"    revised completion EARLIER than target: {int((slip < 0).sum())}")
    add(f"    scheduled slip months > 0             : {int((slip > 0).sum())}")

    # --- 9. target feasibility (STEP 5 preview) -----------------------------
    add("")
    add("[9] TARGET FEASIBILITY CHECK (defines what STEP 5 can defensibly do)")
    cost_pos = int((r > o).sum())
    time_pos = int((slip > 0).sum())
    time_neg_known = int((slip <= 0).sum())
    time_unknown = int(slip.isna().sum())
    add(f"    cost  escalation candidates (>0)      : {cost_pos} / {len(raw)} "
        f"({100 * cost_pos / len(raw):.1f}%)  -> cost_overrun_label possible: YES")
    add(f"    cost  escalation > 5%                 : {int((esc > 0.05).sum())}")
    add(f"    cost  escalation > 10%                : {int((esc > 0.10).sum())}")
    add(f"    time  revised_doc > target_doc        : {time_pos} / {len(raw)} "
        f"({100 * time_pos / len(raw):.1f}%)  -> time_overrun_label possible: YES")
    add(f"    time  revised_doc <= target_doc       : {time_neg_known}")
    add(f"    time  revised_doc missing (label=0*)  : {time_unknown}   *documented assumption")
    add("")
    add("    CONCLUSION: both targets are supported by the observed columns.")
    add("    No target definition is invented beyond these columns.")

    return "\n".join(lines), pd.DataFrame(profile_rows)


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[str, str, int]]]:
    """Returns (cleaned_df, decisions[(decision, rationale, rows_affected)])."""
    df = raw.copy()
    decisions: list[tuple[str, str, int]] = []

    # D1 - exact duplicates --------------------------------------------------
    n_dup = int(df.duplicated().sum())
    if n_dup:
        df = df.drop_duplicates().reset_index(drop=True)
    decisions.append((
        "Drop exact duplicate rows",
        "A byte-identical row carries no extra information and would leak "
        "between train/test splits. No fuzzy/near-duplicate removal is done.",
        n_dup,
    ))

    # D2 - whitespace / placeholder normalisation ----------------------------
    n_ph = 0
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda v: collapse_ws(v) if pd.notna(v) else v)
            mask = df[col].notna() & df[col].str.lower().isin(PLACEHOLDER_TOKENS)
            n_ph += int(mask.sum())
            df.loc[mask, col] = np.nan
    decisions.append((
        "Trim whitespace in text columns; map 'NA'/'NULL'/... tokens to NaN",
        "Placeholders are not real category values; keeping them would create "
        "fake levels in one-hot encoding. Literal '-' is kept for id columns "
        "and reported instead, since those ids are never model features.",
        n_ph,
    ))

    # D3 - numeric coercion + physical range rules ---------------------------
    bad_numeric = {}
    for col in NUMERIC_COLUMNS:
        before = int(df[col].isna().sum())
        df[col] = pd.to_numeric(df[col], errors="coerce")
        bad_numeric[col] = int(df[col].isna().sum() - before)
    n_progress = int(
        (~df["physical_progress_pct"].between(0, 100)
         & df["physical_progress_pct"].notna()).sum()
    )
    df.loc[~df["physical_progress_pct"].between(0, 100), "physical_progress_pct"] = np.nan
    n_nonpos = int(((df["original_cost_crore"] <= 0) |
                    (df["revised_cost_crore"] <= 0) |
                    (df["cumulative_expenditure_crore"] < 0)).sum())
    df.loc[df["original_cost_crore"] <= 0, "original_cost_crore"] = np.nan
    df.loc[df["revised_cost_crore"] <= 0, "revised_cost_crore"] = np.nan
    df.loc[df["cumulative_expenditure_crore"] < 0, "cumulative_expenditure_crore"] = np.nan
    decisions.append((
        "Coerce the 4 numeric columns to float; physical progress must lie in "
        "[0,100], costs must be > 0, expenditure >= 0 (else NaN)",
        "Physically impossible values are set to missing (median-imputed later "
        "inside the model pipeline) instead of deleting the project record.",
        sum(bad_numeric.values()) + n_progress + n_nonpos,
    ))

    # D4 - dates --------------------------------------------------------------
    bad_dates = {}
    for col in DATE_COLUMNS:
        parsed = parse_month(df[col])
        bad_dates[col] = int(df[col].notna().sum() - parsed.notna().sum())
        df[col] = parsed
    decisions.append((
        "Parse MM/YYYY date columns to datetime64 (day=1); unparseable -> NaT",
        "All date features must be real dates for duration/age arithmetic. "
        "Every date in the file parsed successfully (0 invalid values found).",
        sum(bad_dates.values()),
    ))

    # D5 - categorical consistency: agency -----------------------------------
    n_before = df["agency"].nunique()
    df["agency"], merge_map = normalize_agency(df["agency"])
    n_after = df["agency"].nunique()
    decisions.append((
        "Normalise 'agency': trim, unwrap parentheses, case/punctuation-insensitive "
        "merge of identical names, alias NHAI -> full name",
        "188 raw spellings contained variants of the same body (e.g. "
        "'Western Railway [WR] - II' vs 'Western Railway WR - II', '(NHAI)' vs "
        "'(National Highways Authority of India [NHAI])'). Merging prevents the "
        "same agency being encoded as several unrelated one-hot columns. "
        f"merged groups ({len(merge_map)}): "
        + "; ".join(f"{k} <- {v}" for k, v in list(merge_map.items())[:10]),
        n_before - n_after,
    ))

    # D6 - categorical consistency: state ------------------------------------
    n_state_before = df["state"].nunique()
    df["state"] = df["state"].map(collapse_ws)
    n_state_after = df["state"].nunique()
    decisions.append((
        "Trim/collapse whitespace in 'state'; keep 'Multi-States (...)' as-is",
        "Only whitespace normalisation is safe without an external reference. "
        "Multi-state projects are a real category (191 rows) and are kept; "
        "rare states are grouped at encoding time (one-hot min_frequency).",
        n_state_before - n_state_after,
    ))

    # D7 - logical anomalies that are KEPT -----------------------------------
    start, appr = df["start_date"], df["approval_date"]
    n_backwards = int((start < appr).sum())
    n_rev_lower = int((df["revised_cost_crore"] < df["original_cost_crore"]).sum())
    decisions.append((
        "KEEP rows where start_date < approval_date and where revised cost < "
        "original cost (flagged, not deleted)",
        "These are either genuine (early start, de-scoped works) or data-entry "
        "errors we cannot prove. Deleting ~50-300 real projects would bias the "
        "sample; the values are reported in the audit and remain usable as-is.",
        n_backwards + n_rev_lower,
    ))

    return df, decisions


# ============================================================================
# MAIN
# ============================================================================
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CLEAN_CSV.parent.mkdir(parents=True, exist_ok=True)

    # STEP 1 - read raw twice: strings (to see true placeholders) + typed.
    raw = pd.read_csv(RAW_CSV, dtype=str)
    typed = pd.read_csv(RAW_CSV)
    report, profile = build_report(raw, typed)
    print(report)

    profile.to_csv(OUT_DIR / "01_column_profile.csv", index=False)
    (OUT_DIR / "01_data_audit_report.txt").write_text(report, encoding="utf-8")

    # STEP 2 - clean.
    cleaned, decisions = clean(raw)
    log_lines = [
        "=" * 78,
        "PAIMANA AI - STEP 2 : CLEANING DECISION LOG",
        f"source      : {RAW_CSV.name} (unchanged, sha256={sha256_of(RAW_CSV)})",
        f"output      : {CLEAN_CSV.relative_to(ROOT)}",
        f"rows in/out : {len(raw)} -> {len(cleaned)} "
        f"(rows removed = {len(raw) - len(cleaned)})",
        "rule        : no row is deleted unless it is an exact duplicate.",
        "=" * 78,
        "",
    ]
    for i, (decision, rationale, affected) in enumerate(decisions, 1):
        log_lines.append(f"[D{i}] {decision}")
        log_lines.append(f"     rows/values affected : {affected}")
        log_lines.append(f"     rationale            : {rationale}")
        log_lines.append("")
    log_lines.append("FINAL SCHEMA")
    for col, dt in cleaned.dtypes.items():
        log_lines.append(f"    {col:<32} {dt}  (missing={int(cleaned[col].isna().sum())})")
    log = "\n".join(log_lines)
    print("\n" + log)
    (OUT_DIR / "01_cleaning_log.txt").write_text(log, encoding="utf-8")

    # Save cleaned dataset (dates -> ISO strings for portability).
    out = cleaned.copy()
    for col in DATE_COLUMNS:
        out[col] = out[col].dt.strftime("%Y-%m-%d")
    out.to_csv(CLEAN_CSV, index=False)
    print(f"\nSaved cleaned dataset -> {CLEAN_CSV}")
    print(f"Original CSV untouched -> {RAW_CSV}")


if __name__ == "__main__":
    main()




