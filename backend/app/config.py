"""PAIMANA AI backend configuration (Phase 7.1 - foundation).

Design rules for this phase:
* Environment-variable driven (all values overridable, nothing hard-coded).
* Project-relative paths only - no absolute Windows paths anywhere.
* NO database configuration yet (that arrives in a later phase).

All paths are derived from this file's location:
    backend/app/config.py -> parents[0]=app, [1]=backend, [2]=project root
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# Project root derived from this file (portable, never an absolute literal).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    """Runtime settings, read from environment variables with safe defaults."""

    def __init__(self) -> None:
        # --- service -------------------------------------------------------
        self.service_name: str = os.getenv(
            "PAIMANA_SERVICE_NAME", "PAIMANA AI Backend")
        self.environment: str = os.getenv("PAIMANA_ENV", "development")
        self.api_version: str = os.getenv("PAIMANA_API_VERSION", "0.1.0")
        self.host: str = os.getenv("PAIMANA_HOST", "127.0.0.1")
        self.port: int = int(os.getenv("PAIMANA_PORT", "8000"))

        # --- project-relative data locations (read-only for the API) ------
        self.project_root: Path = PROJECT_ROOT
        self.models_dir: Path = Path(
            os.getenv("PAIMANA_MODELS_DIR", str(PROJECT_ROOT / "models")))
        self.risk_output_dir: Path = Path(
            os.getenv("PAIMANA_RISK_DIR",
                      str(PROJECT_ROOT / "outputs" / "risk")))
        self.features_csv: Path = Path(
            os.getenv("PAIMANA_FEATURES_CSV",
                      str(PROJECT_ROOT / "data" / "processed"
                          / "paimana_features.csv")))

        # --- CORS: only the future React dev server (Phase 7+) ------------
        self.cors_origins: list[str] = _split_csv(os.getenv(
            "PAIMANA_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173"))

    def public_dict(self) -> dict:
        """Non-sensitive settings safe to expose for diagnostics."""
        return {
            "service": self.service_name,
            "environment": self.environment,
            "version": self.api_version,
            "cors_origins": self.cors_origins,
            "models_dir": str(self.models_dir),
            "risk_output_dir": str(self.risk_output_dir),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton (FastAPI dependency-injection friendly)."""
    return Settings()
