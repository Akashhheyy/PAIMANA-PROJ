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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .schemas import HealthResponse, RootResponse

settings = get_settings()

app = FastAPI(
    title=settings.service_name,
    version=settings.api_version,
    description=(
        "PAIMANA AI backend foundation (Phase 7.1). Health and API-info "
        "endpoints only; database and ML API integration come in later "
        "phases."
    ),
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
            "Early Warning System. Backend foundation only: ML endpoints "
            "are not exposed yet."
        ),
        endpoints=["/", "/health"],
        phase="7.1-backend-foundation",
    )


@app.get("/health", response_model=HealthResponse, tags=["info"])
def health() -> HealthResponse:
    """Health/liveness endpoint."""
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.api_version,
    )
