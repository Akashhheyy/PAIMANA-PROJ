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


def tearDownModule() -> None:
    """Dispose the module-level fixture so Windows temp cleanup succeeds."""
    global FIXTURE
    if FIXTURE is not None:
        FIXTURE.dispose()
        FIXTURE = None


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


class TestImport(unittest.TestCase):
    def test_import_counts_and_snapshot(self) -> None:
        f = get_fixture()
        self.assertEqual(f.summary["projects"], 1981)
        self.assertEqual(f.summary["risk_records"], 1981)
        self.assertEqual(f.summary["warning_records"], 1981)
        self.assertEqual(f.summary["null_time_probability"], 354)
        with f.SessionLocal() as db:
            self.assertEqual(db.scalar(
                select(func.count()).select_from(Project)), 1981)
            self.assertEqual(db.scalar(
                select(func.count()).select_from(RiskResult)), 1981)
            self.assertEqual(db.scalar(
                select(func.count()).select_from(EarlyWarning)), 1981)
            snap = db.scalar(select(ImportSnapshot))
            self.assertIsNotNone(snap)
            self.assertEqual(snap.snapshot_id, "2026-04")
            self.assertEqual(snap.status, "completed")

    def test_repeated_import_is_idempotent(self) -> None:
        f = get_fixture()
        with f.SessionLocal() as db:
            import_snapshot(db, f.frames)          # second import
            self.assertEqual(db.scalar(
                select(func.count()).select_from(Project)), 1981)
            self.assertEqual(db.scalar(
                select(func.count()).select_from(RiskResult)), 1981)
            self.assertEqual(db.scalar(
                select(func.count()).select_from(EarlyWarning)), 1981)
            self.assertEqual(db.scalar(select(func.count())
                                       .select_from(ImportSnapshot)), 1)
            snap = db.scalar(select(ImportSnapshot))
            self.assertIn('"projects_new": 0', snap.summary_json)

    def test_null_time_probability_preserved(self) -> None:
        f = get_fixture()
        with f.SessionLocal() as db:
            nulls = db.scalar(select(func.count()).select_from(RiskResult)
                              .where(RiskResult.time_overrun_probability
                                     .is_(None)))
            self.assertEqual(int(nulls), 354)

    def test_failed_import_rolls_back(self) -> None:
        """Mid-write failure -> transaction rolled back, counts intact."""
        f = get_fixture()

        class _Boom:
            def __str__(self):
                raise ValueError("simulated mid-import failure")

        bad_warnings = f.frames["warnings"].copy()
        bad_warnings.loc[bad_warnings.index[0], "warning_type"] = _Boom()
        with f.SessionLocal() as db:
            with self.assertRaises(RuntimeError):
                import_snapshot(db, {**f.frames, "warnings": bad_warnings})
            self.assertEqual(db.scalar(
                select(func.count()).select_from(Project)), 1981)
            self.assertEqual(db.scalar(
                select(func.count()).select_from(EarlyWarning)), 1981)

    def test_validation_rejects_mismatched_sources(self) -> None:
        f = get_fixture()
        bad_features = f.frames["features"].iloc[:-1]   # drop one project
        with self.assertRaises(ImportValidationError):
            validate_frames({**f.frames, "features": bad_features})

    def test_foreign_key_integrity(self) -> None:
        f = get_fixture()
        with f.SessionLocal() as db:
            db.add(RiskResult(project_code=999999999,
                              report_month="April 2026",
                              cost_overrun_probability=0.5,
                              risk_category="Low", score_status="complete",
                              missing_component="none"))
            with self.assertRaises(IntegrityError):
                db.flush()
            db.rollback()


class TestApiOnDatabase(unittest.TestCase):
    """Endpoints served from the temporary imported database."""

    @classmethod
    def setUpClass(cls) -> None:
        app.dependency_overrides[get_db] = override_get_db
        cls.features = pd.read_csv(
            PROJECT_ROOT / "data" / "processed" / "paimana_features.csv")

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.pop(get_db, None)

    def test_project_list_matches_source_count(self) -> None:
        resp = client.get("/api/projects", params={"page_size": 50})
        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["total"], 1981)
        self.assertEqual(body["items"][0]["project_code"], 612786)

    def test_project_search_and_pagination(self) -> None:
        body = client.get("/api/projects",
                          params={"search": "kadapa"}).json()
        self.assertEqual(body["total"], 6)
        page2 = client.get("/api/projects",
                           params={"page": 2, "page_size": 5}).json()
        self.assertEqual(len(page2["items"]), 5)
        self.assertNotEqual(page2["items"][0]["project_code"],
                            client.get("/api/projects",
                                       params={"page_size": 5}
                                       ).json()["items"][0]["project_code"])

    def test_detail_and_404(self) -> None:
        truth = self.features.set_index("project_code")
        body = client.get("/api/projects/706724").json()
        self.assertEqual(body["project_code"], 706724)
        self.assertEqual(body["state"], "Assam")
        # dates come from the DB exactly as the CSV records them
        self.assertEqual(body["target_doc"], str(truth.loc[706724, "target_doc"]))
        self.assertEqual(body["revised_doc"],
                         str(truth.loc[706724, "revised_doc"]))
        # a row with an unrecorded revised date arrives as NULL
        other = client.get("/api/projects/612183").json()
        self.assertTrue(pd.isna(truth.loc[612183, "revised_doc"]))
        self.assertIsNone(other["revised_doc"])
        self.assertEqual(client.get("/api/projects/999999999").status_code,
                         404)
        self.assertEqual(client.get("/api/projects/xyz").status_code, 404)

    def test_risk_lookup_partial_null(self) -> None:
        body = client.get("/api/projects/612183/risk").json()
        self.assertEqual(body["score_status"], "partial")
        self.assertIsNone(body["time_overrun_probability"])
        self.assertEqual(body["missing_component"], "time_overrun_probability")

    def test_risk_summary_matches_artifacts(self) -> None:
        body = client.get("/api/risk/summary").json()
        self.assertEqual((body["total_projects"], body["high_risk_count"],
                          body["medium_risk_count"], body["low_risk_count"],
                          body["partial_incomplete_count"],
                          body["cost_warning_count"], body["time_warning_count"],
                          body["combined_high_risk_warning_count"]),
                         (1981, 765, 575, 641, 354, 380, 1239, 749))

    def test_early_warning_filtering(self) -> None:
        body = client.get("/api/early-warnings",
                          params={"risk_category": "High",
                                  "warning_type": "COST_WARNING",
                                  "page_size": 5}).json()
        self.assertGreater(body["total"], 0)
        self.assertTrue(all(i["risk_category"] == "High"
                            and "COST_WARNING" in i["warning_type"]
                            for i in body["items"]))

    def test_dashboard_distribution_matches_source(self) -> None:
        body = client.get("/api/dashboard/progress-distribution").json()
        self.assertEqual(body["total_projects"], 1981)
        self.assertEqual(sum(b["count"] for b in body["bins"]),
                         body["projects_included"])
        by_label = {b["label"]: b["count"] for b in body["bins"]}
        self.assertEqual(by_label["90-100"], 589)
        self.assertEqual(by_label["0-10"], 272)

    def test_predict_still_works_from_trained_models(self) -> None:
        resp = client.post("/api/predict", json={
            "original_cost_crore": 500.0, "approval_year": 2021,
            "approval_month": 6, "planned_horizon_months": 48.0,
            "agency": "MoRTH", "state": "Maharashtra"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(0.0 <= body["cost_overrun_probability"] <= 1.0)
        self.assertTrue(0.0 <= body["time_overrun_probability"] <= 1.0)
        self.assertEqual(client.post("/api/predict", json={}).status_code,
                         422)


class TestDbBoundaryAndMissing(unittest.TestCase):
    """SQL binning edges (0/10/90/100) and NULL progress on a tiny database."""

    def test_sql_bins_and_null_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = _build_engine(f"sqlite:///{tmp}/edge.db")
            try:
                Base.metadata.create_all(engine)
                from sqlalchemy.orm import sessionmaker as sm
                SessionLocal = sm(bind=engine, expire_on_commit=False)
                codes = [90001, 90002, 90003, 90004, 90005, 90006, 90007]
                progresses = [0.0, 10.0, 10.0001, 90.0, 90.0001, 100.0, None]
                with SessionLocal() as db:
                    for code, progress in zip(codes, progresses):
                        db.add(Project(project_code=code,
                                       project_name=f"Edge {code}",
                                       agency="Test", state="Test",
                                       report_month="April 2026",
                                       physical_progress_pct=progress))
                    db.commit()
                with SessionLocal() as db:
                    out = project_service.progress_distribution(db=db)
                by_label = {b["label"]: b["count"] for b in out["bins"]}
                self.assertEqual(by_label["0-10"], 2)
                self.assertEqual(by_label["10-20"], 1)
                self.assertEqual(by_label["80-90"], 1)
                self.assertEqual(by_label["90-100"], 2)
                self.assertEqual(out["projects_included"], 6)
                self.assertEqual(out["projects_missing_progress"], 1)
                self.assertIsNotNone(out["mean_progress"])
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)



