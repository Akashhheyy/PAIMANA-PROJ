# PAIMANA AI — Phase 7.4 Prompt 1: Dashboard Graph Design & Data Audit

Scope: audit only. No frontend built, no backend changed, no model touched.
Data: April 2026 PAIMANA snapshot (1,981 projects).

## 1. Existing frontend status

**No frontend exists.**

- Top-level directories: `.git`, `backend`, `data`, `ml`, `models`, `outputs`,
  `tests` — there is no `frontend/` directory.
- No `package.json`, `vite.config.*`, `next.config.*` or `angular.json`
  anywhere in the workspace (excluding `node_modules`, of which none exist).
- Consequently there is nothing to reuse frontend-side; the two graphs will
  require a fresh frontend scaffold in a later prompt (not this one).
- Python-side charting libraries already available: **plotly 6.7.0**,
  matplotlib 3.10.8. Not installed: dash, streamlit, altair, bokeh.

## 2. Available fields for the dashboard progress graph (Graph 1)

Source of truth: `data/processed/paimana_features.csv` (identical
`physical_progress_pct` also in `paimana_clean.csv`).

| Field | Status | Details |
|---|---|---|
| `physical_progress_pct` | complete | 1,981 values, **0 missing**, float, range 0–100, mean **60.2**, median **70.0** |
| `agency` | filter | 181 unique values |
| `state` | filter | 107 unique values (incl. 191 `Multi-States (...)` rows) |
| `report_month` | label | constant `"April 2026"` → the snapshot caption |

Actual verified distribution (10-point bins, final bin inclusive, sums to 1,981):

| Progress range | 0–10 | 10–20 | 20–30 | 30–40 | 40–50 | 50–60 | 60–70 | 70–80 | 80–90 | 90–100 |
|---|---|---|---|---|---|---|---|---|---|---|
| Projects | 272 | 124 | 112 | 119 | 112 | 130 | 125 | 169 | 229 | **589** |

- 97 projects sit at exactly **100%**; 95 at exactly **0%**.
- **Binning pitfall (verified):** `[90,100)` excludes the 97 rows at 100.0
  (bin sum 1,884). The final bin must be inclusive → `(90,100]` gives 589 and
  a total of exactly 1,981. The implementation must assert `sum(bins)==total`.
- **No historical/monthly progress columns exist** → month-by-month trends are
  impossible and must not be fabricated (per prompt).

## 3. Available fields for each project's risk pie chart (Graph 2)

Source of truth: `outputs/risk/project_risk_scores.csv` +
`outputs/risk/early_warning_results.csv`, exposed by the API.

| Field | Status |
|---|---|
| `cost_overrun_probability` | complete for all 1,981 (0 null) |
| `time_overrun_probability` | **null for 354 rows** (time label unknown → `score_status=partial`) |
| `combined_risk_score` | complete for all 1,981 (never zero-filled) |
| `risk_category` | High 765 / Medium 575 / Low 641 (thresholds 0.65 / 0.35) |
| `score_status` | complete 1,627 / partial 354 |
| `missing_component` | `none` or `time_overrun_probability` |
| `warning_type`, `warning_priority(+_label)`, `warning_message`, `risk_indicators`, `recommended_action` | present (Phase 6) |
| identity: `project_code`, `project_name`, `state`, `agency`, `report_month` | present |

**Semantics that must be preserved:** cost and time probabilities are two
independent model outputs for the *same* project — **overlapping risks, not
mutually exclusive slices of a whole**; they must never be normalized to sum
to 100%.

## 4. Existing endpoints that can supply the data

| Graph | Endpoint | Verdict |
|---|---|---|
| Graph 2 (pie) | `GET /api/projects/{project_code}/risk` | **COMPLETE — no change needed.** Returns both probabilities (nullable), combined score, category, score status/missing component, warning fields, indicators, identity. Verified `ProjectRiskResponse` schema fields (17). |
| Graph 2 (detail context) | `GET /api/projects/{project_code}` | Provides progress/status context for the same page (`ProjectDetail` includes `physical_progress_pct`). |
| Graph 1 (total) | `GET /api/risk/summary` | Supplies `total_projects` (1,981) and category counts only — no progress data. |
| Graph 1 (per-project) | `GET /api/projects` | Paginated list with `state`/`agency` (filters) but **`ProjectSummary` has NO `physical_progress_pct`** (verified item keys: `agency, project_code, project_name, report_month, risk_category, state`). |
| Graph 1 (progress) | `GET /api/projects/{code}` | Has `physical_progress_pct`, but only one project per call — 1,981 calls for a histogram is not viable. |

## 5. Missing backend capabilities

**One gap only** (Graph 1); Graph 2 is fully served today.

`GET /api/projects` items do not carry `physical_progress_pct`, and no
aggregate endpoint exists, so the dashboard cannot obtain the progress
distribution without 1,981 per-project calls.

**Smallest required change (proposed — not implemented in this prompt):**

```
GET /api/dashboard/progress-distribution?agency=<optional>&state=<optional>
→ {
    "total_projects": 1981,          // filtered total
    "missing_values": 0,             // excluded from bins, reported, never zero-filled
    "bins": [{"label":"0-10","count":272}, ... {"label":"90-100","count":589}],
    "mean_progress": 60.2, "median_progress": 70.0,
    "report_month": "April 2026",
    "snapshot_label": "April 2026 snapshot"
  }
```

- Implementation: one small pure function in the existing
  `project_service` (reuses the cached `projects_frame()`), one route module
  `backend/app/api/dashboard.py`, one schema, one router registration, tests.
- Reads CSV values only — **no model inference, no risk formula, no warning
  threshold is duplicated or changed.**
- Optional later: `GET /api/dashboard/facets` (distinct agency/state lists)
  if the filter UI needs them; not required if the filter is a query param
  on the endpoint above.
- Alternative rejected as insufficient alone: adding
  `physical_progress_pct` to `ProjectSummary` still forces the client to page
  through 1,981 rows (20+ requests at `page_size=100`).

## 6. Recommended chart types and their interpretation

**Graph 1 — Overall Project Progress (general dashboard):**
- **Vertical bar histogram** over the 10 verified bins above (horizontal
  bars equally acceptable). Best for distribution shape: the strong right
  skew (589 projects at 90–100%) and the 0–10% tail (272, including 95
  not-yet-started) are immediately visible.
- Must display: **total N = 1,981** (or the filtered total), the caption
  **“April 2026 snapshot”**, and per-bar counts.
- Do **not** use a line/area chart — there is no time axis in the data and a
  trend line would be fabricated.
- Optional aggregates: mean 60.2 / median 70.0 markers.
- Filtering by `agency`/`state` is supported by the data (181/107 values)
  through the proposed endpoint's query parameters.

**Graph 2 — Individual Project Risk Pie:**
- Donut/pie with **two segments: cost-overrun probability vs time-overrun
  probability**, each labelled with *its own* probability and drawn only
  from the selected project's row (`project_code`-keyed).
- Required UI interpretation text: *“Cost and time probabilities are
  independent model estimates of the same project — they overlap and do NOT
  sum to 100%.”* Segment angles must not imply composition (e.g. fixed 50/50
  angles with colour intensity by probability, or two labelled gauges in a
  donut; the legend carries the numeric probabilities).
- **Combined risk score shown separately** (gauge or numeric chip) — it is
  the Phase-5 equal-weighted score, not a slice of the pie.
- **Risk category badge**: High / Medium / Low (existing thresholds
  0.65 / 0.35 unchanged).
- **Partial/unavailable**: when `score_status=partial` (time probability is
  null), show the cost segment normally and the time segment as a grey,
  hatched “unavailable” segment labelled *“time risk unavailable — not 0”*
  (or omit it with an explicit note). The combined score remains displayable
  because the Phase-5 partial rule already computed it — never zero-filled.

## 7. Data-quality limitations

1. **Single April 2026 snapshot** — no history exists; any “trend” would be
   fabricated. Both graphs must be captioned as a snapshot.
2. Progress is **reported** data (0–100, complete, self-reported): 97 rows at
   exactly 100%, 95 at 0% — plausible but unaudited here.
3. **Bin edge pitfall**: the final bin must be inclusive of 100 or 97
   projects disappear (verified: 1,884 vs 1,981 with `[90,100)`). The
   implementation must assert `sum(bins) == total_projects`.
4. **354 projects (17.9%) have no time-overrun probability** (unknown time
   label). Missing ≠ zero — the pie must show these as unavailable.
5. Probabilities are **uncalibrated model outputs** (Phase-4 plan-only
   models): model-estimated associations, not confirmed future events, and
   not parts of a whole.
6. `state` has 107 values incl. 191 multi-state rows; `agency` has 181 —
   filter UIs need multi-select/top-N handling; filtered bin sums must be
   asserted equal to the filtered total.
7. Risk categories/warnings come from Phases 5–6 unchanged; the graphs are
   read-only views of those artifacts.

## 8. Proposed implementation files (for Prompts 2/3 — not created now)

Backend (the smallest change from §5):
- `backend/app/api/dashboard.py` — new router (1 GET route)
- `backend/app/schemas/dashboard.py` — `ProgressDistributionResponse`
- `backend/app/services/project_service.py` — add a pure binning function
  (reuses `projects_frame()` cache; no ML imports)
- `backend/app/main.py` — register the router + add to `ALL_ENDPOINTS`
- `backend/tests/test_dashboard_graphs.py` — bin-sum == total, filter
  behaviour, missing-value reporting, pie-endpoint contract

Frontend (to be scaffolded in a later prompt — none exists today):
- `frontend/` (Vite + React, subject to project conventions decided then)
- `ProgressDistributionChart` (Graph 1), `RiskPieChart` (Graph 2)
- Dashboard page (Graph 1 + total) and project details page (Graph 2)
- Chart-library choice belongs to the next prompt; note `plotly 6.7.0` is
  available in the Python environment if server-side rendering were preferred.

## 9. Confirmation that existing models and data remain unchanged

SHA-256 verified **before any Phase 7.4 work** (and this prompt changed
nothing except creating this report):

| File | Status |
|---|---|
| `PAIMANA_April_2026_Dataset.csv` (`708A2FD9…`) | UNCHANGED |
| `data/processed/paimana_clean.csv` (`A7F330AC…`) | UNCHANGED |
| `data/processed/paimana_features.csv` (`57819774…`) | UNCHANGED |
| `models/cost_overrun/pipeline.joblib` (`8769F00F…`) | UNCHANGED |
| `models/time_overrun/pipeline.joblib` (`450847CF…`) | UNCHANGED |
| `outputs/risk/project_risk_scores.csv` (`2BC562BE…`) | UNCHANGED |
| `outputs/risk/early_warning_results.csv` (`9C6AABF8…`) | UNCHANGED |

No model retraining, no algorithm/formula/threshold changes, no database,
no LLM/RAG, no deployment. This audit is the only artifact produced by
Prompt 1; the frontend and Prompt 2/3 work have **not** been started.


