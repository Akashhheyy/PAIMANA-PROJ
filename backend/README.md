# PAIMANA AI — Backend (Phase 7.1: Foundation Only)

FastAPI backend **foundation** for *PAIMANA AI — Predictive Infrastructure
Risk Monitoring and Early Warning System*.

> **Phase 7.1 scope:** application skeleton, configuration, CORS, `/` and
> `/health`. **No database, no ML endpoints, no frontend, no LLM/RAG, no
> deployment.** The trained models and all ML outputs are untouched by this
> package.

## Architecture

```
HTTP request
    └─ Route        (backend/app/api/*.py)        validation, HTTP mapping
        └─ Service  (backend/app/services/*.py)   logic, one lru_cache load
            └─ ML artifact (models/*.joblib, outputs/risk/*.csv, data/...)
```

- `model_service` — `joblib.load` runs **once** at startup (cached singleton);
  predictions use the pipeline's own `feature_names_in_` column order.
  Never retrains, never writes model files.
- `risk_service` — counts straight from `project_risk_scores.csv` and
  `early_warning_results.csv`; warning/type names imported from `ml/06`/`ml/07`
  so thresholds **cannot drift** from the ML layer (0.35 / 0.65, probes ≥ 0.65).
- `project_service` — reads `paimana_features.csv` once, joins the existing
  Phase-5 risk category.

## How to start the backend

Run from the **project root** (the folder containing `backend/`):

```bash
uvicorn backend.app.main:app --reload --port 8000
```

Then open:

- API docs (Swagger): <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>

Optional environment variables (all have safe defaults — see `app/config.py`):

| Variable | Default |
|---|---|
| `PAIMANA_SERVICE_NAME` | `PAIMANA AI Backend` |
| `PAIMANA_ENV` | `development` |
| `PAIMANA_API_VERSION` | `0.1.0` |
| `PAIMANA_HOST` | `127.0.0.1` |
| `PAIMANA_PORT` | `8000` |
| `PAIMANA_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |
| `PAIMANA_MODELS_DIR` | `<project root>/models` (relative) |
| `PAIMANA_RISK_DIR` | `<project root>/outputs/risk` (relative) |
| `PAIMANA_DATABASE_URL` | `sqlite:///<project root>/data/paimana.db` (relative; set to a PostgreSQL URL to port) |

Dependencies: `backend/requirements.txt` (`pip install -r backend/requirements.txt`
— fastapi, uvicorn, httpx, pydantic, watchfiles, **sqlalchemy**).

## Database (Phase 8)

Local SQLite + SQLAlchemy, read by the API through dependency-injected
sessions (`get_db`). **No database work happens at application startup.**

```powershell
# 1. (optional) point elsewhere; default is data/paimana.db (git-ignored)
$env:PAIMANA_DATABASE_URL = "sqlite:///C:/path/to/paimana.db"

# 2. create/upgrade the schema (safe, never destructive)
python -m backend.app.db.init_db

# 3. import the April 2026 snapshot (idempotent - reruns update, never duplicate)
python -m backend.app.db.import_snapshot

# 4. inspect what is stored
python -m backend.app.db.inspect_db
```

Tables: `projects` (1 row per project; `project_code` unique), `risk_results`
(`(project_code, report_month)` unique; `time_overrun_probability` NULL where
the time label was unknown — never 0), `early_warnings` (same uniqueness;
identity fields live in `projects`, not duplicated), `import_snapshots`
(provenance: snapshot id `2026-04`, source files, counts), `schema_version`
(applied migrations; rerunning init is a no-op).

**Future monthly snapshots:** add a new migration only if the schema must
change, then run a snapshot import for the new `report_month` — composite
uniqueness keeps each period's rows separate, and old rows are never deleted.

Database file: `data/paimana.db` (~3 MB, **git-ignored** — each environment
builds its own via the commands above).

Current limitations: SQLite single-writer semantics under heavy concurrency;
no auth/rate limiting; the API serves the April 2026 snapshot associations
(prototype, not verified future forecasts).

## Backend structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, CORS, / and /health
│   ├── config.py         # env-driven settings, project-relative paths (+DB URL)
│   ├── db/               # Phase 8: session, models, migrations, init_db,
│   │                     # import_snapshot, inspect_db
│   ├── api/              # projects, predictions, risk, warnings, dashboard
│   ├── services/         # model_service, risk_service, project_service
│   └── schemas/          # Root/Health + projects, predictions, risk, warnings
├── tests/
│   ├── test_endpoints.py # root + health + CORS tests (Phase 7.1)
│   ├── test_api_phase72.py  # ML-integration endpoints (Phase 7.2)
│   ├── test_phase73_hardening.py  # error handling, determinism (Phase 7.3)
│   ├── test_dashboard_graphs.py  # progress distribution (Phase 7.4)
│   └── test_database.py  # DB layer + DB-backed API tests (Phase 8)
├── requirements.txt
└── README.md
```

## Available endpoints

| Method | Path | Purpose | Response |
|---|---|---|---|
| GET | `/` | API information | `service`, `version`, `environment`, `description`, `endpoints`, `phase` |
| GET | `/health` | Liveness check | `{"status": "ok", "service": "PAIMANA AI Backend", ...}` |
| GET | `/api/projects` | Paginated project list (`page`, `page_size`, `search`) | `items`, `page`, `page_size`, `total` |
| GET | `/api/projects/{project_code}` | Project detail (404 if unknown) | plan/status fields + risk category |
| GET | `/api/projects/{project_code}/risk` | Existing Phase-5 score + Phase-6 warning | probabilities, category, warning, indicators, action |
| GET | `/api/risk/summary` | Counts from the existing outputs | total/high/medium/low/partial + cost/time/combined warning counts |
| GET | `/api/early-warnings` | Existing warnings (`risk_category`, `warning_type`, `page`, `page_size`) | warning rows as generated by Phase 6 |
| GET | `/api/dashboard/progress-distribution` | Progress histogram (`agency`, `state` filters) | `snapshot_label`, totals, 10 bins, mean/median (Phase 7.4) |
| POST | `/api/predict` | Phase-4 plan-only prediction | cost/time probabilities, combined score, category |

Architecture: `Route → Service → existing ML artifact/logic → response schema`.
Models are loaded **once** at startup (cached); no retraining, no new risk
formulas, no new warning rules — thresholds come from `ml/06`/`ml/07`.

**CORS:** restricted to the future React dev server
(`http://localhost:5173`, `http://127.0.0.1:5173`) — not unrestricted.

## Running the tests

From the project root:

```bash
python -m unittest discover -s backend/tests -v
```

Covers: root, health, CORS, project list/detail/404, risk summary (verified
against the existing CSVs), early-warning filters, project risk thresholds,
predict valid/invalid input, model-caching/no-retrain guards, Phase-7.3
error handling (invalid pagination/filters, malformed JSON, missing
artifacts → clean JSON errors, no internals leaked), and determinism.

## Example API calls

```bash
# project list + search + pagination
curl "http://localhost:8000/api/projects?page=1&page_size=2&search=kadapa"

# project detail (404 when the code is unknown)
curl http://localhost:8000/api/projects/612786

# existing risk score + warning for one project
curl http://localhost:8000/api/projects/612786/risk

# summary counts from the existing Phase-5/6 outputs
curl http://localhost:8000/api/risk/summary
# {"total_projects":1981,"high_risk_count":765,"medium_risk_count":575,
#  "low_risk_count":641,"partial_incomplete_count":354,"cost_warning_count":380,
#  "time_warning_count":1239,"combined_high_risk_warning_count":749}

# existing early warnings (filters: risk_category, warning_type)
curl "http://localhost:8000/api/early-warnings?risk_category=High&warning_type=COST_WARNING"

# April-2026 physical-progress distribution (10 bins; optional agency/state filters)
curl "http://localhost:8000/api/dashboard/progress-distribution?agency=MoRTH"
```

## Prediction request structure (`POST /api/predict`)

Exactly the Phase-4 plan-only feature schema — every field required except
`log1p_original_cost`, which is derived server-side with the Phase-3
`np.log1p` formula when omitted. Missing/invalid fields return **422**
(nothing is silently defaulted):

```bash
curl -X POST http://localhost:8000/api/predict \
  -H "Content-Type: application/json" \
  -d '{"original_cost_crore":500.0,"approval_year":2021,"approval_month":6,
       "planned_horizon_months":48.0,"agency":"MoRTH","state":"Maharashtra"}'
```

## Response structure (`PredictionResponse`)

```json
{
  "cost_overrun_probability": 0.2218,
  "time_overrun_probability": 0.9995,
  "cost_probability_available": true,
  "time_probability_available": true,
  "combined_risk_score": 0.6107,
  "score_status": "complete",
  "missing_component": "none",
  "risk_category": "Medium"
}
```

All probabilities lie in `[0,1]`; `risk_category` follows the existing ML
thresholds (Low < 0.35 ≤ Medium < 0.65 ≤ High). Missing model artifacts yield
a clean 503, unavailable data a clean 500 — both as JSON without stack
traces or filesystem paths.

## Current limitations / coming in later phases

- **No database** — data is read from the existing generated CSVs (read-only).
  **Database integration is the next phase.**
- This backend serves only the **April 2026 PAIMANA snapshot**: scores are
  model-estimated within-snapshot associations, not verified future forecasts.

## Current limitations / coming in later phases

- **No database** — data is read from the existing generated CSVs (read-only).
- Predictions use the **plan-only** schema (7 Phase-4 features); `log1p_original_cost`
  is derived server-side with the exact Phase-3 formula when omitted.
- Missing request fields return **422** — nothing is silently defaulted.
- **No authentication**, rate limiting, or deployment configuration.
- React frontend, LLM, and RAG layers are out of scope so far.

The existing ML artifacts (`models/`, `ml/`, `outputs/risk/`) are strictly
read-only inputs and are never modified by this backend.
