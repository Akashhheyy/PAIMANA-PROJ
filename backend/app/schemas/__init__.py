"""Pydantic response/response models for the API.

Phase 7.1 only defines the root + health shapes; request schemas for the
ML endpoints arrive in a later phase.
"""

from __future__ import annotations

from pydantic import BaseModel


class RootResponse(BaseModel):
    """Response model for GET / (API information)."""

    service: str
    version: str
    environment: str
    description: str
    endpoints: list[str]
    phase: str


class HealthResponse(BaseModel):
    """Response model for GET /health."""

    status: str
    service: str
    version: str
