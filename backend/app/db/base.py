"""SQLAlchemy declarative base and schema-version bookkeeping."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base shared by every model."""


class SchemaVersion(Base):
    """Records applied schema migrations (lightweight, versioned)."""

    __tablename__ = "schema_version"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
