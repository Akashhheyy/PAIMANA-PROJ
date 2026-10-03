# PAIMANA AI - LEAKAGE REVIEW (Phase 3, Steps 2-4)

- generated (UTC): 2026-10-03T11:50:24.281516+00:00
- source data: data/processed/paimana_clean.csv (raw CSV sha256 `708a2fd905256878e6dc697fec366c71d126f06c5bd9119f2ca1cbd2fd2b93af`)
- snapshot: **April 2026** (single month; report_month is constant)

## 1. Target definitions and class counts

| Target | Definition | Eligible | Positive | Negative | Unknown (-1, excluded) |
|---|---|---|---|---|---|
| cost_overrun_label | 1 if `revised_cost_crore > original_cost_crore`, else 0; **-1** if either cost is missing/invalid (NaN or <= 0) | 1981 | 542 | 1439 | 0 |
| time_overrun_label | 1 if `revised_doc > target_doc`, else 0; **-1** if either date is missing/invalid | 1627 | 1245 | 382 | 354 |

Unknown labels stay at **-1** and are dropped from supervised training; they are NEVER encoded as class 0 (a missing revised_doc must not be read as 'no schedule overrun').

## 2. Rejected columns (never used as features)

| FEATURE | MODEL | LEAKAGE RISK | REASON |
|---|---|---|---|
| `revised_cost_crore` | cost_overrun | **LEAKAGE** | The cost label is defined directly as revised > original cost; any feature derived from it would read the answer. |
| `revised_doc` | time_overrun | **LEAKAGE** | The time label is defined directly as revised_doc > target_doc; using revised_doc (or anything derived from it) would read the answer. |
| `cost_overrun_label` | cost_overrun | **LEAKAGE** | The target itself. |
| `time_overrun_label` | time_overrun | **LEAKAGE** | The target itself. |
| `report_month` | both | **CONSTANT** | April 2026 for every row -> zero variance, no predictive value; it is the snapshot date, not a project attribute. |
| `sl_no` | both | **IDENTIFIER** | Row serial number, unique per record. |
| `project_code` | both | **IDENTIFIER** | Unique per project; would only let the model memorise rows. |
| `legacy_ocms_code` | both | **IDENTIFIER** | Legacy id, mostly '-'; unique where populated. |
| `pmgid` | both | **IDENTIFIER** | PMG id, mostly '-'; unique where populated. |
| `project_name` | both | **IDENTIFIER/TEXT** | Free text unique per row (1981 distinct names); no text model in this phase, and it would act as a row identifier. |

## 3. Allowed features - COST OVERRUN model

`revised_cost_crore` and anything derived from it are used **only** to build the label. None of the features below touch it.

| FEATURE | EXPERIMENT | LEAKAGE RISK | REASON |
|---|---|---|---|
| `original_cost_crore` | plan_only + current_status | NONE | Fixed at sanction time; contains no post-approval outcome information. |
| `log1p_original_cost` | plan_only + current_status | NONE | Fixed at sanction time; contains no post-approval outcome information. |
| `approval_year` | plan_only + current_status | NONE | Fixed at sanction time; contains no post-approval outcome information. |
| `approval_month` | plan_only + current_status | NONE | Fixed at sanction time; contains no post-approval outcome information. |
| `planned_horizon_months` | plan_only + current_status | NONE | Fixed at sanction time; contains no post-approval outcome information. |
| `agency` | plan_only + current_status | NONE | Fixed at sanction time; contains no post-approval outcome information. |
| `state` | plan_only + current_status | NONE | Fixed at sanction time; contains no post-approval outcome information. |
| `cumulative_expenditure_crore` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |
| `log1p_expenditure` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |
| `expenditure_ratio` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |
| `physical_progress_pct` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |
| `progress_expenditure_gap` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |
| `project_age_months` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |
| `planned_duration_months` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |
| `approval_to_start_months` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |
| `months_to_target` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |
| `target_passed` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |
| `schedule_elapsed_pct` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |
| `progress_vs_schedule_pct` | current_status only | LOW-MED (status, not leakage) | Observed April-2026 state derived from plan/status columns only - never from revised_cost_crore, so it does not read the label; but it is measured *after* the project started, so it is allowed only in the clearly documented current-status experiment. |

## 4. Allowed features - TIME OVERRUN model

`revised_doc` and anything derived from it are used **only** to build the label; no feature below ever reads it.

| FEATURE | EXPERIMENT | LEAKAGE RISK | REASON |
|---|---|---|---|
| `original_cost_crore` | plan_only + current_status | NONE | Plan-time fact; `target_doc` appears only as a planned-duration anchor and is never compared with `revised_doc`. |
| `log1p_original_cost` | plan_only + current_status | NONE | Plan-time fact; `target_doc` appears only as a planned-duration anchor and is never compared with `revised_doc`. |
| `approval_year` | plan_only + current_status | NONE | Plan-time fact; `target_doc` appears only as a planned-duration anchor and is never compared with `revised_doc`. |
| `approval_month` | plan_only + current_status | NONE | Plan-time fact; `target_doc` appears only as a planned-duration anchor and is never compared with `revised_doc`. |
| `planned_horizon_months` | plan_only + current_status | NONE | Plan-time fact; `target_doc` appears only as a planned-duration anchor and is never compared with `revised_doc`. |
| `agency` | plan_only + current_status | NONE | Plan-time fact; `target_doc` appears only as a planned-duration anchor and is never compared with `revised_doc`. |
| `state` | plan_only + current_status | NONE | Plan-time fact; `target_doc` appears only as a planned-duration anchor and is never compared with `revised_doc`. |
| `cumulative_expenditure_crore` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |
| `log1p_expenditure` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |
| `expenditure_ratio` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |
| `physical_progress_pct` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |
| `progress_expenditure_gap` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |
| `project_age_months` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |
| `planned_duration_months` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |
| `approval_to_start_months` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |
| `months_to_target` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |
| `target_passed` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |
| `schedule_elapsed_pct` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |
| `progress_vs_schedule_pct` | current_status only | LOW-MED (status, not leakage) | Computed from plan/status columns only (`start_date`, `target_doc`, expenditure, progress vs the constant report month); `revised_doc` is never read. Deadline-relative fields (`months_to_target`, `target_passed`) do associate with revision likelihood, but contain no revised-date information - this is documented confounding, not leakage. |

## 5. Early-warning suitability assessment (important)

- The **plan_only** experiment uses only information fixed at sanction (cost, approval timing, planned horizon, agency, state). It is the only set that may be described as *early prediction*.
- The **current_status** experiment adds April-2026 expenditure, physical progress, project age and deadline proximity. These fields reflect how the project is going *now*.
- **Using current-status features does NOT prove early predictive capability.** Strong current-status results only show that the model can classify present condition from present signals; they cannot show the model would have flagged an overrun *before* it happened. Such models are reported strictly as *current-status classifiers*.
- 5 rows have `start_date` after the report month, so even start-derived fields carry current-state information; that is why all start-derived features live in `current_status only`.
- This dataset is a **single April 2026 snapshot**. It cannot support temporal validation or establish future prediction performance. A later phase must obtain historical monthly snapshots and run temporal validation before the system may be presented as a validated forecasting system.

## 6. Structural / split notes

- `report_month` is constant -> rejected as a feature.
- Identifiers (`sl_no`, `project_code`, `legacy_ocms_code`, `pmgid`) and `project_name` rejected -> memorisation risk.
- No duplicate rows and no duplicate `project_code` -> one project cannot appear in both train and test.
- Agencies and states are shared across the split, and only one month exists, so any later train/test split measures *within-snapshot* generalisation only.
