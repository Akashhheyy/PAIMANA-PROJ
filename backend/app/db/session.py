"""Engine/session factory and the FastAPI database dependency.

- Database URL is configurable (env PAIMANA_DATABASE_URL); the default is a
  project-relative SQLite file at <project root>/data/paimana.db (no
  hard-coded absolute paths; portable to PostgreSQL by setting the URL).
- Sessions are created per request via `get_db` (dependency injection),
  committed at the end of the request and rolled back on error.
- SQLite foreign keys are enforced via a connect-time PRAGMA.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings


def _build_engine(url: str) -> Engine:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_fk(dbapi_connection, _record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


# Engine is created lazily on first import of this module; the SQLite file
# itself is only touched on the first actual connection (init/import decide
# when that happens - never an ordinary API request on a fresh checkout).
engine = _build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                            expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, commit/rollback/close."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
