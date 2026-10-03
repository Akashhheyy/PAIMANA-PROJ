# PAIMANA AI - COST OVERRUN MODEL REPORT

- generated (UTC): 2026-10-03T12:06:01.319213+00:00
- script: `ml/04_train_models.py`  |  random seed: **42**  |  test size: **20%** (stratified, shared by all classifiers)
- data: `data/processed/paimana_features.csv` (sha256 `57819774001a7d6b2e999c9fdc4a2e6407a4eef1bf631b2a0deb41e2972fe9bc`)

## 1. Target definition

`cost_overrun_label`: 1 if revised_cost_crore > original_cost_crore; 0 if <=; -1 (unknown, excluded) if either cost missing/invalid (NaN or <= 0).

## 2. Sample counts and split

| | count | positive (1) | negative (0) |
|---|---|---|---|
| eligible rows | 1981 | 542 | 1439 |
| excluded (unknown = -1) | 0 | - | - |
| train | 1584 | 433 | 1151 |
| test | 397 | 109 | 288 |

## 3. Feature sets and leakage controls

- **plan_only (PRIMARY, early-warning oriented)**: ['original_cost_crore', 'log1p_original_cost', 'approval_year', 'approval_month', 'planned_horizon_months', 'agency', 'state']
- **current_status (SEPARATE, clearly labelled)**: plan_only + ['cumulative_expenditure_crore', 'log1p_expenditure', 'expenditure_ratio', 'physical_progress_pct', 'progress_expenditure_gap', 'project_age_months', 'planned_duration_months', 'approval_to_start_months', 'months_to_target', 'target_passed', 'schedule_elapsed_pct', 'progress_vs_schedule_pct']
- Forbidden for this model (asserted at runtime): ['cost_overrun_label', 'legacy_ocms_code', 'pmgid', 'project_code', 'project_name', 'report_month', 'revised_cost_crore', 'revised_doc', 'sl_no', 'time_overrun_label']
- Feature allowances follow `outputs/models/leakage_review.md`.
- Current-status results describe a **current-status classifier** and are **not** evidence of genuine early prediction.

## 4. Model comparison (held-out test set, same rows for all models)

### Experiment: `plan_only` (primary)

| MODEL | STATUS | ACCURACY | PRECISION | RECALL | F1 | ROC-AUC | PR-AUC | CM (tn/fp/fn/tp) |
|---|---|---|---|---|---|---|---|---|
| dummy_baseline | OK | 0.7254 | 0.0000 | 0.0000 | 0.0000 | 0.5000 | 0.2746 | 288/0/109/0 |
| logistic_regression | OK | 0.7531 | 0.5369 | 0.7339 | 0.6202 | 0.8138 | 0.6102 | 219/69/29/80 |
| random_forest | OK | 0.7708 | 0.5738 | 0.6422 | 0.6061 | 0.8292 | 0.6109 | 236/52/39/70 |
| hist_gradient_boosting | OK | 0.7758 | 0.5847 | 0.6330 | 0.6079 | 0.8060 | 0.6097 | 239/49/40/69 |

### Experiment: `current_status` (separate status experiment)

| MODEL | STATUS | ACCURACY | PRECISION | RECALL | F1 | ROC-AUC | PR-AUC | CM (tn/fp/fn/tp) |
|---|---|---|---|---|---|---|---|---|
| dummy_baseline | OK | 0.7254 | 0.0000 | 0.0000 | 0.0000 | 0.5000 | 0.2746 | 288/0/109/0 |
| logistic_regression | OK | 0.7985 | 0.5973 | 0.8165 | 0.6899 | 0.8659 | 0.7214 | 228/60/20/89 |
| random_forest | OK | 0.7985 | 0.6408 | 0.6055 | 0.6226 | 0.8721 | 0.7318 | 251/37/43/66 |
| hist_gradient_boosting | OK | 0.7985 | 0.6436 | 0.5963 | 0.6190 | 0.8586 | 0.7199 | 252/36/44/65 |

> Baseline = `dummy_baseline` (predicts the training prior; PR-AUC equals test prevalence, ROC-AUC 0.5 by construction).

## 5. Selection criterion and precision-recall trade-offs

- Criterion: **highest PR-AUC** on the shared held-out test set (tie-break F1). Accuracy is deliberately NOT the criterion: with 27.4% positives, accuracy is dominated by the majority class and can look high while missing overruns.
- Selected (plan_only / PRIMARY): **random_forest** (PR-AUC 0.6109, F1 0.6061)
- Selected (current_status / separate): **random_forest** (PR-AUC 0.7318, F1 0.6226)
- Honest baseline verdict: the selected plan_only model **improves on** the dummy baseline (PR-AUC delta = +0.3363; valid).
- Trade-off: for early warning a missed overrun (FN) is usually costlier than a false alarm (FP), so recall matters; but low precision floods reviewers with false alarms and destroys trust. `class_weight='balanced'` shifts models toward the positive class (higher recall, some precision cost). Threshold fixed at 0.5 - NOT tuned on the test set.

## 6. Limitations

- **Single April 2026 snapshot**: this random split measures only within-snapshot discrimination. It cannot establish that the model predicts overruns *in the future*; temporal validation on historical monthly snapshots is required in a later phase before any forecasting claim.
- plan_only features are available at sanction time only; performance reflects association, not causation (no feature *causes* an overrun).
- Test set used once for evaluation; no hyper-parameter tuning or threshold selection was performed with it.
- Labels derive from reported revised cost/dates as recorded in April 2026; unreported revisions are invisible (time target excludes the 354 unknown rows rather than guessing).
- Covers only projects above the reporting threshold; generalisation to smaller projects is untested.

## 7. Artifacts

- pipeline (primary): `models\cost_overrun\pipeline.joblib`
- pipeline (current_status): `models\cost_overrun\pipeline_current_status.joblib`
- metadata: `models\cost_overrun\metadata.json`
- comparison table: `outputs\models\cost_overrun_model_comparison.csv`
