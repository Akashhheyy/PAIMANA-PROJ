"""
PAIMANA AI - PHASE 4 (TRAIN + EVALUATE THE TWO INDEPENDENT MODELS)
==================================================================
Project : PAIMANA AI - Predictive Infrastructure Risk Monitoring and Early Warning System
Scope   : TWO independent binary classifiers only:
              1. cost overrun   2. time overrun
          NO risk-scoring engine, alerts, frontend, backend, database,
          dashboard, LLM, RAG or deployment.

Reads   : data/processed/paimana_features.csv   (from ml/03_feature_engineering.py)
          outputs/models/feature_dictionary.csv
          outputs/models/leakage_review.md  (feature allowances)
Saves   : models/cost_overrun/{pipeline.joblib, pipeline_current_status.joblib, metadata.json}
          models/time_overrun/{pipeline.joblib, pipeline_current_status.joblib, metadata.json}
          outputs/models/cost_overrun_model_comparison.csv
          outputs/models/time_overrun_model_comparison.csv
          outputs/models/cost_overrun_report.md
          outputs/models/time_overrun_report.md

TARGETS
  cost_overrun_label : 1 if revised_cost_crore > original_cost_crore, 0 if <=,
                       -1 unknown (excluded from training)
  time_overrun_label : 1 if revised_doc > target_doc, 0 if <=,
                       -1 unknown (excluded from training)

EXPERIMENTS (per target, same held-out test rows for all classifiers)
  plan_only       -> PRIMARY. Features fixed at sanction time (early-warning
                     oriented; see outputs/models/leakage_review.md).
  current_status  -> SEPARATE & LABELLED. Adds April-2026 status fields.
                     A current-status classifier - NOT genuine early prediction.

SELECTION CRITERION (not accuracy): highest PR-AUC (average precision) on the
shared held-out test set, tie-break F1; a selection is only declared "valid"
if it beats the DummyClassifier baseline PR-AUC. Hyper-parameters are fixed a
priori; the test set is never used for tuning.

Run:  python ml/04_train_models.py
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score,
                             confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
ML_DIR = ROOT / "ml"
FEATURES_CSV = ROOT / "data" / "processed" / "paimana_features.csv"
DICT_CSV = ROOT / "outputs" / "models" / "feature_dictionary.csv"
OUT_DIR = ROOT / "outputs" / "models"
RAW_CSV = ROOT / "PAIMANA_April_2026_Dataset.csv"
CLEAN_CSV = ROOT / "data" / "processed" / "paimana_clean.csv"

RANDOM_SEED = 42
TEST_SIZE = 0.20
np.random.seed(RANDOM_SEED)

# Integrity anchors (verified before AND after training).
EXPECTED_RAW_SHA = "708a2fd905256878e6dc697fec366c71d126f06c5bd9119f2ca1cbd2fd2b93af"
EXPECTED_CLEAN_SHA = "a7f330ac31d3939f6006e45e36de516ba381adf15831a154b6a5fb10cc06206b"

TARGETS = {
    "cost_overrun": {
        "label": "cost_overrun_label",
        "definition": "1 if revised_cost_crore > original_cost_crore; 0 if <=; "
                      "-1 (unknown, excluded) if either cost missing/invalid "
                      "(NaN or <= 0).",
    },
    "time_overrun": {
        "label": "time_overrun_label",
        "definition": "1 if revised_doc > target_doc; 0 if <=; -1 (unknown, "
                      "excluded) if either date missing/invalid. Unknown is "
                      "never treated as 0.",
    },
}

# Columns forbidden as INPUT features for either model (labels, outcome
# columns, identifiers, constants, free text).
FORBIDDEN_FOR_BOTH = {
    "cost_overrun_label", "time_overrun_label",
    "revised_cost_crore", "revised_doc",
    "sl_no", "project_code", "legacy_ocms_code", "pmgid",
    "project_name", "report_month",
}


def sha256_of(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Re-use the EXACT feature definitions from step 03 (single source of truth).
def load_feature_module():
    spec = importlib.util.spec_from_file_location(
        "paimana_fe03", ML_DIR / "03_feature_engineering.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fe03 = load_feature_module()
PLAN_FEATURES = list(fe03.PLAN_FEATURES)
STATUS_FEATURES = list(fe03.STATUS_FEATURES)
CATEGORICAL_FEATURES = list(fe03.CATEGORICAL_FEATURES)

# ------------------------------------------------------------ leakage guard --
def forbidden_for(target: str) -> set[str]:
    """Forbidden input columns for one target (fail-fast if any appears)."""
    extra = {"revised_cost_crore"} if target == "cost_overrun" else set()
    return FORBIDDEN_FOR_BOTH | extra


def assert_features_allowed(features: list[str], target: str,
                             dictionary: pd.DataFrame) -> None:
    """Raise AssertionError if a forbidden/leakage feature enters a model."""
    forbidden = forbidden_for(target)
    bad = set(features) & forbidden
    assert not bad, f"LEAKAGE: {target} got forbidden raw columns {sorted(bad)}"

    # No feature name may reference the outcome columns or any label.
    named = [f for f in features
             if "revised" in f.lower() or f.endswith("_label")]
    assert not named, f"LEAKAGE: {target} got outcome-derived features {named}"

    # The feature dictionary records each feature's SOURCE columns; no source
    # may be an outcome column (covers derived features like expenditure_ratio).
    src = dictionary.set_index("feature")["source_columns"].to_dict()
    bad_src = [f for f in features
               if "revised" in str(src.get(f, "")).lower()]
    assert not bad_src, (
        f"LEAKAGE: {target} features derived from outcome columns {bad_src}")

    # Identifiers / constants / free text must never be present.
    ident = [f for f in features if f in FORBIDDEN_FOR_BOTH]
    assert not ident, f"LEAKAGE: identifier/constant columns present {ident}"


# -------------------------------------------------------------- pipeline -----
def build_preprocessor(features: list[str]) -> ColumnTransformer:
    """Dense output everywhere => compatible with HistGradientBoosting.
    Imputation/scaling fitted on TRAINING data only (inside the pipeline)."""
    num = [f for f in features if f not in CATEGORICAL_FEATURES]
    cat = [f for f in features if f in CATEGORICAL_FEATURES]
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler())])
    categorical = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="infrequent_if_exist",
                                 min_frequency=10,   # rare states/agencies grouped
                                 sparse_output=False)),
    ])
    return ColumnTransformer(
        [("num", numeric, num), ("cat", categorical, cat)],
        remainder="drop", verbose_feature_names_out=False)


HGB_SUPPORTS_CLASS_WEIGHT = "class_weight" in inspect.signature(
    HistGradientBoostingClassifier).parameters


def make_estimators() -> list[tuple[str, object]]:
    """Four classifiers, hyper-parameters fixed a priori (NO test-set tuning)."""
    hgb_kwargs: dict = {"random_state": RANDOM_SEED, "max_iter": 300,
                        "learning_rate": 0.08, "max_leaf_nodes": 31,
                        "l2_regularization": 0.1}
    if HGB_SUPPORTS_CLASS_WEIGHT:
        hgb_kwargs["class_weight"] = "balanced"
    return [
        ("dummy_baseline", DummyClassifier(strategy="prior")),
        ("logistic_regression",
         LogisticRegression(max_iter=2000, class_weight="balanced",
                            random_state=RANDOM_SEED)),
        ("random_forest",
         RandomForestClassifier(n_estimators=400, min_samples_leaf=2,
                                class_weight="balanced_subsample",
                                random_state=RANDOM_SEED, n_jobs=-1)),
        ("hist_gradient_boosting",
         HistGradientBoostingClassifier(**hgb_kwargs)),
    ]


def fit_pipeline(pipe: Pipeline, X: pd.DataFrame, y: pd.Series) -> Pipeline:
    """Fit; if this sklearn build lacks HistGB class_weight, emulate it with
    balanced sample weights instead (documented fallback)."""
    last = pipe.steps[-1][0]
    if last == "model" and not HGB_SUPPORTS_CLASS_WEIGHT and \
            isinstance(pipe.named_steps["model"], HistGradientBoostingClassifier):
        n = len(y); n1 = int((y == 1).sum()); n0 = int((y == 0).sum())
        w = np.where(y.to_numpy() == 1, n / (2 * max(n1, 1)), n / (2 * max(n0, 1)))
        return pipe.fit(X, y, model__sample_weight=w)
    return pipe.fit(X, y)


# -------------------------------------------------------------- metrics ------
def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                    y_proba: np.ndarray | None) -> dict:
    m = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
    }
    classes = np.unique(y_true)
    if y_proba is not None and len(classes) == 2:
        m["roc_auc"] = float(roc_auc_score(y_true, y_proba))
        m["pr_auc"] = float(average_precision_score(y_true, y_proba))
    else:
        m["roc_auc"] = None   # not calculable without both classes
        m["pr_auc"] = None
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    m["confusion_matrix"] = {"tn": int(tn), "fp": int(fp),
                             "fn": int(fn), "tp": int(tp)}
    return m


def positive_proba(pipe: Pipeline, X: pd.DataFrame) -> np.ndarray | None:
    try:
        proba = pipe.predict_proba(X)
    except AttributeError:
        return None
    idx = list(pipe.classes_).index(1) if 1 in list(pipe.classes_) else None
    return None if idx is None else proba[:, idx]


# ------------------------------------------------------------- experiments ---
def run_experiment(df: pd.DataFrame, label_col: str, target: str,
                   features: list[str], experiment: str,
                   train_idx: np.ndarray, test_idx: np.ndarray,
                   dictionary: pd.DataFrame) -> tuple[list[dict], dict]:
    """Train all four classifiers for one experiment of one target.
    Same held-out test rows for every classifier. Errors are recorded, never
    fabricated: a failing model gets status=FAILED and training continues."""
    assert_features_allowed(features, target, dictionary)

    X_all = df[features]                     # feature matrix (asserted clean)
    assert set(X_all.columns).isdisjoint(forbidden_for(target) |
                                         FORBIDDEN_FOR_BOTH), \
        "forbidden column entered the feature matrix"
    y_all = df[label_col]
    X_train, X_test = X_all.iloc[train_idx], X_all.iloc[test_idx]
    y_train, y_test = y_all.iloc[train_idx], y_all.iloc[test_idx]

    rows: list[dict] = []
    fitted: dict[str, Pipeline] = {}
    base = {
        "target": target, "experiment": experiment,
        "n_eligible": int(len(df)), "train_n": int(len(train_idx)),
        "test_n": int(len(test_idx)),
        "train_pos": int((y_train == 1).sum()), "train_neg": int((y_train == 0).sum()),
        "test_pos": int((y_test == 1).sum()), "test_neg": int((y_test == 0).sum()),
    }
    for name, est in make_estimators():
        pipe = Pipeline([("preprocess", build_preprocessor(features)),
                         ("model", est)])
        row = {**base, "model": name, "status": "OK", "error": ""}
        try:
            fit_pipeline(pipe, X_train, y_train)
            pred = pipe.predict(X_test)
            proba = positive_proba(pipe, X_test)
            row.update(compute_metrics(y_test.to_numpy(), np.asarray(pred), proba))
            fitted[name] = pipe
        except Exception as exc:                # genuine issue -> record & go on
            row["status"] = "FAILED"
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"    [FAILED] {target}/{experiment}/{name}: {row['error']}")
            traceback.print_exc()
        rows.append(row)
    return rows, {"fitted": fitted, "X_test": X_test, "y_test": y_test,
                  "features": features}


def select_best(rows: list[dict]) -> dict | None:
    """Criterion: max PR-AUC, tie-break max F1 (never accuracy alone)."""
    ok = [r for r in rows if r.get("status") == "OK" and r.get("pr_auc") is not None]
    if not ok:
        ok = [r for r in rows if r.get("status") == "OK"]   # fall back to F1
        if not ok:
            return None
        return max(ok, key=lambda r: r["f1"])
    return max(ok, key=lambda r: (r["pr_auc"], r["f1"]))


def beats_baseline(best: dict | None, rows: list[dict]) -> tuple[bool, float]:
    """True if best PR-AUC exceeds the dummy baseline PR-AUC by > 0.01."""
    if best is None or best.get("pr_auc") is None:
        return False, float("nan")
    dummy = next((r for r in rows if r["model"] == "dummy_baseline"
                  and r.get("status") == "OK"), None)
    if dummy is None or dummy.get("pr_auc") is None:
        return False, float("nan")
    delta = best["pr_auc"] - dummy["pr_auc"]
    return bool(delta > 0.01), float(delta)


def comparison_frame(rows: list[dict]) -> pd.DataFrame:
    cols = ["target", "experiment", "model", "status", "n_eligible", "train_n",
            "test_n", "train_pos", "train_neg", "test_pos", "test_neg",
            "accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc",
            "error"]
    out = []
    for r in rows:
        flat = {c: r.get(c, "") for c in cols}
        cm = r.get("confusion_matrix")
        if isinstance(cm, dict):
            flat.update({f"cm_{k}": v for k, v in cm.items()})
        else:
            flat.update({"cm_tn": "", "cm_fp": "", "cm_fn": "", "cm_tp": ""})
        out.append(flat)
    df = pd.DataFrame(out)
    return df[[c for c in df.columns if c in cols] +
              ["cm_tn", "cm_fp", "cm_fn", "cm_tp"]]


# ---------------------------------------------------------------- reports ----
def fmt(v) -> str:
    if v is None or v == "":
        return "n/a"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def build_report_md(target: str, info: dict, rows: list[dict],
                    best_plan: dict | None, best_status: dict | None,
                    plan_ok: bool, plan_delta: float) -> str:
    L: list[str] = []
    add = L.append
    add(f"# PAIMANA AI - {target.replace('_', ' ').upper()} MODEL REPORT")
    add("")
    add(f"- generated (UTC): {datetime.now(timezone.utc).isoformat()}")
    add(f"- script: `ml/04_train_models.py`  |  random seed: **{RANDOM_SEED}**  |  "
        f"test size: **{TEST_SIZE:.0%}** (stratified, shared by all classifiers)")
    add(f"- data: `data/processed/paimana_features.csv` (sha256 "
        f"`{info['features_sha']}`)")
    add("")
    add("## 1. Target definition")
    add("")
    add(f"`{TARGETS[target]['label']}`: {TARGETS[target]['definition']}")
    add("")
    add("## 2. Sample counts and split")
    add("")
    add("| | count | positive (1) | negative (0) |")
    add("|---|---|---|---|")
    add(f"| eligible rows | {info['n_eligible']} | {info['pos']} | {info['neg']} |")
    add(f"| excluded (unknown = -1) | {info['n_unknown']} | - | - |")
    add(f"| train | {info['train_n']} | {info['train_pos']} | {info['train_neg']} |")
    add(f"| test | {info['test_n']} | {info['test_pos']} | {info['test_neg']} |")
    add("")
    add("## 3. Feature sets and leakage controls")
    add("")
    add(f"- **plan_only (PRIMARY, early-warning oriented)**: {PLAN_FEATURES}")
    add(f"- **current_status (SEPARATE, clearly labelled)**: plan_only + "
        f"{[f for f in STATUS_FEATURES if f not in PLAN_FEATURES]}")
    add(f"- Forbidden for this model (asserted at runtime): "
        f"{sorted(forbidden_for(target))}")
    add("- Feature allowances follow `outputs/models/leakage_review.md`.")
    add("- Current-status results describe a **current-status classifier** and "
        "are **not** evidence of genuine early prediction.")
    add("")
    add("## 4. Model comparison (held-out test set, same rows for all models)")
    for exp in ("plan_only", "current_status"):
        exp_rows = [r for r in rows if r["experiment"] == exp]
        if not exp_rows:
            continue
        add("")
        add(f"### Experiment: `{exp}`" + (" (primary)" if exp == "plan_only"
                                          else " (separate status experiment)"))
        add("")
        add("| MODEL | STATUS | ACCURACY | PRECISION | RECALL | F1 | ROC-AUC | "
            "PR-AUC | CM (tn/fp/fn/tp) |")
        add("|---|---|---|---|---|---|---|---|---|")
        for r in exp_rows:
            cm = r.get("confusion_matrix") or {}
            cms = (f"{cm.get('tn')}/{cm.get('fp')}/{cm.get('fn')}/{cm.get('tp')}"
                   if cm else "n/a")
            add(f"| {r['model']} | {r['status']} | {fmt(r.get('accuracy'))} | "
                f"{fmt(r.get('precision'))} | {fmt(r.get('recall'))} | "
                f"{fmt(r.get('f1'))} | {fmt(r.get('roc_auc'))} | "
                f"{fmt(r.get('pr_auc'))} | {cms} |")
    add("")
    add("> Baseline = `dummy_baseline` (predicts the training prior; PR-AUC "
        "equals test prevalence, ROC-AUC 0.5 by construction).")
    add("")
    add("## 5. Selection criterion and precision-recall trade-offs")


    add("")
    add("- Criterion: **highest PR-AUC** on the shared held-out test set "
        "(tie-break F1). Accuracy is deliberately NOT the criterion: with "
        f"{info['pos_rate']:.1%} positives, accuracy is dominated by the "
        "majority class and can look high while missing overruns.")
    add(f"- Selected (plan_only / PRIMARY): "
        f"**{best_plan['model'] if best_plan else 'none'}** "
        f"(PR-AUC {fmt(best_plan.get('pr_auc')) if best_plan else 'n/a'}, "
        f"F1 {fmt(best_plan.get('f1')) if best_plan else 'n/a'})")
    if best_status:
        add(f"- Selected (current_status / separate): **{best_status['model']}** "
            f"(PR-AUC {fmt(best_status.get('pr_auc'))}, "
            f"F1 {fmt(best_status.get('f1'))})")
    if best_plan and best_plan.get("pr_auc") is not None:
        dummy = next((r for r in rows if r["model"] == "dummy_baseline"
                      and r["experiment"] == "plan_only"), None)
        if dummy and dummy.get("pr_auc") is not None:
            verdict = ("improves on" if plan_delta > 0.01
                       else "does NOT meaningfully improve on")
            add(f"- Honest baseline verdict: the selected plan_only model "
                f"**{verdict}** the dummy baseline "
                f"(PR-AUC delta = {plan_delta:+.4f}; "
                f"{'valid' if plan_ok else 'NOT a meaningful gain'}).")
    add("- Trade-off: for early warning a missed overrun (FN) is usually "
        "costlier than a false alarm (FP), so recall matters; but low "
        "precision floods reviewers with false alarms and destroys trust. "
        "`class_weight='balanced'` shifts models toward the positive class "
        "(higher recall, some precision cost). Threshold fixed at 0.5 - NOT "
        "tuned on the test set.")
    if best_plan is None:
        add("- **No model trained successfully; no result can be claimed.**")
    add("")
    add("## 6. Limitations")
    add("")
    add("- **Single April 2026 snapshot**: this random split measures only "
        "within-snapshot discrimination. It cannot establish that the model "
        "predicts overruns *in the future*; temporal validation on historical "
        "monthly snapshots is required in a later phase before any forecasting "
        "claim.")
    add("- plan_only features are available at sanction time only; performance "
        "reflects association, not causation (no feature *causes* an overrun).")
    add("- Test set used once for evaluation; no hyper-parameter tuning or "
        "threshold selection was performed with it.")
    add("- Labels derive from reported revised cost/dates as recorded in April "
        "2026; unreported revisions are invisible (time target excludes the 354 "
        "unknown rows rather than guessing).")
    add("- Covers only projects above the reporting threshold; generalisation "
        "to smaller projects is untested.")
    add("")
    add("## 7. Artifacts")
    add("")
    add(f"- pipeline (primary): `{info['pipe_path']}`")
    add(f"- pipeline (current_status): `{info['pipe_status_path']}`")
    add(f"- metadata: `{info['meta_path']}`")
    add(f"- comparison table: `{info['csv_path']}`")
    add("")
    return "\n".join(L)


def build_metadata(target: str, info: dict, rows: list[dict],
                   best_plan: dict | None, best_status: dict | None,
                   plan_ok: bool, plan_delta: float) -> dict:
    def slim(r: dict | None) -> dict | None:
        if r is None:
            return None
        keys = ["model", "experiment", "accuracy", "precision", "recall", "f1",
                "roc_auc", "pr_auc", "confusion_matrix", "status"]
        return {k: r.get(k) for k in keys}

    return {
        "target": target,
        "target_definition": TARGETS[target]["definition"],
        "unknown_handling": "-1 rows excluded from training/evaluation; never "
                            "treated as class 0.",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "random_seed": RANDOM_SEED,
        "split": {"test_size": TEST_SIZE,
                  "strategy": "stratified train_test_split",
                  "shared_test_rows_for_all_classifiers": True,
                  "n_train": info["train_n"], "n_test": info["test_n"]},
        "class_counts": {
            "eligible": {"n": info["n_eligible"], "pos": info["pos"],
                         "neg": info["neg"],
                         "excluded_unknown": info["n_unknown"]},
            "train": {"n": info["train_n"], "pos": info["train_pos"],
                      "neg": info["train_neg"]},
            "test": {"n": info["test_n"], "pos": info["test_pos"],
                     "neg": info["test_neg"]},
        },
        "primary_experiment": "plan_only",
        "feature_sets": {"plan_only": PLAN_FEATURES,
                         "current_status": STATUS_FEATURES},
        "forbidden_columns": sorted(forbidden_for(target)),
        "selection_criterion": "max PR-AUC on the shared held-out test set; "
                               "tie-break F1; accuracy never used alone; a "
                               "selection counts as valid only if PR-AUC beats "
                               "the dummy baseline by > 0.01",
        "selected_model_plan_only": slim(best_plan),
        "selected_model_current_status": slim(best_status),
        "plan_only_beats_baseline": plan_ok,
        "plan_only_pr_auc_delta_vs_baseline": (None if np.isnan(plan_delta)
                                               else round(plan_delta, 6)),
        "results": {f"{r['experiment']}/{r['model']}": r for r in rows},
        "artifacts": {
            "pipeline_plan_only": info["pipe_path"],
            "pipeline_current_status": info["pipe_status_path"],
            "comparison_csv": info["csv_path"],
            "report_md": info["meta_report_path"],
        },
        "data": {"features_csv": str(FEATURES_CSV.relative_to(ROOT)),
                 "features_sha256": info["features_sha"],
                 "raw_csv_sha256_expected": EXPECTED_RAW_SHA,
                 "clean_csv_sha256_expected": EXPECTED_CLEAN_SHA},
        "library_versions": {"python": __import__("platform").python_version(),
                             "scikit-learn": sklearn.__version__,
                             "pandas": pd.__version__,
                             "numpy": np.__version__},
        "limitations": [
            "Single April 2026 snapshot: within-snapshot discrimination only; "
            "future prediction performance is NOT established.",
            "Temporal validation on historical monthly snapshots is required "
            "before presenting this as a forecasting system.",
            "Association, not causation: feature importance does not mean a "
            "feature causes overruns.",
            "Threshold 0.5 fixed; not tuned (test set must not be tuned on).",
            "current_status experiment is a current-status classifier, not "
            "genuine early prediction.",
            "Labels rely on reported revisions; unreported revisions are not "
            "captured (354 time-target rows excluded as unknown).",
        ],
        "intended_use": "Research prototype for SIH: offline comparison of two "
                        "independent binary classifiers (cost/time overrun) on "
                        "one snapshot. NOT for operational decisions, alerts or "
                        "publishable forecasts.",
    }


# =================================================================== main ====
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}"
              + (f" - {detail}" if detail else ""))

    print("=" * 78)
    print("PAIMANA AI - PHASE 4 : TRAIN + EVALUATE COST & TIME OVERRUN MODELS")
    print("=" * 78)

    # ---- STEP 1: verify data and targets -----------------------------------
    print("\n[STEP 1] VERIFY DATA AND TARGETS")
    for p in (FEATURES_CSV, DICT_CSV, RAW_CSV, CLEAN_CSV):
        assert p.exists(), f"missing required input: {p}"
        print(f"    found {p.relative_to(ROOT)}")

    df = pd.read_csv(FEATURES_CSV)
    dictionary = pd.read_csv(DICT_CSV)
    raw_sha, clean_sha = sha256_of(RAW_CSV), sha256_of(CLEAN_CSV)
    print(f"    features shape: {df.shape}")
    print(f"    raw sha256    : {raw_sha}")
    print(f"    clean sha256  : {clean_sha}")
    check("original CSV unchanged (pre)", raw_sha == EXPECTED_RAW_SHA)
    check("cleaned CSV unchanged (pre)", clean_sha == EXPECTED_CLEAN_SHA)

    for target, spec in TARGETS.items():
        assert spec["label"] in df.columns, f"missing label {spec['label']}"
    print("    target column check: both label columns present")

    counts: dict[str, dict] = {}
    for target, spec in TARGETS.items():
        lab = spec["label"]
        elig = df[df[lab] != -1]
        pos, neg = int((elig[lab] == 1).sum()), int((elig[lab] == 0).sum())
        unk = int((df[lab] == -1).sum())
        counts[target] = {"eligible": len(elig), "pos": pos, "neg": neg,
                          "unknown": unk}
        print(f"\n    {target}:")
        print(f"      definition        : {spec['definition']}")
        print(f"      eligible rows     : {len(elig)}")
        print(f"      positive (1)      : {pos} "
              f"({100 * pos / max(len(elig), 1):.1f}%)")
        print(f"      negative (0)      : {neg}")
        print(f"      unknown (-1, kept): {unk}  (excluded from training, "
              "never treated as 0)")

    # ---- STEP 2: leakage allowances (fail-fast assertions) ------------------
    print("\n[STEP 2] LEAKAGE CHECKS (allowances from leakage_review.md)")
    for target in TARGETS:
        for exp, feats in (("plan_only", PLAN_FEATURES),
                           ("current_status", STATUS_FEATURES)):
            assert_features_allowed(feats, target, dictionary)
            print(f"    PASS {target}/{exp}: {len(feats)} features, no forbidden "
                  "or outcome-derived column")
    print(f"    HistGB class_weight supported (sklearn {sklearn.__version__}): "
          f"{HGB_SUPPORTS_CLASS_WEIGHT}")

    features_sha = sha256_of(FEATURES_CSV)
    info: dict[str, dict] = {}
    rows_all: dict[str, list[dict]] = {}
    bundles: dict[str, dict] = {}

        # ---- STEPS 3-5: train, evaluate, save for both targets ------------------
    for target, spec in TARGETS.items():
        print(f"\n[STEP 3/4] TARGET = {target}")
        lab = spec["label"]
        elig = df[df[lab] != -1].reset_index(drop=True)
        y = elig[lab].astype(int)
        idx = np.arange(len(elig))
        strat = y if (y.nunique() == 2 and y.value_counts().min() >= 2) else None
        tr, te = train_test_split(idx, test_size=TEST_SIZE,
                                  random_state=RANDOM_SEED, stratify=strat)
        c = counts[target]
        info[target] = {
            "n_eligible": c["eligible"], "pos": c["pos"], "neg": c["neg"],
            "n_unknown": c["unknown"], "train_n": len(tr), "test_n": len(te),
            "train_pos": int((y.iloc[tr] == 1).sum()),
            "train_neg": int((y.iloc[tr] == 0).sum()),
            "test_pos": int((y.iloc[te] == 1).sum()),
            "test_neg": int((y.iloc[te] == 0).sum()),
            "pos_rate": c["pos"] / max(c["eligible"], 1),
            "features_sha": features_sha,
        }
        print(f"    split: train={len(tr)} (pos {info[target]['train_pos']}/"
              f"neg {info[target]['train_neg']})  test={len(te)} (pos "
              f"{info[target]['test_pos']}/neg {info[target]['test_neg']})  "
              f"stratified={strat is not None}")

        rows: list[dict] = []
        bundle_by_exp: dict[str, dict] = {}
        for exp, feats in (("plan_only", PLAN_FEATURES),
                           ("current_status", STATUS_FEATURES)):
            print(f"    -- experiment: {exp} ({len(feats)} features)")
            r, bundle = run_experiment(elig, lab, target, feats, exp, tr, te,
                                       dictionary)
            rows += r
            bundle_by_exp[exp] = bundle
            for row in r:
                if row["status"] == "OK":
                    print(f"       {row['model']:<24} acc={row['accuracy']:.3f} "
                          f"prec={row['precision']:.3f} rec={row['recall']:.3f} "
                          f"f1={row['f1']:.3f} roc={fmt(row['roc_auc'])} "
                          f"pr={fmt(row['pr_auc'])}")
        rows_all[target] = rows
        bundles[target] = bundle_by_exp

        plan_rows = [r for r in rows if r["experiment"] == "plan_only"]
        status_rows = [r for r in rows if r["experiment"] == "current_status"]
        best_plan = select_best(plan_rows)
        best_status = select_best(status_rows)
        plan_ok, plan_delta = beats_baseline(best_plan, plan_rows)

        # ---- STEP 5: save artifacts ----------------------------------------
        tdir = ROOT / "models" / target
        tdir.mkdir(parents=True, exist_ok=True)
        info[target].update({
            "pipe_path": str((tdir / "pipeline.joblib").relative_to(ROOT)),
            "pipe_status_path": str(
                (tdir / "pipeline_current_status.joblib").relative_to(ROOT)),
            "meta_path": str((tdir / "metadata.json").relative_to(ROOT)),
            "csv_path": str((OUT_DIR / f"{target}_model_comparison.csv")
                            .relative_to(ROOT)),
            "meta_report_path": str((OUT_DIR / f"{target}_report.md")
                                    .relative_to(ROOT)),
        })
        if best_plan is not None:
            pipe = bundle_by_exp["plan_only"]["fitted"].get(best_plan["model"])
            if pipe is not None:
                joblib.dump(pipe, ROOT / info[target]["pipe_path"])
        if best_status is not None:
            pipe = bundle_by_exp["current_status"]["fitted"].get(
                best_status["model"])
            if pipe is not None:
                joblib.dump(pipe, ROOT / info[target]["pipe_status_path"])
        comparison_frame(rows).to_csv(ROOT / info[target]["csv_path"],
                                      index=False)
        (ROOT / info[target]["meta_report_path"]).write_text(
            build_report_md(target, info[target], rows, best_plan, best_status,
                            plan_ok, plan_delta), encoding="utf-8")
        (ROOT / info[target]["meta_path"]).write_text(
            json.dumps(build_metadata(target, info[target], rows, best_plan,
                                      best_status, plan_ok, plan_delta),
                       indent=2, default=str), encoding="utf-8")
        print(f"    selected (plan_only / PRIMARY): "
              f"{best_plan['model'] if best_plan else 'none'}")
        print(f"    selected (current_status)     : "
              f"{best_status['model'] if best_status else 'none'}")
        print(f"    plan_only beats baseline: {plan_ok} (PR-AUC delta "
              f"{plan_delta:+.4f})")

        # ---- STEP 6: validation -------------------------------------------------
    print("\n[STEP 6] VALIDATION")
    for target in TARGETS:
        pipe_path = ROOT / info[target]["pipe_path"]
        meta_path = ROOT / info[target]["meta_path"]
        check(f"{target}: pipeline file exists", pipe_path.exists(),
              str(pipe_path.relative_to(ROOT)))
        pipe = joblib.load(pipe_path)
        check(f"{target}: pipeline reloads", pipe is not None)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        check(f"{target}: metadata loads", meta.get("target") == target)

        X_one = bundles[target]["plan_only"]["X_test"].iloc[[0]]
        forbidden = forbidden_for(target) | FORBIDDEN_FOR_BOTH
        stray = set(X_one.columns) & forbidden
        check(f"{target}: forbidden columns absent from feature matrix",
              not stray, f"stray={sorted(stray)}")

        pred = np.asarray(pipe.predict(X_one))
        check(f"{target}: prediction shape == (1,)", pred.shape == (1,),
              f"shape={pred.shape}")
        check(f"{target}: predicted class is 0/1", pred[0] in (0, 1),
              f"value={pred[0]}")
        proba = pipe.predict_proba(X_one)
        check(f"{target}: probability shape == (1,2)", proba.shape == (1, 2),
              f"shape={proba.shape}")
        check(f"{target}: probabilities within [0,1]",
              bool(np.all(proba >= 0) and np.all(proba <= 1)),
              f"min={proba.min():.4f} max={proba.max():.4f}")
        check(f"{target}: probability rows sum to ~1",
              abs(float(proba.sum()) - 1.0) < 1e-6, f"sum={proba.sum():.6f}")

        sp = ROOT / info[target]["pipe_status_path"]
        pipe2 = joblib.load(sp) if sp.exists() else None
        check(f"{target}: current_status pipeline reloads", pipe2 is not None)
        cdf = pd.read_csv(ROOT / info[target]["csv_path"])
        check(f"{target}: comparison CSV readable", len(cdf) == 8,
              f"rows={len(cdf)}")
        rep = ROOT / info[target]["meta_report_path"]
        check(f"{target}: report md readable", rep.exists() and rep.stat().st_size > 500,
              f"bytes={rep.stat().st_size}")

    check("original CSV unchanged (post)", sha256_of(RAW_CSV) == EXPECTED_RAW_SHA)
    check("cleaned CSV unchanged (post)", sha256_of(CLEAN_CSV) == EXPECTED_CLEAN_SHA)

    failed = [c for c in checks if not c[1]]
    print(f"\n    validation summary: {len(checks) - len(failed)}/{len(checks)} "
          "checks passed")
    for name, _, detail in failed:
        print(f"    FAILED: {name} {detail}")
    if failed:
        raise SystemExit(1)

    # ---- final summary ------------------------------------------------------
    print("\n" + "=" * 78)
    print("FINAL SUMMARY (actual held-out test metrics)")
    for target in TARGETS:
        rows = rows_all[target]
        bp = select_best([r for r in rows if r["experiment"] == "plan_only"])
        bs = select_best([r for r in rows if r["experiment"] == "current_status"])
        c = counts[target]
        print(f"  {target}  (eligible {c['eligible']}: pos {c['pos']} / "
              f"neg {c['neg']}; unknown excluded {c['unknown']})")
        print(f"    PRIMARY  plan_only      : "
              f"{bp['model'] if bp else 'none'}")
        if bp:
            print(f"             acc={bp['accuracy']:.3f} "
                  f"prec={bp['precision']:.3f} rec={bp['recall']:.3f} "
                  f"f1={bp['f1']:.3f} roc_auc={fmt(bp['roc_auc'])} "
                  f"pr_auc={fmt(bp['pr_auc'])}")
        print(f"    SEPARATE current_status : "
              f"{bs['model'] if bs else 'none'}")
        if bs:
            print(f"             acc={bs['accuracy']:.3f} "
                  f"prec={bs['precision']:.3f} rec={bs['recall']:.3f} "
                  f"f1={bs['f1']:.3f} roc_auc={fmt(bs['roc_auc'])} "
                  f"pr_auc={fmt(bs['pr_auc'])}")
        print(f"    artifacts: {info[target]['pipe_path']}, "
              f"{info[target]['meta_path']}, {info[target]['csv_path']}, "
              f"{info[target]['meta_report_path']}")
    print("=" * 78)
    print("STOP: no risk scoring, alerts, frontend, backend, database, "
          "dashboard, LLM, RAG or deployment (per instructions).")


if __name__ == "__main__":
    main()








