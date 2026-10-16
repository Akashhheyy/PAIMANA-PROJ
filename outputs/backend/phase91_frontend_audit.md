# PAIMANA AI — Phase 9.1: Frontend Audit Report

Scope: **audit only**. Nothing was created, edited, deleted, renamed or
installed. No backend, database, model, dataset or risk artifact was touched
(`git status` clean after inspection). No API fields were invented — every
field below was read from the actual schemas/CSVs.

## 1. Existing frontend status

**No frontend exists.**

- Workspace top level: `.git backend data ml models outputs tests` — there is
  **no `frontend/` directory**.
- No `package.json`, `vite.config.*`, `next.config.*` or `angular.json`
  anywhere in the workspace; no `.ts/.tsx/.js/.jsx/.vue` source files
  (outside `node_modules`, of which there are none).
- **No API client and no backend proxy exist.**
- Toolchain available but unused: `node v24.14.0`, `npm 11.9.0` (global
  packages: only `cline`; no chart libraries).
- Python-side plotting (`plotly 6.7.0`, `matplotlib 3.10.8`) exists but is
  server-side only — irrelevant to browser rendering.

## 2. Backend readiness for frontend integration

The backend (expects `127.0.0.1:8000`; config env-driven, project-relative) is
**fully graph-ready with zero gaps**:

- `GET /` + `GET /health` → service/version info and liveness.
- `GET /api/projects?page=&page_size=(1..100)&search=` → paginated list.
- `GET /api/projects/{project_code}` → detail (404 when unknown).
- `GET /api/projects/{project_code}/risk` → **everything the risk pie needs**.
- `GET /api/risk/summary` → dashboard totals/counts.
- `GET /api/early-warnings?risk_category=&warning_type=&page=&page_size=`
  → filtered warning rows (invalid filters → clean 422).
- `GET /api/dashboard/progress-distribution?agency=&state=` → pre-binned
  histogram (10 bins, sum == included, missing counted not zero-filled).
- Models load once at startup (`get_pipelines`); every endpoint reads the
  existing SQLite via injected `get_db` sessions (file
  `data/paimana.db` present).
- CORS already allows the React dev server (`http://localhost:5173`,
  `http://127.0.0.1:5173`) — **no proxy needed**; direct `fetch`/axios calls
  from Vite dev will work.
- Pinned deps (`fastapi==0.115.6`, `uvicorn==0.34.0`, `httpx==0.28.1`,
  `pydantic>=2.0`, `sqlalchemy==2.0.36`); 77 backend tests.
- Response schemas verified by reading `backend/app/schemas/*.py` directly
  (no fields invented, none left unverified).

## 3. Graph 1 — Overall Project Progress (data supply: COMPLETE)

Available fields (verified in `paimana_features.csv`, 1,981 × 32):
`physical_progress_pct` — 1,981 values, **0 missing**, float, range 0–100;
`agency` — 181 unique; `state` — 107 unique; `report_month` = `"April 2026"`.
- `GET /api/dashboard/progress-distribution` returns the pre-computed
  10-bin histogram (`0-10`…`90-100`, final bin includes exactly 100%),
  `total_projects: 1981`, `projects_included`, `projects_missing_progress`,
  `mean_progress`, `median_progress`, `snapshot_label: "April 2026"`,
  plus `agency_filter`/`state_filter` echoes and 422 validation of filters.
- Total row count must be displayed from `total_projects`; the snapshot
  caption must read the April 2026 label.
- Agency/state filtering is data-supported (exact-match query params);
  per audit record, no historical per-month progress columns exist, so no
  month-by-month trend may be rendered.

## 4. Graph 2 — Per-project risk pie (data supply: COMPLETE)

Verified fields in `ProjectRiskResponse`:
`project_code, project_name, state, agency, report_month,
cost_overrun_probability (float|null), time_overrun_probability
(float|null), combined_risk_score (float|null), risk_category,
score_status, missing_component, warning_type, warning_priority(_label),
warning_message, risk_indicators, recommended_action`.
- Artifact counts confirm the chart rules: `cost_p` complete (1,981),
  `time_p` NULL for exactly **354** partial rows (never 0),
  category split High 765 / Medium 575 / Low 641, status 1,627 complete /
  354 partial.
- The chart must key strictly by `project_code` (the `/risk` endpoint's own
  lookup), render an explicit "unavailable — not 0" state for missing time
  probability, keep combined score and category as separate displays
  (category is High/Medium/Low only), and label the pie so the two slices
  are read as **overlapping model-estimated risks, not parts summing to 100%**.

## 5. Reusable vs. to-be-built

Reusable (all exist, no changes needed): the seven endpoints above, their
pydantic schemas (`schemas/*.py` — exact response contracts listed in §4),
the CORS setup for `localhost:5173`, the `/docs` OpenAPI reference, and the
77-test backend suite that guards these contracts.

To be built (nothing exists): the entire `frontend/` tree —
`package.json` + Vite React-TS scaffold, router (`/` dashboard,
`/projects/:project_code` detail), API client (base URL `127.0.0.1:8000`),
state handling, components (progress histogram, pie chart + score/category
displays, project list with search/pagination, filter controls),
light-theme styling, and frontend tests.

## 6. Phased implementation plan (recommended next step: Phase 9.2)

1. Scaffold `frontend/` (Vite + React + TypeScript; strict TS), install only
   a router, an HTTP client, and **one** chart library sized for two simple
   charts (a lightweight bar/pie-capable library is sufficient — no
   dashboard-framework package and no server chart dependency, which would
   only duplicate the backend's existing aggregation endpoints).
2. Build the API client layer mirroring `RiskSummaryResponse`,
   `ProjectList/Detail/RiskResponse`, `EarlyWarningListResponse`,
   `ProgressDistributionResponse` (7 schemas above) with typed nullability
   for the 354 time-probability gaps.
3. Build the dashboard page (Graph 1 histogram from
   `/api/dashboard/progress-distribution`, summary strip from
   `/api/risk/summary`, explicit "April 2026 snapshot" caption).
4. Build the project list (search + pagination) and project-detail page
   (Graph 2 pie from `/api/projects/{code}/risk` with the null-handling and
   non-100% labeling rules of §4, plus warning/recommendation panels).
5. Style as a clean light professional theme suitable for SIH demo;
   verify against the live backend (`127.0.0.1:8000`) and `/docs`.

## 7. Dashboard styling direction

Clean light professional theme for SIH demonstration: neutral light
background, high-contrast ink text, one restrained accent for brand/primary
actions plus semantic risk colors (red/amber/green) reserved for category
and warning states; generous whitespace, card-based KPI strip, tabular
numerals, and visible "April 2026 snapshot" captioning — no dark mode, no
decorative gradients.

---
Audit performed read-only on 2026-10-16; no files created/edited/deleted/
renamed/installed beyond **this report itself**; backend, database, ML
models, datasets and risk artifacts untouched.

