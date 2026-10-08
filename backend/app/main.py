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

from .api import predictions, projects, risk, warnings
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
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load trained models and existing ML outputs ONCE at startup.

    Fail fast with a clean message if an artifact is missing; afterwards the
    cached objects are reused by every request (no per-request joblib.load)."""
    from .services import model_service, project_service, risk_service

    logger.info("startup: loading trained models and existing ML outputs ...")
    try:
        model_service.get_pipelines()
        risk_service.risk_frame()
        risk_service.warnings_frame()
        project_service.projects_frame()
    except Exception as exc:
        logger.error("startup failed: %s", exc)
        raise RuntimeError(
            "backend startup failed: trained models or ML outputs are "
            "unavailable") from None
    info = model_service.model_info()
    logger.info("startup OK: cost=%s time=%s features=%s",
                info["cost_model_type"], info["time_model_type"],
                len(info["feature_schema"]))
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
