# PAIMANA AI - RISK SCORING REPORT (Phase 5)

- generated (UTC): 2026-10-05T07:40:43.040054+00:00
- script: `ml/06_risk_scoring.py`  |  formula version: `v1-equal-weight-2026-04-snapshot`
- output: `outputs/risk/project_risk_scores.csv`

## 1. What this is (and is not)

- **PROTOTYPE risk scoring** over a single **April 2026** snapshot.
- It is **NOT verified future prediction** and **NOT a validated early-warning rate** - Phase 4 established that a single snapshot cannot support temporal validation.
- The score reflects **modelled associations, not causation**: a High risk score does not mean any feature *causes* a cost or time overrun.
- Scores were produced by **loading the saved Phase-4 pipelines** (`joblib.load`). No model was retrained, replaced or tuned in this phase, and no Phase-4 result was modified.
- Inference runs with `n_jobs=1` (thread-serial tree summation) so repeated runs are byte-identical; this changes only in-memory parallelism, never the fitted parameters or the files on disk.

## 2. Inputs and models

| item | sha256 (before) | sha256 (after) | unchanged |
|---|---|---|---|
| original CSV | `708a2fd905256878...` | `708a2fd905256878...` | YES |
| cleaned CSV | `a7f330ac31d3939f...` | `a7f330ac31d3939f...` | YES |
| features CSV | `57819774001a7d6b...` | `57819774001a7d6b...` | YES |
| cost pipeline | `8769f00f66df06fd...` | `8769f00f66df06fd...` | YES |
| cost metadata | `50dddb7635504374...` | `50dddb7635504374...` | YES |
| time pipeline | `450847cf046d8581...` | `450847cf046d8581...` | YES |
| time metadata | `96fc671bc22e545c...` | `96fc671bc22e545c...` | YES |

| pipeline | estimator (from Phase 4) | input features (exact saved order) |
|---|---|---|
| `models/cost_overrun/pipeline.joblib` | random_forest (plan_only) | ['original_cost_crore', 'log1p_original_cost', 'approval_year', 'approval_month', 'planned_horizon_months', 'agency', 'state'] |
| `models/time_overrun/pipeline.joblib` | hist_gradient_boosting (plan_only) | ['original_cost_crore', 'log1p_original_cost', 'approval_year', 'approval_month', 'planned_horizon_months', 'agency', 'state'] |

## 3. Scoring formula

```
both probabilities available :
    combined = (W_COST * cost_p + W_TIME * time_p) / (W_COST + W_TIME)
    with W_COST = 0.5, W_TIME = 0.5   -> score_status 'complete'
only one available           :
    combined = the available probability
    -> score_status 'partial'; missing_component names what is absent;
       a missing probability is NEVER replaced with 0
neither available            : combined = NaN, score_status 'missing'
```

## 4. Risk thresholds (configurable, prototype defaults)

| category | condition |
|---|---|
| Low | `0 <= combined < 0.35` |
| Medium | `0.35 <= combined < 0.65` |
| High | `0.65 <= combined <= 1` |
| Unknown | combined is NaN |

Rationale: the equal-weighted probability is centred on 0.5, so a symmetric middle band marks the uncertain zone and the outer thirds flag clearly above/below-average overrun probability. **These thresholds are NOT calibrated or validated** against outcomes (calibrating on this same single snapshot would overfit); they are configurable placeholders for a later phase.

## 5. Eligibility and missing data

- rows scored                 : 1981
- cost probability available  : 1981
- time probability available  : 1627 (only rows with a KNOWN time-overrun target)
- time label unknown (-1 rows): 354 - label preserved as -1, probability left empty, never treated as negative
- score_status counts         : {'complete': 1627, 'partial': 354}
- missing_component counts    : {'none': 1627, 'time_overrun_probability': 354}

## 6. Summary counts by risk category

| risk_category | projects | of which 'complete' | of which 'partial' |
|---|---|---|---|
| Low | 641 | 356 | 285 |
| Medium | 575 | 522 | 53 |
| High | 765 | 749 | 16 |

combined score: min=0.0071, median=0.5755, max=0.9755

## 7. Data limitations

- Single April 2026 snapshot: scores separate projects *within this snapshot* only; future-month performance is untested.
- `plan_only` probabilities come from Phase-4 models whose test PR-AUC was 0.61 (cost) and 0.97 (time); the cost model in particular still misclassifies many projects - treat individual scores as indicative.
- Time probability availability is defined by label knowledge (354 rows have no revised completion date); on truly new projects the same rule must be expressed as 'time model input unavailable'.
- Probabilities are uncalibrated classifier outputs used as scores.
- Association, not causation; no alerting thresholds were validated.
