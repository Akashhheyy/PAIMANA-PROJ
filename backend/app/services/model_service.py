"""Model service - loads the EXISTING Phase-4 pipelines ONCE and predicts.

Rules honoured here:
* joblib.load runs at most once per process (lru_cache) - never per request.
* No retraining, no model file is written, no ML logic is duplicated:
  loading/n_jobs determinism is delegated to ml/06_risk_scoring.load_pipelines.
* The input schema is the exact Phase-4 plan-only schema taken from the
  model metadata (feature_names_in_), never an invented feature set.
* Missing artifacts raise ModelServiceError -> API maps it to a clean
  service error (no stack traces / filesystem paths leak to clients).
"""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import get_settings

# Exact Phase-4 plan-only feature schema (source of truth = model metadata).
PLAN_ONLY_FEATURES: list[str] = [
    "original_cost_crore",
    "log1p_original_cost",
    "approval_year",
    "approval_month",
    "planned_horizon_months",
    "agency",
    "state",
]


class ModelServiceError(RuntimeError):
    """Raised when trained artifacts cannot be loaded/predicted (clean msg)."""


def load_ml_module(slug: str, filename: str):
    """Import an ml/<digit-prefixed>.py module exactly once (source of truth:
    Phase-5 risk maths and Phase-6 warning rules stay in the ML layer)."""
    if slug in sys.modules:
        return sys.modules[slug]
    path = get_settings().project_root / "ml" / filename
    if not path.exists():
        raise ModelServiceError(f"required ML module {filename} is unavailable")
    spec = importlib.util.spec_from_file_location(slug, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[slug] = mod
    spec.loader.exec_module(mod)
    return mod


# Phase-5 risk scoring (thresholds, combination) and Phase-6 warning logic.
rs06 = load_ml_module("paimana_rs06", "06_risk_scoring.py")
rs07 = load_ml_module("paimana_rs07", "07_early_warning.py")


@lru_cache(maxsize=1)
def get_pipelines() -> dict[str, Any]:
    """Load BOTH trained pipelines exactly once and reuse them.

    Delegates to ml/06.load_pipelines (joblib.load only, n_jobs=1 for
    deterministic inference). Never fits/retrains anything."""
    try:
        return rs06.load_pipelines()
    except Exception as exc:            # artifact missing/corrupt
        raise ModelServiceError(
            "trained model artifacts could not be loaded"
        ) from exc


def _predict_one(pipeline: Any, features: dict[str, Any]) -> float:
    """Positive-class probability for one model using its OWN saved column
    order. Missing keys are an error, never silently filled."""
    expected = list(pipeline.feature_names_in_)
    missing = [f for f in expected if f not in features]
    if missing:
        raise ValueError(f"missing required model features: {missing}")
    X = pd.DataFrame([[features[f] for f in expected]], columns=expected)
    proba = pipeline.predict_proba(X)
    idx = list(pipeline.classes_).index(1)
    return float(proba[0][idx])


def predict_plan_only(features: dict[str, Any]) -> dict[str, Any]:
    """Cost + time overrun probabilities for one plan-only feature record.

    Returns probabilities, availability flags, and the Phase-5 combined
    score/category computed with the UNCHANGED Phase-5 functions."""
    pipelines = get_pipelines()
    try:
        cost_p = _predict_one(pipelines["cost_overrun"], features)
        time_p = _predict_one(pipelines["time_overrun"], features)
    except ValueError:
        raise
    except Exception as exc:
        raise ModelServiceError("prediction failed inside the model pipeline") from exc

    combo = rs06.combine_probabilities([cost_p], [time_p])
    combined = combo["combined_risk_score"].iloc[0]
    status = str(combo["score_status"].iloc[0])
    missing_comp = str(combo["missing_component"].iloc[0])
    category = (rs06.risk_category(float(combined))
                if pd.notna(combined) else None)
    return {
        "cost_overrun_probability": cost_p,
        "time_overrun_probability": time_p,
        "cost_probability_available": True,
        "time_probability_available": True,
        "combined_risk_score": (float(combined) if pd.notna(combined) else None),
        "score_status": status,
        "missing_component": missing_comp,
        "risk_category": category,
    }


def derive_log1p_cost(original_cost_crore: float) -> float:
    """Exact Phase-3 derivation (ml/03: np.log1p of sanctioned cost)."""
    return float(np.log1p(original_cost_crore))


def model_info() -> dict[str, Any]:
    """Loaded-model diagnostics (no retraining: returns cached objects)."""
    pipes = get_pipelines()
    return {
        "cost_model_type": type(pipes["cost_overrun"].steps[-1][1]).__name__,
        "time_model_type": type(pipes["time_overrun"].steps[-1][1]).__name__,
        "feature_schema": list(pipes["cost_overrun"].feature_names_in_),
    }
