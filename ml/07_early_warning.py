"""
PAIMANA AI - PHASE 6 : EXPLAINABLE EARLY-WARNING / DECISION-SUPPORT LAYER
=========================================================================
Scope   : ONLY the explainable early-warning layer. No retraining, no model
          artifact changes, no frontend/React/FastAPI/database/LLM/RAG/deploy.

WHAT IT IS
----------
"An explainable prototype early-warning and decision-support layer based on
 model-estimated project risk."  (single April 2026 snapshot - NOT a validated
 future forecasting system; explanations show model ASSOCIATIONS, never causes)

Inputs  : outputs/risk/project_risk_scores.csv          (Phase 5, read-only)
          outputs/models/feature_dictionary.csv         (feature meanings)
          models/{cost_overrun,time_overrun}/pipeline.joblib (loaded, never fit)
Outputs : outputs/risk/early_warning_results.csv
          outputs/risk/early_warning_report.md

STEP 2 - EARLY-WARNING LEVELS (thresholds REUSED from Phase 5 `06_risk_scoring`,
never silently changed - verified at runtime):
    Low     : risk score <  0.35      -> LOW     "No immediate model-based warning"
    Medium  : 0.35 <= score <  0.65   -> MEDIUM  "Monitor"
    High    : score >= 0.65           -> HIGH    "Priority monitoring"
    Missing score -> NOT_AVAILABLE (never assumed to be 0 / never "Low")

STEP 3 - WARNING TYPES (threshold 0.65 = Phase-5 HIGH_MIN):
    COST_WARNING                  cost_overrun_probability  >= 0.65
    TIME_WARNING                  time_overrun_probability  >= 0.65
    COMBINED_HIGH_RISK_WARNING    combined >= 0.65 AND both probabilities present
    MEDIUM_RISK_WARNING           0.35 <= combined < 0.65
    DATA_COMPLETENESS_WARNING     score not complete (missing/partial evidence)
    Missing probabilities are NEVER treated as zero risk.

STEP 5 - EXPLANATIONS: SHAP (shap TreeExplainer) on the actual plan-only model
inputs when available; otherwise sklearn permutation importance (global only).
Wording states "model-estimated risk" / "model-associated indicator" -
NEVER "X causes overrun".

Run : python ml/07_early_warning.py
Test: python -m unittest discover -s tests -v
"""

from __future__ import annotations

import hashlib
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RISK_CSV = ROOT / "outputs" / "risk" / "project_risk_scores.csv"
RISK_REPORT = ROOT / "outputs" / "risk" / "risk_scoring_report.md"
OUT_DIR = ROOT / "outputs" / "risk"
RESULTS_CSV = OUT_DIR / "early_warning_results.csv"
REPORT_MD = OUT_DIR / "early_warning_report.md"
FDICT_CSV = ROOT / "outputs" / "models" / "feature_dictionary.csv"
MOD06_PATH = ROOT / "ml" / "06_risk_scoring.py"

# --- warning thresholds (== Phase 5; loaded from 06 and asserted) -----------
COST_WARNING_MIN = 0.65
TIME_WARNING_MIN = 0.65

COST_WARNING = "COST_WARNING"
TIME_WARNING = "TIME_WARNING"
COMBINED_HIGH_RISK_WARNING = "COMBINED_HIGH_RISK_WARNING"
MEDIUM_RISK_WARNING = "MEDIUM_RISK_WARNING"
DATA_COMPLETENESS_WARNING = "DATA_COMPLETENESS_WARNING"
WARNING_ORDER = [COST_WARNING, TIME_WARNING, COMBINED_HIGH_RISK_WARNING,
                 MEDIUM_RISK_WARNING, DATA_COMPLETENESS_WARNING]

PRIORITY_LABELS = {
    "HIGH": "Priority monitoring",
    "MEDIUM": "Monitor",
    "LOW": "No immediate model-based warning",
    "NOT_AVAILABLE": "Not available - incomplete data, no risk assumed",
}

REQUIRED_RISK_COLUMNS = [
    "sl_no", "project_code", "project_name", "state", "agency", "report_month",
    "cost_overrun_probability", "time_overrun_probability",
    "combined_risk_score", "score_status", "risk_category",
    "cost_overrun_label", "time_overrun_label",
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_module(path: Path, name: str):
    """Import a digit-prefixed module file (e.g. 06_risk_scoring.py)."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Phase-5 thresholds: load and VERIFY they are unchanged (0.35 / 0.65).
rs06 = load_module(MOD06_PATH, "paimana_rs06")
LOW_MAX = rs06.LOW_MAX
HIGH_MIN = rs06.HIGH_MIN
assert LOW_MAX == 0.35 and HIGH_MIN == 0.65, \
    f"Phase-5 thresholds changed unexpectedly: {LOW_MAX}, {HIGH_MIN}"
assert COST_WARNING_MIN == HIGH_MIN and TIME_WARNING_MIN == HIGH_MIN, \
    "warning thresholds must match the Phase-5 High boundary"


def _has(x) -> bool:
    """True when a probability/score is actually available (not None/NaN)."""
    if x is None:
        return False
    try:
        return not pd.isna(x)
    except (TypeError, ValueError):
        return True


# -------------------------------------- STEP 2/3 : warning classification ----
def warning_types_for(cost_p, time_p, combined, score_status: str) -> list[str]:
    """Return the triggered warning types (fixed order) for one project.

    Pure function; missing values are never coerced to 0.
    """
    has_cost, has_time = _has(cost_p), _has(time_p)
    has_combined = _has(combined)
    both = has_cost and has_time

    types: list[str] = []
    if has_cost and float(cost_p) >= COST_WARNING_MIN:
        types.append(COST_WARNING)
    if has_time and float(time_p) >= TIME_WARNING_MIN:
        types.append(TIME_WARNING)
    if has_combined and both and float(combined) >= HIGH_MIN:
        types.append(COMBINED_HIGH_RISK_WARNING)
    if has_combined and LOW_MAX <= float(combined) < HIGH_MIN:
        types.append(MEDIUM_RISK_WARNING)
    if score_status != "complete" or not has_combined or not both:
        # not enough information for a COMPLETE risk score -> data warning
        types.append(DATA_COMPLETENESS_WARNING)
    return [t for t in WARNING_ORDER if t in types]


def priority_for(types: list[str], combined) -> str:
    """HIGH if any component/combined warning fired; MEDIUM for the medium
    band; NOT_AVAILABLE when there is no combined score (never 'Low');
    otherwise LOW.  Partial evidence keeps the score-based priority but the
    message flags incompleteness."""
    if any(t in (COST_WARNING, TIME_WARNING, COMBINED_HIGH_RISK_WARNING)
           for t in types):
        return "HIGH"
    if MEDIUM_RISK_WARNING in types:
        return "MEDIUM"
    if _has(combined):
        return "LOW"
    return "NOT_AVAILABLE"          # missing score -> NOT a false Low risk


def priority_label(priority: str) -> str:
    return PRIORITY_LABELS.get(priority, priority)


def risk_category_for(combined, score_status: str) -> str:
    """Re-derive (or verify) the Phase-5 category with the SAME thresholds."""
    if score_status != "complete" and not _has(combined):
        return "Unknown"
    if not _has(combined):
        return "Unknown"
    return rs06.risk_category(float(combined), LOW_MAX, HIGH_MIN)


# ------------------------------- STEP 4 : explanation / STEP 6 : actions -----
def warning_message(types: list[str], cost_p, time_p, combined,
                    score_status: str, missing_component: str) -> str:
    """Evidence-based explanation using actual model outputs. Wording states
    model-estimated risk - never causation, never a confirmed future event."""
    parts: list[str] = []
    partial = score_status != "complete" or not _has(combined)
    if partial and types:
        parts.append("Warning based on incomplete model evidence.")

    if COST_WARNING in types:
        parts.append(
            f"The model estimates elevated cost-overrun risk for this project "
            f"(model-estimated probability {float(cost_p):.2f}); this is a "
            f"MODEL-ESTIMATED RISK, not a confirmed future event.")
    if TIME_WARNING in types:
        parts.append(
            f"The model estimates elevated time-overrun risk for this project "
            f"(model-estimated probability {float(time_p):.2f}); this is a "
            f"MODEL-ESTIMATED RISK, not a confirmed future event.")
    if COMBINED_HIGH_RISK_WARNING in types:
        parts.append(
            f"The combined model risk score ({float(combined):.2f}) is in the "
            f"High band based on both cost and time model estimates; this is a "
            f"MODEL-ESTIMATED RISK, not a confirmed future event.")
    if MEDIUM_RISK_WARNING in types:
        parts.append(
            f"The combined model risk score ({float(combined):.2f}) is in the "
            f"Medium band; model-estimated risk is moderate - continue "
            f"monitoring.")
    if DATA_COMPLETENESS_WARNING in types:
        why = (missing_component if _has(missing_component)
               and missing_component not in ("none", "both")
               else (score_status if score_status != "complete"
                     else "incomplete model evidence"))
        parts.append(
            f"Incomplete information for a complete risk score "
            f"(missing: {why}); missing data is NOT scored as zero risk.")

    if not parts:
        parts.append(
            f"No immediate model-based warning (combined score "
            f"{float(combined):.2f} is below the Low/Medium boundary "
            f"{LOW_MAX}).")
    return " ".join(parts)


def recommended_action(types: list[str]) -> str:
    """Monitoring recommendations by warning type - not automatic government
    decisions, and no project-specific facts are invented."""
    cost, time = COST_WARNING in types, TIME_WARNING in types
    parts: list[str] = []
    if cost and time:
        parts.append("Prioritize project for detailed monitoring of both cost "
                     "and schedule.")
    elif cost:
        parts.append("Review project cost escalation status and expenditure "
                     "position.")
    elif time:
        parts.append("Review implementation schedule, milestone status and "
                     "completion timeline.")
    elif COMBINED_HIGH_RISK_WARNING in types:
        parts.append("Prioritize project for detailed monitoring of both cost "
                     "and schedule based on the combined model score.")
    elif MEDIUM_RISK_WARNING in types:
        parts.append("Continue regular monitoring and review upcoming "
                     "milestones.")
    else:
        parts.append("No immediate model-based warning; continue routine "
                     "periodic review.")
    if DATA_COMPLETENESS_WARNING in types:
        parts.append("Obtain/update missing project information before relying "
                     "on the complete risk score.")
    return " ".join(parts)


def risk_indicator_text(cost_p, time_p, combined, category: str,
                        top_indicators: str) -> str:
    """Compose the evidence string from ACTUAL model inputs/outputs."""
    bits = []
    bits.append("cost_p=" + (f"{float(cost_p):.3f}" if _has(cost_p) else "n/a"))
    bits.append("time_p=" + (f"{float(time_p):.3f}" if _has(time_p) else "n/a"))
    bits.append("combined=" + (f"{float(combined):.3f}" if _has(combined)
                               else "n/a"))
    bits.append(f"category={category}")
    if top_indicators:
        bits.append(f"top model-associated indicators (SHAP, not causal): "
                    f"{top_indicators}")
    return " | ".join(bits)


# --------------------------- STEP 5 : feature-based explanation --------------
def _group_index(name: str, feats: list[str]) -> int | None:
    """Map a transformed (one-hot) column back to its original feature."""
    if name in feats:
        return feats.index(name)
    for cat in ("agency", "state"):
        if name.startswith(cat + "_") and cat in feats:
            return feats.index(cat)
    return None


def _fmt_value(v) -> str:
    if isinstance(v, str):
        return v
    try:
        f = float(v)
        return f"{f:g}"
    except (TypeError, ValueError):
        return str(v)


def _top_indicators(row_idx: int, grouped: np.ndarray, feats: list[str],
                    df: pd.DataFrame, top_k: int = 2) -> str:
    """Top-k |SHAP| features for one row, with ACTUAL feature values."""
    vals = grouped[row_idx]
    order = np.argsort(-np.abs(vals))[:top_k]
    out = []
    for j in order:
        if vals[j] == 0 or not np.isfinite(vals[j]):
            continue
        sign = "+" if vals[j] >= 0 else "-"
        v = _fmt_value(df.iloc[row_idx][feats[j]])
        out.append(f"{feats[j]}={v} ({sign}{abs(vals[j]):.3f} "
                   f"{'raises' if vals[j] > 0 else 'lowers'} model estimate)")
    return "; ".join(out)


def _aligned_feature_frame(risk_df: pd.DataFrame) -> pd.DataFrame:
    """Plan-only feature values aligned row-for-row with the Phase-5 output.
    The risk CSV does not carry the raw feature columns, so they are read from
    the Phase-3 feature dataset and verified to be row-aligned via sl_no."""
    fdf = pd.read_csv(ROOT / "data" / "processed" / "paimana_features.csv")
    assert len(fdf) == len(risk_df), "features/risk row-count mismatch"
    if "sl_no" in risk_df.columns and "sl_no" in fdf.columns:
        assert (fdf["sl_no"].to_numpy() == risk_df["sl_no"].to_numpy()).all(), \
            "features CSV is not row-aligned with the Phase-5 risk output"
    return fdf


def compute_explanations(df: pd.DataFrame) -> dict:
    """SHAP TreeExplainer on the actual plan-only model inputs (tree models).
    Fallback: sklearn permutation importance (global only).
    NOTHING here is fabricated; method and scale are reported honestly."""
    result = {"method": "unavailable", "scale_note": "", "global": {},
              "cost_top": [""] * len(df), "time_top": [""] * len(df)}
    try:
        import shap  # available in this environment: 0.52.0
    except Exception:
        result["method"] = "shap_unavailable"
        return _permutation_fallback(df, result)

    try:
        X_df = _aligned_feature_frame(df)     # raw plan features, row-aligned
        pipes = rs06.load_pipelines()          # load only, never fit
        grouped_all: dict[str, np.ndarray] = {}
        scale_note = []
        for key, out_key in (("cost_overrun", "cost_top"),
                             ("time_overrun", "time_top")):
            pipe = pipes[key]
            feats = list(pipe.feature_names_in_)
            pre, model = pipe.named_steps["preprocess"], pipe.named_steps["model"]
            Xt = pre.transform(X_df[feats])
            names = list(pre.get_feature_names_out())
            sv = shap.TreeExplainer(model).shap_values(Xt)
            if isinstance(sv, list):
                arr = np.asarray(sv[1])                       # class 1
                scale_note.append(f"{key}: class-1 probability scale")
            else:
                arr = np.asarray(sv)
                if arr.ndim == 3:
                    arr = arr[..., 1] if arr.shape[-1] == 2 else arr[..., 0]
                    scale_note.append(f"{key}: class-1 probability scale")
                else:
                    scale_note.append(
                        f"{key}: raw margin (log-odds) scale")
            grouped = np.zeros((len(df), len(feats)), dtype="float64")
            for j, nm in enumerate(names):
                g = _group_index(nm, feats)
                if g is not None:
                    grouped[:, g] += arr[:, j]
            grouped_all[key] = grouped
            result[out_key] = [
                _top_indicators(i, grouped, feats, X_df)
                for i in range(len(df))]
        result["method"] = "shap_tree_explainer"
        result["scale_note"] = "; ".join(scale_note)
        result["global"] = {
            key: {list(pipes[key].feature_names_in_)[j]:
                  float(np.mean(np.abs(grouped[:, j])))
                  for j in range(grouped.shape[1])}
            for key, grouped in grouped_all.items()}
        return result
    except Exception as exc:                    # honest fallback, never fake
        result["method"] = f"shap_failed_fallback ({type(exc).__name__}: {exc})"
        return _permutation_fallback(df, result)


def _permutation_fallback(df: pd.DataFrame, result: dict) -> dict:
    """Global-only, defensible alternative: sklearn permutation importance."""
    try:
        from sklearn.inspection import permutation_importance
        X_df = _aligned_feature_frame(df)      # raw plan features, row-aligned
        pipes = rs06.load_pipelines()
        label_of = {"cost_overrun": "cost_overrun_label",
                    "time_overrun": "time_overrun_label"}
        rng = np.random.RandomState(42)
        n = min(600, len(df))
        sample = rng.choice(len(df), size=n, replace=False)
        for key in ("cost_overrun", "time_overrun"):
            pipe = pipes[key]
            feats = list(pipe.feature_names_in_)
            y = df[label_of[key]].to_numpy()[sample]
            mask = y != -1
            Xs = X_df[feats].iloc[sample][mask]
            ys = y[mask]
            if len(np.unique(ys)) < 2:
                continue
            r = permutation_importance(pipe, Xs, ys, n_repeats=5,
                                       random_state=42, scoring="roc_auc")
            result["global"][key] = {
                f: float(m) for f, m in zip(feats, r.importances_mean)}
        result["method"] = (result["method"] if result["method"] != "unavailable"
                            else "sklearn_permutation_importance")
        result["scale_note"] = ("permutation importance on ROC-AUC (global "
                                "only, no per-row attribution)")
    except Exception:
        result["method"] = "unavailable"
        result["scale_note"] = "no explanation method available"
    return result


# ------------------------------------------------------- table assembly -----
NEW_COLUMNS = ["warning_type", "warning_priority", "warning_priority_label",
               "warning_message", "risk_indicators", "recommended_action",
               "explanation_method"]


def assemble_results(risk_df: pd.DataFrame, explanations: dict | None = None
                     ) -> pd.DataFrame:
    """Build the Phase-6 output: ALL Phase-5 columns preserved + warning cols.

    `explanations` is injectable (tests pass None -> indicators without SHAP
    attribution); production passes compute_explanations()."""
    missing = [c for c in REQUIRED_RISK_COLUMNS if c not in risk_df.columns]
    assert not missing, f"Phase-5 risk output missing columns: {missing}"
    if explanations is None:
        explanations = {"method": "none_provided", "scale_note": "",
                        "global": {}, "cost_top": [""] * len(risk_df),
                        "time_top": [""] * len(risk_df)}
    ex_cost = explanations.get("cost_top", [""] * len(risk_df))
    ex_time = explanations.get("time_top", [""] * len(risk_df))
    method = explanations.get("method", "unknown")

    rows = []
    for i in range(len(risk_df)):
        r = risk_df.iloc[i]
        cost_p = r["cost_overrun_probability"]
        time_p = r["time_overrun_probability"]
        combined = r["combined_risk_score"]
        status = str(r["score_status"])
        missing_comp = str(r.get("missing_component", ""))

        types = warning_types_for(cost_p, time_p, combined, status)
        prio = priority_for(types, combined if _has(combined) else None)
        category = risk_category_for(
            combined if _has(combined) else None, status)

        top_parts = []
        if i < len(ex_cost) and ex_cost[i]:
            top_parts.append(f"cost model: {ex_cost[i]}")
        if i < len(ex_time) and ex_time[i]:
            top_parts.append(f"time model: {ex_time[i]}")
        top = " || ".join(top_parts)
        rows.append({
            "warning_type": "|".join(types) if types else "NONE",
            "warning_priority": prio,
            "warning_priority_label": priority_label(prio),
            "warning_message": warning_message(types, cost_p, time_p,
                                               combined, status, missing_comp),
            "risk_indicators": risk_indicator_text(cost_p, time_p, combined,
                                                   category, top),
            "recommended_action": recommended_action(types),
            "explanation_method": method,
        })
    out = risk_df.copy()                     # never drop existing risk info
    new_cols = pd.DataFrame(rows, index=risk_df.index)
    for c in NEW_COLUMNS:
        out[c] = new_cols[c]

    # category must remain identical to the Phase-5 column (same thresholds)
    mismatch = (out["risk_category"] != risk_df["risk_category"])
    assert not mismatch.any(), \
        f"risk_category changed for {int(mismatch.sum())} rows - thresholds drifted"
    # missing probabilities must never be silently zero-filled by this phase
    na_time = risk_df["time_overrun_probability"].isna()
    assert out.loc[na_time, "risk_indicators"].str.contains("time_p=n/a").all()
    return out


# -------------------------------------------------------- report (STEP 9) ----
def build_report(out: pd.DataFrame, explanations: dict,
                 hashes_before: dict, hashes_after: dict) -> str:
    n = len(out)
    prio_counts = out["warning_priority"].value_counts().to_dict()

    def count_type(t: str) -> int:
        return int(out["warning_type"].str.split("|").apply(
            lambda xs: t in xs).sum())

    n_cost = count_type(COST_WARNING)
    n_time = count_type(TIME_WARNING)
    n_comb = count_type(COMBINED_HIGH_RISK_WARNING)
    n_med = count_type(MEDIUM_RISK_WARNING)
    n_data = count_type(DATA_COMPLETENESS_WARNING)
    n_partial = int((out["score_status"] == "partial").sum())
    n_missing = int((out["score_status"] == "missing").sum())

    L: list[str] = []
    add = L.append
    add("# PAIMANA AI - EXPLAINABLE EARLY-WARNING REPORT (Phase 6)")
    add("")
    add(f"- generated (UTC): {datetime.now(timezone.utc).isoformat()}")
    add("- **This is an explainable prototype early-warning and "
        "decision-support layer based on model-estimated project risk.**")
    add("- Single April 2026 reporting snapshot - NOT a validated future "
        "forecasting system. Future historical monthly snapshots can later be "
        "used for temporal validation.")
    add("- Output: `outputs/risk/early_warning_results.csv` "
        f"({n} rows, {out.shape[1]} columns)")
    add("")
    add("## 1. Projects analyzed")
    add("")
    add(f"- **{n} projects** (all rows of the Phase-5 risk output)")
    add("")
    add("## 2-4. Warning counts by priority (actual values)")
    add("")
    add("| priority | label | projects |")
    add("|---|---|---|")
    for p in ("HIGH", "MEDIUM", "LOW", "NOT_AVAILABLE"):
        if p in prio_counts:
            add(f"| {p} | {PRIORITY_LABELS[p]} | {prio_counts[p]} |")
    add("")
    add(f"- **HIGH warnings (Priority monitoring): {prio_counts.get('HIGH', 0)}**")
    add(f"- **MEDIUM warnings (Monitor): {prio_counts.get('MEDIUM', 0)}**")
    add(f"- **LOW / no immediate warning: {prio_counts.get('LOW', 0)}**")
    add(f"- NOT_AVAILABLE (no score, no assumed risk): "
        f"{prio_counts.get('NOT_AVAILABLE', 0)}")
    add("")
    add("## 5. Partial / incomplete scores")
    add("")
    add(f"- score_status = partial : {n_partial}")
    add(f"- score_status = missing  : {n_missing}")
    add(f"- rows with DATA_COMPLETENESS_WARNING : {n_data}")
    add("- Missing probabilities are reported as `n/a` and are **never "
        "treated as zero risk**.")
    add("")
    add("## 6-8. Warning type counts (actual values)")
    add("")
    add("| warning type | projects |")
    add("|---|---|")
    add(f"| COST_WARNING (cost_p >= {COST_WARNING_MIN}) | {n_cost} |")
    add(f"| TIME_WARNING (time_p >= {TIME_WARNING_MIN}) | {n_time} |")
    add(f"| COMBINED_HIGH_RISK_WARNING (combined >= {HIGH_MIN}, both present) "
        f"| {n_comb} |")
    add(f"| MEDIUM_RISK_WARNING ({LOW_MAX} <= combined < {HIGH_MIN}) | {n_med} |")
    add(f"| DATA_COMPLETENESS_WARNING | {n_data} |")
    add("")

    add("## 9. Warning logic")
    add("")
    add("- Thresholds are **reused unchanged from Phase 5** "
        f"(`06_risk_scoring`): Low < {LOW_MAX} <= Medium < {HIGH_MIN} <= High; "
        "verified by runtime assertion.")
    add("- Priority: HIGH if COST/TIME/COMBINED warning fired; else MEDIUM for "
        "the medium band; else LOW when a combined score exists; "
        "**NOT_AVAILABLE when no score exists (never reported as Low)**.")
    add("- Partial scores keep their score-based priority but every message is "
        "prefixed with \"Warning based on incomplete model evidence.\"")
    add(f"- COMBINED_HIGH_RISK_WARNING additionally requires BOTH probabilities; "
        f"COST/TIME warnings trigger at >= {COST_WARNING_MIN}.")
    add("- Missing probabilities are never treated as zero risk.")
    add("")
    add("## 10. Explanation methodology")
    add("")
    add(f"- method: **{explanations.get('method', 'unknown')}**")
    add(f"- scale: {explanations.get('scale_note', 'n/a')}")
    add("- Per-project `risk_indicators` list actual model outputs "
        "(cost_p, time_p, combined, category) plus the top model-associated "
        "plan features with actual values and signed contributions.")
    add("- Wording rules: \"the model estimates elevated risk\" / "
        "\"model-associated indicator\" - NEVER \"X causes overrun\", and every "
        "high probability is labelled a MODEL-ESTIMATED RISK, not a confirmed "
        "future event.")
    g = explanations.get("global", {})
    if g:
        add("- Global model-associated feature strength "
            "(mean |attribution|, association not causation):")
        for key, per in g.items():
            ranked = sorted(per.items(), key=lambda kv: -kv[1])[:7]
            add(f"  - **{key}**: " + ", ".join(
                f"{f}={v:.4f}" for f, v in ranked))
    add("- Feature meanings come from `outputs/models/feature_dictionary.csv`; "
        "feature allowances from `outputs/models/leakage_review.md`.")
    add("")
    add("## 11. Limitations")
    add("")
    add("- Single April 2026 snapshot: warnings separate projects within this "
        "snapshot only; they do NOT forecast the future.")
    add("- Underlying Phase-4 models: plan-only PR-AUC 0.61 (cost) / 0.97 "
        "(time) on the same snapshot - individual scores are indicative.")
    add("- Uncalibrated probabilities used as scores; thresholds (0.35/0.65 and "
        "the 0.65 warning triggers) are unvalidated prototype defaults.")
    add("- Recommendations are **monitoring suggestions, not automatic "
        "government decisions**; no project-specific facts are invented.")
    add("- Association, not causation: attribution shows what the model "
        "relied on, not what causes overruns.")
    add("- 354 rows lack a time-overrun probability (unknown label); their "
        "warnings rest on cost evidence only and are flagged as incomplete.")
    add("")
    add("## Data integrity (inputs unchanged by this phase)")
    add("")
    add("| file | sha256 before | unchanged |")
    add("|---|---|---|")
    for k, h in hashes_before.items():
        ok = hashes_after.get(k) == h
        add(f"| {k} | `{h[:16]}...` | {'YES' if ok else '**NO**'} |")
    add("")
    return "\n".join(L)


# =================================================================== main ====
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 78)
    print("PAIMANA AI - PHASE 6 : EXPLAINABLE EARLY-WARNING LAYER")
    print("=" * 78)

    watched = {
        "original CSV": ROOT / "PAIMANA_April_2026_Dataset.csv",
        "cleaned CSV": ROOT / "data" / "processed" / "paimana_clean.csv",
        "features CSV": ROOT / "data" / "processed" / "paimana_features.csv",
        "cost model": ROOT / "models" / "cost_overrun" / "pipeline.joblib",
        "time model": ROOT / "models" / "time_overrun" / "pipeline.joblib",
        "phase5 risk output": RISK_CSV,
        "phase5 risk report": RISK_REPORT,
    }
    hashes_before = {k: sha256_of(p) for k, p in watched.items()}
    for k, h in hashes_before.items():
        print(f"    sha256 {k:<20}: {h[:24]}...")

    # STEP 1 - inspect actual Phase-5 columns before writing new code
    print("\n[STEP 1] loading Phase 5 risk output")
    assert RISK_CSV.exists(), f"missing {RISK_CSV}"
    risk_df = pd.read_csv(RISK_CSV)
    missing = [c for c in REQUIRED_RISK_COLUMNS if c not in risk_df.columns]
    assert not missing, f"missing expected Phase-5 columns: {missing}"
    print(f"    shape: {risk_df.shape}")
    print(f"    columns: {list(risk_df.columns)}")
    print(f"    score_status: {risk_df['score_status'].value_counts().to_dict()}")
    print(f"    thresholds reused from 06: LOW_MAX={LOW_MAX} HIGH_MIN={HIGH_MIN}")

    # STEP 5 - explanations (SHAP on actual model inputs; honest fallback)
    print("\n[STEP 5] computing model explanations (SHAP TreeExplainer)")
    explanations = compute_explanations(risk_df)
    print(f"    method : {explanations['method']}")
    print(f"    scale  : {explanations['scale_note']}")

    # STEPS 2/3/4/6/8 - warnings, priorities, messages, actions, output
    print("\n[STEPS 2-4, 6, 8] assembling early-warning results")
    out = assemble_results(risk_df, explanations)
    print(f"    rows={len(out)} columns={len(out.columns)}")
    print(f"    priority counts : "
          f"{out['warning_priority'].value_counts().to_dict()}")
    for t in WARNING_ORDER:
        c = int(out['warning_type'].str.split('|').apply(lambda x: t in x).sum())
        print(f"    {t:<30}: {c}")

    # STEP 7 - save + STEP 9 report + STEP 11 integrity
    print("\n[STEP 7/9] writing outputs")
    out.to_csv(RESULTS_CSV, index=False)
    hashes_after = {k: sha256_of(p) for k, p in watched.items()}
    report = build_report(out, explanations, hashes_before, hashes_after)
    REPORT_MD.write_text(report, encoding="utf-8")
    print(f"    saved {RESULTS_CSV.relative_to(ROOT)} "
          f"({RESULTS_CSV.stat().st_size} bytes, {len(out)} rows)")
    print(f"    saved {REPORT_MD.relative_to(ROOT)} "
          f"({REPORT_MD.stat().st_size} bytes)")

    print("\n[STEP 11] data integrity")
    ok = True
    for k in watched:
        same = hashes_before[k] == hashes_after[k]
        ok &= same
        print(f"    [{'PASS' if same else 'FAIL'}] {k} unchanged")
    assert ok, "an input file was modified - aborting"
    reread = pd.read_csv(RESULTS_CSV)
    assert len(reread) == len(out)
    assert all(c in reread.columns for c in NEW_COLUMNS)
    print(f"    [PASS] results CSV re-read OK ({len(reread)} rows, "
          f"{len(reread.columns)} columns)")
    print("\nNOTE: explainable prototype early-warning and decision-support "
          "layer based\n      on model-estimated project risk - single April "
          "2026 snapshot, not a\n      validated future forecasting system.")
    print("=" * 78)


if __name__ == "__main__":
    main()







