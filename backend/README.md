# PAIMANA AI — Backend (Phase 7.1: Foundation Only)

FastAPI backend **foundation** for *PAIMANA AI — Predictive Infrastructure
Risk Monitoring and Early Warning System*.

> **Phase 7.1 scope:** application skeleton, configuration, CORS, `/` and
> `/health`. **No database, no ML endpoints, no frontend, no LLM/RAG, no
> deployment.** The trained models and all ML outputs are untouched by this
> package.

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

Dependencies: `backend/requirements.txt` (`pip install -r backend/requirements.txt`
— already satisfied in the current environment).

## Backend structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, CORS, / and /health
│   ├── config.py         # env-driven settings, project-relative paths (no DB config)
│   ├── api/              # route modules      (empty — later phase)
│   ├── services/         # business logic     (empty — later phase)
│   └── schemas/          # pydantic models    (RootResponse, HealthResponse)
├── tests/
│   └── test_endpoints.py # root + health + CORS tests
├── requirements.txt
└── README.md
```

## Available endpoints

| Method | Path | Purpose | Response |
|---|---|---|---|
| GET | `/` | API information | `service`, `version`, `environment`, `description`, `endpoints`, `phase` |
| GET | `/health` | Liveness check | `{"status": "ok", "service": "PAIMANA AI Backend", "version": ...}` |

**CORS:** restricted to the future React dev server
(`http://localhost:5173`, `http://127.0.0.1:5173`) — not unrestricted.

## Running the tests

From the project root:

```bash
python -m unittest discover -s backend/tests -v
```

Covers: root endpoint, health endpoint, restricted-CORS configuration.

## Current limitations / coming in later phases

- **No database** — no schema, no PostgreSQL/SQLite, no persistence.
- **No ML API integration** — project scoring, risk and early-warning
  endpoints are **not** exposed yet; services/ and api/ are placeholders.
- **No authentication**, no rate limiting, no deployment configuration.
- The React frontend, LLM, and RAG layers are out of scope for this phase.

The existing ML artifacts (`models/`, `ml/`, `outputs/risk/`) remain
read-only inputs for a future phase and are never modified by this backend.
