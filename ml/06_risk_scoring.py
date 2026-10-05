"""
PAIMANA AI - PHASE 5 : PROJECT RISK SCORING + EARLY-WARNING LOGIC
=================================================================
Project : PAIMANA AI - Predictive Infrastructure Risk Monitoring and Early Warning System
Scope   : Prototype risk scoring ONLY. No frontend, backend API, database,
          LLM, RAG or deployment in this phase.

WHAT THIS SCRIPT DOES (no retraining, ever)
-------------------------------------------
1. Loads the Phase-4 saved pipelines with joblib.load() only:
       models/cost_overrun/pipeline.joblib   (RandomForestClassifier, plan_only)
       models/time_overrun/pipeline.joblib   (HistGradientBoosting, plan_only)
2. Reads data/processed/paimana_features.csv and feeds each pipeline EXACTLY
   the columns of its saved feature_names_in_ in that exact order.
3. cost_overrun_probability  -> generated for every eligible project
   (cost label != -1; all 1981 rows are eligible in this dataset).
4. time_overrun_probability  -> generated ONLY where time_overrun_label != -1.
   Unknown (-1) rows keep label -1 and get a MISSING time probability -
   they are never treated as negative cases and never scored as 0.
5. Transparent combination of the two probabilities (see formula below).
6. Writes outputs/risk/project_risk_scores.csv
   and   outputs/risk/risk_scoring_report.md

RISK SCORING FORMULA (version v1, equal weights - fully configurable)
---------------------------------------------------------------------
    both available : combined = (W_COST * cost_p + W_TIME * time_p)
                              / (W_COST + W_TIME)          -> status "complete"
    only one       : combined = the available probability  -> status "partial"
                     (missing component is RECORDED, never substituted with 0)
    neither        : combined = NaN                        -> status "missing"

    risk_category:
        score <  LOW_MAX            -> "Low"
        LOW_MAX <= score < HIGH_MIN -> "Medium"
        score >= HIGH_MIN           -> "High"
        score is NaN                -> "Unknown"

DEFAULT THRESHOLDS (prototype defaults, configurable constants below)
    LOW_MAX  = 0.35 , HIGH_MIN = 0.65
    Rationale: an equal-weighted probability centred on 0.5 is split into a
    symmetric "uncertain" middle band; the outer thirds flag clearly
    above/below-average overrun probability. These thresholds are NOT
    calibrated or validated on any outcome data - calibration on this same
    single snapshot would overfit. They are placeholders for a later phase.

HONESTY NOTICE
--------------
This is PROTOTYPE RISK SCORING over a single April 2026 snapshot. It is NOT
verified future prediction, NOT a validated early-warning rate, and it does
NOT establish causation: a high score means the modelled associations are
high, not that any feature causes an overrun.

Run:  python ml/06_risk_scoring.py
Tests: python -m unittest discover -s tests -v
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FEATURES_CSV = ROOT / "data" / "processed" / "paimana_features.csv"
RAW_CSV = ROOT / "PAIMANA_April_2026_Dataset.csv"
CLEAN_CSV = ROOT / "data" / "processed" / "paimana_clean.csv"
OUT_DIR = ROOT / "outputs" / "risk"
RESULTS_CSV = OUT_DIR / "project_risk_scores.csv"
REPORT_MD = OUT_DIR / "risk_scoring_report.md"

COST_PIPELINE = ROOT / "models" / "cost_overrun" / "pipeline.joblib"
COST_META = ROOT / "models" / "cost_overrun" / "metadata.json"
TIME_PIPELINE = ROOT / "models" / "time_overrun" / "pipeline.joblib"
TIME_META = ROOT / "models" / "time_overrun" / "metadata.json"

# ---- configurable scoring configuration ------------------------------------
W_COST = 0.5          # weight of cost probability in the combined score
W_TIME = 0.5          # weight of time probability in the combined score
LOW_MAX = 0.35        # score <  LOW_MAX           -> Low
HIGH_MIN = 0.65       # score >= HIGH_MIN          -> High  (else Medium)
FORMULA_VERSION = "v1-equal-weight-2026-04-snapshot"
COST_LABEL = "cost_overrun_label"
TIME_LABEL = "time_overrun_label"
PROB_TOL = 1e-9       # tolerance for probability range checks

# Columns no pipeline may ever receive (leakage guard inherited from Phase 4).
FORBIDDEN_INPUTS = {
    "cost_overrun_label", "time_overrun_label", "revised_cost_crore",
    "revised_doc", "sl_no", "project_code", "legacy_ocms_code", "pmgid",
    "project_name", "report_month",
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------- pure scoring functions ---------
def combine_probabilities(cost, time, w_cost: float = W_COST,
                          w_time: float = W_TIME) -> pd.DataFrame:
    """Combine cost/time overrun probabilities transparently.

    Parameters
    ----------
    cost, time : array-like of floats, None or NaN (scalar values allowed).
        NaN/None = probability not available for that component.
    w_cost, w_time : non-negative weights (defaults 0.5 / 0.5).

    Returns
    -------
    DataFrame indexed like the inputs with columns:
        combined_risk_score, score_status, missing_component
        score_status       : 'complete' | 'partial' | 'missing'
        missing_component  : 'none' | 'time_overrun_probability'
                             | 'cost_overrun_probability' | 'both'

    Formula (both present): (w_cost*cost + w_time*time) / (w_cost + w_time)
    Formula (one present) : the single available probability (status partial).
    A missing probability is NEVER replaced by 0.
    """
    cost_s = cost if isinstance(cost, pd.Series) else pd.Series(cost, dtype="float64")
    time_s = time if isinstance(time, pd.Series) else pd.Series(time, dtype="float64")
    cost_s = pd.to_numeric(cost_s, errors="coerce").astype("float64")
    time_s = pd.to_numeric(time_s, errors="coerce").astype("float64")
    if not cost_s.index.equals(time_s.index):
        time_s = time_s.reindex(cost_s.index)

    if w_cost < 0 or w_time < 0 or (w_cost + w_time) == 0:
        raise ValueError("weights must be non-negative and not both zero")

    has_cost, has_time = cost_s.notna(), time_s.notna()
    both = has_cost & has_time
    only_cost = has_cost & ~has_time
    only_time = ~has_cost & has_time

    combined = pd.Series(np.nan, index=cost_s.index, dtype="float64")
    total_w = float(w_cost + w_time)
    combined[both] = ((w_cost * cost_s[both] + w_time * time_s[both]) / total_w)
    combined[only_cost] = cost_s[only_cost]
    combined[only_time] = time_s[only_time]

    status = pd.Series("missing", index=cost_s.index, dtype="object")
    status[both] = "complete"
    status[only_cost | only_time] = "partial"

    missing = pd.Series("both", index=cost_s.index, dtype="object")
    missing[both] = "none"
    missing[only_cost] = "time_overrun_probability"
    missing[only_time] = "cost_overrun_probability"

    return pd.DataFrame({
        "combined_risk_score": combined,
        "score_status": status,
        "missing_component": missing,
    }, index=cost_s.index)


def risk_category(score, low_max: float = LOW_MAX,
                  high_min: float = HIGH_MIN) -> str:
    """Scalar: classify one combined score into Low / Medium / High / Unknown.
    Boundaries: [0, low_max) Low | [low_max, high_min) Medium |
                 [high_min, 1] High | NaN -> Unknown."""
    if score is None or (isinstance(score, float) and np.isnan(score)) or \
            pd.isna(score):
        return "Unknown"
    s = float(score)
    if s < low_max:
        return "Low"
    if s < high_min:
        return "Medium"
    return "High"


def assign_risk_categories(scores, low_max: float = LOW_MAX,
                           high_min: float = HIGH_MIN) -> pd.Series:
    """Vectorised wrapper around risk_category()."""
    if not isinstance(scores, pd.Series):
        scores = pd.Series(scores, dtype="float64")
    return pd.Series([risk_category(s, low_max, high_min) for s in scores],
                     index=scores.index, dtype="object")


# ---------------------------------------------- model loading / inference ----
def load_pipelines() -> dict:
    """joblib.load ONLY - models are never refit, replaced or retrained here.

    Inference determinism note: the saved RandomForest carries n_jobs=-1 from
    Phase 4. sklearn accumulates per-tree probabilities in thread-completion
    order, so parallel predict_proba() can differ in the last floating-point
    bits between runs (non-byte-identical CSVs). We therefore force
    n_jobs=1 on the IN-MEMORY object only: fitted parameters and the artifact
    files on disk are untouched, repeated runs become byte-identical."""
    for p in (COST_PIPELINE, TIME_PIPELINE, COST_META, TIME_META):
        assert p.exists(), f"missing Phase-4 artifact: {p}"
    pipes = {
        "cost_overrun": joblib.load(COST_PIPELINE),
        "time_overrun": joblib.load(TIME_PIPELINE),
    }
    for pipe in pipes.values():
        model = pipe.steps[-1][1]
        if hasattr(model, "n_jobs"):
            model.n_jobs = 1          # determinism only - NOT a retrain/replace
    return pipes


def schema_of(pipe) -> list[str]:
    """Exact input columns and order the saved pipeline expects."""
    names = getattr(pipe, "feature_names_in_", None)
    if names is None:
        raise AttributeError("pipeline has no feature_names_in_; cannot guarantee "
                             "the schema it was trained on")
    return list(names)


def predict_probabilities(df: pd.DataFrame, pipelines: dict) -> pd.DataFrame:
    """Cost probability for every eligible row; time probability ONLY where
    time_overrun_label != -1 (unknown rows stay NaN - never treated as 0/negative)."""
    out = pd.DataFrame(index=df.index)

    # ---- cost overrun probability -----------------------------------------
    cost_pipe = pipelines["cost_overrun"]
    cost_feats = schema_of(cost_pipe)
    assert not (set(cost_feats) & FORBIDDEN_INPUTS), "forbidden cost input!"
    assert all(f in df.columns for f in cost_feats), \
        f"dataset missing cost features: {[f for f in cost_feats if f not in df.columns]}"
    cost_eligible = df[COST_LABEL] != -1
    Xc = df.loc[cost_eligible, cost_feats]          # exact column ORDER
    p_cost = np.full(len(df), np.nan, dtype="float64")
    if len(Xc):
        proba = cost_pipe.predict_proba(Xc)
        idx = list(cost_pipe.classes_).index(1)
        p_cost[np.flatnonzero(cost_eligible.to_numpy())] = proba[:, idx]
    out["cost_overrun_probability"] = p_cost
    out["cost_probability_available"] = cost_eligible.to_numpy()

    # ---- time overrun probability (known labels only) ----------------------
    time_pipe = pipelines["time_overrun"]
    time_feats = schema_of(time_pipe)
    assert not (set(time_feats) & FORBIDDEN_INPUTS), "forbidden time input!"
    assert all(f in df.columns for f in time_feats), \
        f"dataset missing time features: {[f for f in time_feats if f not in df.columns]}"
    time_known = df[TIME_LABEL] != -1                # unknown -> NO prediction
    Xt = df.loc[time_known, time_feats]              # exact column ORDER
    p_time = np.full(len(df), np.nan, dtype="float64")
    if len(Xt):
        proba = time_pipe.predict_proba(Xt)
        idx = list(time_pipe.classes_).index(1)
        p_time[np.flatnonzero(time_known.to_numpy())] = proba[:, idx]
    out["time_overrun_probability"] = p_time
    out["time_probability_available"] = time_known.to_numpy()
    out["time_label_known"] = time_known.to_numpy()

    # ---- integrity assertions ---------------------------------------------
    c = out["cost_overrun_probability"].dropna()
    t = out["time_overrun_probability"].dropna()
    assert c.empty or (c.between(-PROB_TOL, 1 + PROB_TOL).all()), "cost prob out of range"
    assert t.empty or (t.between(-PROB_TOL, 1 + PROB_TOL).all()), "time prob out of range"
    # unknown time rows must remain NaN (never zero-filled):
    unknown_mask = df[TIME_LABEL] == -1
    assert out.loc[unknown_mask, "time_overrun_probability"].isna().all(), \
        "unknown time labels must not receive a probability"
    return out


# --------------------------------------------------------- risk table -------
def build_risk_table(df: pd.DataFrame | None = None,
                     pipelines: dict | None = None) -> pd.DataFrame:
    """Build the full project-level risk table (pure-ish; injectable for tests)."""
    if df is None:
        assert FEATURES_CSV.exists(), f"missing {FEATURES_CSV}"
        df = pd.read_csv(FEATURES_CSV)
    if pipelines is None:
        pipelines = load_pipelines()

    probs = predict_probabilities(df, pipelines)
    combo = combine_probabilities(probs["cost_overrun_probability"],
                                  probs["time_overrun_probability"])
    table = pd.DataFrame({
        "sl_no": df["sl_no"].to_numpy() if "sl_no" in df.columns else np.nan,
        "project_code": df["project_code"].to_numpy()
                        if "project_code" in df.columns else np.nan,
        "project_name": df["project_name"].to_numpy()
                        if "project_name" in df.columns else "",
        "state": df["state"].to_numpy() if "state" in df.columns else "",
        "agency": df["agency"].to_numpy() if "agency" in df.columns else "",
        "report_month": df["report_month"].to_numpy()
                        if "report_month" in df.columns else "",
        "cost_overrun_label": df[COST_LABEL].to_numpy(),
        "time_overrun_label": df[TIME_LABEL].to_numpy(),   # -1 preserved
        "cost_overrun_probability": probs["cost_overrun_probability"].to_numpy(),
        "time_overrun_probability": probs["time_overrun_probability"].to_numpy(),
        "cost_probability_available": probs[
            "cost_probability_available"].to_numpy(),
        "time_probability_available": probs[
            "time_probability_available"].to_numpy(),
        "combined_risk_score": combo["combined_risk_score"].to_numpy(),
        "score_status": combo["score_status"].to_numpy(),
        "missing_component": combo["missing_component"].to_numpy(),
    })
    table["risk_category"] = assign_risk_categories(
        table["combined_risk_score"]).to_numpy()
    table["scoring_formula_version"] = FORMULA_VERSION

    # ---- final integrity gates --------------------------------------------
    assert not (set(schema_of(pipelines["cost_overrun"])) & FORBIDDEN_INPUTS)
    assert not (set(schema_of(pipelines["time_overrun"])) & FORBIDDEN_INPUTS)
    known = table["time_overrun_label"] != -1
    assert table.loc[~known, "time_overrun_probability"].isna().all(), \
        "unknown time rows must keep NaN probability"
    assert table.loc[~known, "time_overrun_label"].eq(-1).all(), \
        "unknown time labels must be preserved as -1"
    for col in ("cost_overrun_probability", "time_overrun_probability"):
        s = table[col].dropna()
        assert s.empty or s.between(0.0, 1.0).all(), f"{col} outside [0,1]"
    s = table["combined_risk_score"].dropna()
    assert s.empty or s.between(0.0, 1.0).all(), "combined score outside [0,1]"
    # missing component must never be hidden behind a 0 score:
    partial = table["score_status"] == "partial"
    assert table.loc[partial, "missing_component"].ne("both").all()
    assert table.loc[partial, "missing_component"].ne("none").all()
    return table


def summary_counts(table: pd.DataFrame) -> dict:
    """Counts used by the report (all computed from the real table)."""
    return {
        "total_rows": int(len(table)),
        "cost_probability_available": int(
            table["cost_probability_available"].sum()),
        "time_probability_available": int(
            table["time_probability_available"].sum()),
        "time_label_unknown_rows": int((table["time_overrun_label"] == -1).sum()),
        "score_status": {k: int(v) for k, v in
                         table["score_status"].value_counts().items()},
        "missing_component": {k: int(v) for k, v in
                              table["missing_component"].value_counts().items()},
        "risk_category": {k: int(v) for k, v in
                          table["risk_category"].value_counts().items()},
        "risk_category_by_status": {
            f"{status}|{cat}": int(n)
            for (status, cat), n in
            table.groupby(["score_status", "risk_category"]).size().items()},
        "combined_score_stats": {
            "min": float(table["combined_risk_score"].min()),
            "median": float(table["combined_risk_score"].median()),
            "max": float(table["combined_risk_score"].max()),
        },
    }


# ----------------------------------------------------------------- report ----
def build_report(table: pd.DataFrame, hashes_before: dict,
                 hashes_after: dict) -> str:
    s = summary_counts(table)
    L: list[str] = []
    add = L.append
    add("# PAIMANA AI - RISK SCORING REPORT (Phase 5)")
    add("")
    add(f"- generated (UTC): {datetime.now(timezone.utc).isoformat()}")
    add(f"- script: `ml/06_risk_scoring.py`  |  formula version: "
        f"`{FORMULA_VERSION}`")
    add("- output: `outputs/risk/project_risk_scores.csv`")
    add("")
    add("## 1. What this is (and is not)")
    add("")
    add("- **PROTOTYPE risk scoring** over a single **April 2026** snapshot.")
    add("- It is **NOT verified future prediction** and **NOT a validated "
        "early-warning rate** - Phase 4 established that a single snapshot "
        "cannot support temporal validation.")
    add("- The score reflects **modelled associations, not causation**: a High "
        "risk score does not mean any feature *causes* a cost or time overrun.")
    add("- Scores were produced by **loading the saved Phase-4 pipelines** "
        "(`joblib.load`). No model was retrained, replaced or tuned in this "
        "phase, and no Phase-4 result was modified.")
    add("- Inference runs with `n_jobs=1` (thread-serial tree summation) so "
        "repeated runs are byte-identical; this changes only in-memory "
        "parallelism, never the fitted parameters or the files on disk.")
    add("")
    add("## 2. Inputs and models")
    add("")
    add("| item | sha256 (before) | sha256 (after) | unchanged |")
    add("|---|---|---|---|")
    for name, h0 in hashes_before.items():
        h1 = hashes_after.get(name, "")
        add(f"| {name} | `{h0[:16]}...` | `{h1[:16]}...` | "
            f"{'YES' if h0 == h1 else '**NO**'} |")
    add("")
    add("| pipeline | estimator (from Phase 4) | input features (exact saved order) |")
    add("|---|---|---|")
    cost_meta = json.loads(COST_META.read_text(encoding="utf-8"))
    time_meta = json.loads(TIME_META.read_text(encoding="utf-8"))
    add(f"| `models/cost_overrun/pipeline.joblib` | "
        f"{cost_meta['selected_model_plan_only']['model']} "
        f"({cost_meta['primary_experiment']}) | "
        f"{cost_meta['feature_sets']['plan_only']} |")
    add(f"| `models/time_overrun/pipeline.joblib` | "
        f"{time_meta['selected_model_plan_only']['model']} "
        f"({time_meta['primary_experiment']}) | "
        f"{time_meta['feature_sets']['plan_only']} |")
    add("")
    add("## 3. Scoring formula")
    add("")
    add("```")
    add("both probabilities available :")
    add("    combined = (W_COST * cost_p + W_TIME * time_p) / (W_COST + W_TIME)")
    add(f"    with W_COST = {W_COST}, W_TIME = {W_TIME}   -> score_status 'complete'")
    add("only one available           :")
    add("    combined = the available probability")
    add("    -> score_status 'partial'; missing_component names what is absent;")
    add("       a missing probability is NEVER replaced with 0")
    add("neither available            : combined = NaN, score_status 'missing'")
    add("```")
    add("")
    add("## 4. Risk thresholds (configurable, prototype defaults)")
    add("")
    add("| category | condition |")
    add("|---|---|")
    add(f"| Low | `0 <= combined < {LOW_MAX}` |")
    add(f"| Medium | `{LOW_MAX} <= combined < {HIGH_MIN}` |")
    add(f"| High | `{HIGH_MIN} <= combined <= 1` |")
    add("| Unknown | combined is NaN |")
    add("")
    add("Rationale: the equal-weighted probability is centred on 0.5, so a "
        "symmetric middle band marks the uncertain zone and the outer thirds "
        "flag clearly above/below-average overrun probability. **These "
        "thresholds are NOT calibrated or validated** against outcomes "
        "(calibrating on this same single snapshot would overfit); they are "
        "configurable placeholders for a later phase.")
    add("")
    add("## 5. Eligibility and missing data")
    add("")
    add(f"- rows scored                 : {s['total_rows']}")
    add(f"- cost probability available  : {s['cost_probability_available']}")
    add(f"- time probability available  : {s['time_probability_available']} "
        "(only rows with a KNOWN time-overrun target)")
    add(f"- time label unknown (-1 rows): {s['time_label_unknown_rows']} - label "
        "preserved as -1, probability left empty, never treated as negative")
    add(f"- score_status counts         : {s['score_status']}")
    add(f"- missing_component counts    : {s['missing_component']}")
    add("")
    add("## 6. Summary counts by risk category")
    add("")
    add("| risk_category | projects | of which 'complete' | of which 'partial' |")
    add("|---|---|---|---|")
    for cat in ("Low", "Medium", "High", "Unknown"):
        n = s["risk_category"].get(cat, 0)
        if n == 0 and cat == "Unknown":
            continue
        comp = s["risk_category_by_status"].get(f"complete|{cat}", 0)
        part = s["risk_category_by_status"].get(f"partial|{cat}", 0)
        add(f"| {cat} | {n} | {comp} | {part} |")
    add("")
    cs = s["combined_score_stats"]
    add(f"combined score: min={cs['min']:.4f}, median={cs['median']:.4f}, "
        f"max={cs['max']:.4f}")
    add("")
    add("## 7. Data limitations")
    add("")
    add("- Single April 2026 snapshot: scores separate projects *within this "
        "snapshot* only; future-month performance is untested.")
    add("- `plan_only` probabilities come from Phase-4 models whose test PR-AUC "
        "was 0.61 (cost) and 0.97 (time); the cost model in particular still "
        "misclassifies many projects - treat individual scores as indicative.")
    add("- Time probability availability is defined by label knowledge (354 "
        "rows have no revised completion date); on truly new projects the same "
        "rule must be expressed as 'time model input unavailable'.")
    add("- Probabilities are uncalibrated classifier outputs used as scores.")
    add("- Association, not causation; no alerting thresholds were validated.")
    add("")
    return "\n".join(L)


# =================================================================== main ====
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 78)
    print("PAIMANA AI - PHASE 5 : PROTOTYPE RISK SCORING (April 2026 snapshot)")
    print("=" * 78)

    watched = {"original CSV": RAW_CSV, "cleaned CSV": CLEAN_CSV,
               "features CSV": FEATURES_CSV,
               "cost pipeline": COST_PIPELINE, "cost metadata": COST_META,
               "time pipeline": TIME_PIPELINE, "time metadata": TIME_META}
    hashes_before = {k: sha256_of(p) for k, p in watched.items()}
    for k, h in hashes_before.items():
        print(f"    sha256 {k:<15}: {h[:24]}...")

    print("\n[1] loading saved pipelines (joblib.load only - no retraining)")
    pipelines = load_pipelines()
    for name, pipe in pipelines.items():
        print(f"    {name}: {type(pipe).__name__} -> "
              f"{type(pipe.steps[-1][1]).__name__}")
        print(f"      input schema ({len(schema_of(pipe))}): {schema_of(pipe)}")

    print("\n[2] building project risk table")
    table = build_risk_table(pipelines=pipelines)
    print(f"    rows={len(table)}  columns={len(table.columns)}")
    s = summary_counts(table)
    print(f"    cost prob available : {s['cost_probability_available']}")
    print(f"    time prob available : {s['time_probability_available']} "
          f"(unknown label rows kept empty: {s['time_label_unknown_rows']})")
    print(f"    score_status        : {s['score_status']}")
    print(f"    risk_category       : {s['risk_category']}")

    print("\n[3] writing artifacts")
    table.to_csv(RESULTS_CSV, index=False)
    hashes_after = {k: sha256_of(p) for k, p in watched.items()}
    report = build_report(table, hashes_before, hashes_after)
    REPORT_MD.write_text(report, encoding="utf-8")
    print(f"    saved {RESULTS_CSV.relative_to(ROOT)} "
          f"({RESULTS_CSV.stat().st_size} bytes, {len(table)} rows)")
    print(f"    saved {REPORT_MD.relative_to(ROOT)} "
          f"({REPORT_MD.stat().st_size} bytes)")

    print("\n[4] integrity checks")
    ok = True
    for k in watched:
        same = hashes_before[k] == hashes_after[k]
        ok &= same
        print(f"    [{'PASS' if same else 'FAIL'}] {k} unchanged")
    assert ok, "an input file changed during scoring - aborting"
    assert RESULTS_CSV.exists() and REPORT_MD.exists()
    reread = pd.read_csv(RESULTS_CSV)
    assert len(reread) == len(table), "written CSV row count mismatch"
    print(f"    [PASS] results CSV re-read OK ({len(reread)} rows)")
    print("\nNOTE: prototype risk scoring on one snapshot - not verified future "
          "prediction;\n      scores reflect modelled associations, not causation.")
    print("=" * 78)


if __name__ == "__main__":
    main()





