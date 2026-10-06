# PAIMANA AI - EXPLAINABLE EARLY-WARNING REPORT (Phase 6)

- generated (UTC): 2026-10-06T12:20:47.425826+00:00
- **This is an explainable prototype early-warning and decision-support layer based on model-estimated project risk.**
- Single April 2026 reporting snapshot - NOT a validated future forecasting system. Future historical monthly snapshots can later be used for temporal validation.
- Output: `outputs/risk/early_warning_results.csv` (1981 rows, 24 columns)

## 1. Projects analyzed

- **1981 projects** (all rows of the Phase-5 risk output)

## 2-4. Warning counts by priority (actual values)

| priority | label | projects |
|---|---|---|
| HIGH | Priority monitoring | 1281 |
| MEDIUM | Monitor | 61 |
| LOW | No immediate model-based warning | 639 |

- **HIGH warnings (Priority monitoring): 1281**
- **MEDIUM warnings (Monitor): 61**
- **LOW / no immediate warning: 639**
- NOT_AVAILABLE (no score, no assumed risk): 0

## 5. Partial / incomplete scores

- score_status = partial : 354
- score_status = missing  : 0
- rows with DATA_COMPLETENESS_WARNING : 354
- Missing probabilities are reported as `n/a` and are **never treated as zero risk**.

## 6-8. Warning type counts (actual values)

| warning type | projects |
|---|---|
| COST_WARNING (cost_p >= 0.65) | 380 |
| TIME_WARNING (time_p >= 0.65) | 1239 |
| COMBINED_HIGH_RISK_WARNING (combined >= 0.65, both present) | 749 |
| MEDIUM_RISK_WARNING (0.35 <= combined < 0.65) | 575 |
| DATA_COMPLETENESS_WARNING | 354 |

## 9. Warning logic

- Thresholds are **reused unchanged from Phase 5** (`06_risk_scoring`): Low < 0.35 <= Medium < 0.65 <= High; verified by runtime assertion.
- Priority: HIGH if COST/TIME/COMBINED warning fired; else MEDIUM for the medium band; else LOW when a combined score exists; **NOT_AVAILABLE when no score exists (never reported as Low)**.
- Partial scores keep their score-based priority but every message is prefixed with "Warning based on incomplete model evidence."
- COMBINED_HIGH_RISK_WARNING additionally requires BOTH probabilities; COST/TIME warnings trigger at >= 0.65.
- Missing probabilities are never treated as zero risk.

## 10. Explanation methodology

- method: **shap_tree_explainer**
- scale: cost_overrun: class-1 probability scale; time_overrun: raw margin (log-odds) scale
- Per-project `risk_indicators` list actual model outputs (cost_p, time_p, combined, category) plus the top model-associated plan features with actual values and signed contributions.
- Wording rules: "the model estimates elevated risk" / "model-associated indicator" - NEVER "X causes overrun", and every high probability is labelled a MODEL-ESTIMATED RISK, not a confirmed future event.
- Global model-associated feature strength (mean |attribution|, association not causation):
  - **cost_overrun**: approval_year=0.1161, agency=0.1008, state=0.0425, original_cost_crore=0.0415, log1p_original_cost=0.0409, planned_horizon_months=0.0247, approval_month=0.0229
  - **time_overrun**: approval_year=4.3825, planned_horizon_months=3.4608, approval_month=1.0383, original_cost_crore=0.8769, agency=0.7816, state=0.6751, log1p_original_cost=0.0000
- Feature meanings come from `outputs/models/feature_dictionary.csv`; feature allowances from `outputs/models/leakage_review.md`.

## 11. Limitations

- Single April 2026 snapshot: warnings separate projects within this snapshot only; they do NOT forecast the future.
- Underlying Phase-4 models: plan-only PR-AUC 0.61 (cost) / 0.97 (time) on the same snapshot - individual scores are indicative.
- Uncalibrated probabilities used as scores; thresholds (0.35/0.65 and the 0.65 warning triggers) are unvalidated prototype defaults.
- Recommendations are **monitoring suggestions, not automatic government decisions**; no project-specific facts are invented.
- Association, not causation: attribution shows what the model relied on, not what causes overruns.
- 354 rows lack a time-overrun probability (unknown label); their warnings rest on cost evidence only and are flagged as incomplete.

## Data integrity (inputs unchanged by this phase)

| file | sha256 before | unchanged |
|---|---|---|
| original CSV | `708a2fd905256878...` | YES |
| cleaned CSV | `a7f330ac31d3939f...` | YES |
| features CSV | `57819774001a7d6b...` | YES |
| cost model | `8769f00f66df06fd...` | YES |
| time model | `450847cf046d8581...` | YES |
| phase5 risk output | `2bc562bedf2f6197...` | YES |
| phase5 risk report | `47dc69e6eed733a2...` | YES |
