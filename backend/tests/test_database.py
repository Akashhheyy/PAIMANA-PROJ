"""Phase 8 tests - SQLite/SQLAlchemy layer (temporary databases only).

Covers: connection/init, schema creation + migration idempotency, snapshot
import, idempotent re-import, transaction rollback on failed import,
foreign-key integrity, and API compatibility against the imported data.

Run from the project root:
    python -m unittest discover -s backend/tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from backend.app.db import migrations as mig  # noqa: E402
from backend.app.db.base import Base, SchemaVersion  # noqa: E402
from backend.app.db.import_snapshot import (  # noqa: E402
    ImportValidationError, import_snapshot, load_snapshot_frames,
    validate_frames)
from backend.app.db.models import (EarlyWarning, ImportSnapshot,  # noqa: E402
                                   Project, RiskResult)
from backend.app.db.session import _build_engine, get_db  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.services import project_service  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(app)


class _Fixture:
    """One temporary SQLite database, imported ONCE for the whole module."""

    def __init__(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(prefix="paimana_test_")
        self.engine = _build_engine(f"sqlite:///{self.tmpdir.name}/test.db")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False,
                                         expire_on_commit=False)
        self.frames = load_snapshot_frames(PROJECT_ROOT)
        with self.SessionLocal() as db:
            self.summary = import_snapshot(db, self.frames)

    def dispose(self) -> None:
        self.engine.dispose()
        self.tmpdir.cleanup()


FIXTURE: _Fixture | None = None


def get_fixture() -> _Fixture:
    global FIXTURE
    if FIXTURE is None:
        FIXTURE = _Fixture()
    return FIXTURE


def override_get_db():
    session = get_fixture().SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class TestSchemaAndMigrations(unittest.TestCase):
    def test_schema_creation_and_migration_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = _build_engine(f"sqlite:///{tmp}/mig.db")
            try:
                applied1 = mig.apply_pending(engine)
                self.assertEqual(applied1, ["0001_initial"])
                with Session(engine) as db:
                    versions = db.scalars(select(SchemaVersion)).all()
                    self.assertEqual([v.version for v in versions],
                                     ["0001_initial"])
                    tables = db.execute(text(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )).scalars().all()
                    for needed in ("projects", "risk_results", "early_warnings",
                                   "import_snapshots", "schema_version"):
                        self.assertIn(needed, tables)
                applied2 = mig.apply_pending(engine)   # rerun: nothing pending
                self.assertEqual(applied2, [])
            finally:
                engine.dispose()


# END_DB_TESTS_A
