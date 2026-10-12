"""PAIMANA AI - Phase 7.1: FastAPI backend foundation.

Scope of THIS phase (nothing more):
* GET /        -> simple API information
* GET /health  -> liveness check
* CORS restricted to the future React dev server (localhost:5173)

Not built here (later phases): database, ML/project/risk endpoints,
React frontend, LLM, RAG, deployment. Nothing under models/, ml/ or
outputs/risk/ is modified by this application.

Run (from the project root):
    uvicorn backend.app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import dashboard, predictions, projects, risk, warnings
from .config import get_settings
from .schemas import HealthResponse, RootResponse

logger = logging.getLogger("paimana.backend")
settings = get_settings()

ALL_ENDPOINTS = [
    "/",
    "/health",
    "/api/projects",
    "/api/projects/{project_code}",
    "/api/projects/{project_code}/risk",
    "/api/risk/summary",
    "/api/early-warnings",
    "/api/predict",
    "/api/dashboard/progress-distribution",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load trained models ONCE at startup; check (never create) the DB.

    Fail fast if a model artifact is missing (clean message). The database
    is only checked for reachability - schema initialization and snapshot
    import are EXPLICIT commands (python -m backend.app.db.init_db /
    import_snapshot), never performed or destructive at startup."""
    from .services import model_service

    logger.info("startup: loading trained models ...")
    try:
        model_service.get_pipelines()
    except Exception as exc:
        logger.error("startup failed: %s", exc)
        raise RuntimeError(
            "backend startup failed: trained models are unavailable") from None
    info = model_service.model_info()
    logger.info("startup OK: cost=%s time=%s features=%s",
                info["cost_model_type"], info["time_model_type"],
                len(info["feature_schema"]))

    # read-only database reachability check (no migrations/imports at startup)
    from sqlalchemy import text
    from .db.session import SessionLocal
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        logger.info("database reachable: %s", settings.database_url)
    except Exception:
        logger.warning(
            "database not initialized yet - run: "
            "python -m backend.app.db.init_db && "
            "python -m backend.app.db.import_snapshot")
    yield

app = FastAPI(
    title=settings.service_name,
    version=settings.api_version,
    description=(
        "PAIMANA AI backend (Phase 7.2): health/info plus read-only API "
        "access to the existing Phase-4 models, Phase-5 risk scores and "
        "Phase-6 early warnings. No database, no retraining, no new rules."
    ),
    lifespan=lifespan,
)

# --- CORS: allow ONLY the future React development server (Step 5) ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # default: localhost:5173 variants
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=RootResponse, tags=["info"])
def root() -> RootResponse:
    """Root endpoint: simple API information."""
    return RootResponse(
        service=settings.service_name,
        version=settings.api_version,
        environment=settings.environment,
        description=(
            "PAIMANA AI - Predictive Infrastructure Risk Monitoring and "
            "Early Warning System. Exposes the existing Phase-4 models, "
            "Phase-5 risk scores and Phase-6 early warnings read-only."
        ),
        endpoints=ALL_ENDPOINTS,
        phase="7.2-ml-api-integration",
    )


@app.get("/health", response_model=HealthResponse, tags=["info"])
def health() -> HealthResponse:
    """Health/liveness endpoint."""
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.api_version,
    )


# --- Phase 7.2: ML integration routes (Route -> Service -> ML artifact) -----
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(predictions.router, prefix="/api/predict",
                   tags=["predictions"])
app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
app.include_router(warnings.router, prefix="/api/early-warnings",
                   tags=["early-warnings"])

# --- Phase 7.4: dashboard graph data (read-only aggregation) ---------------
app.include_router(dashboard.router, prefix="/api/dashboard",
                   tags=["dashboard"])
