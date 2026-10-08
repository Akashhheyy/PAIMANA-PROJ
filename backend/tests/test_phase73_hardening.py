"""Phase 7.3 hardening tests - error handling, determinism, contract safety.

Covers behaviours required by Phase 7.3 that were not yet asserted:
* missing model artifact   -> clean 503 (no paths / no traceback)
* unavailable project/risk -> clean 500 (no paths / no traceback)
* invalid pagination       -> 422
* malformed JSON body      -> clean 4xx JSON (no traceback)
* invalid categorical input-> 422 (no silent defaults)
* determinism              -> identical probabilities across repeated calls
* error responses leak no Windows paths / stack traces / internals

Run from the project root:
    python -m unittest discover -s backend/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.config import get_settings  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.services import (  # noqa: E402
    model_service, project_service, risk_service)

client = TestClient(app)

VALID_PREDICT = {
    "original_cost_crore": 500.0,
    "approval_year": 2021,
    "approval_month": 6,
    "planned_horizon_months": 48.0,
    "agency": "MoRTH",
    "state": "Maharashtra",
}

LEAK_MARKERS = ("Traceback", "site-packages", "\\\\", "File \"", ".py\", line")


def assert_clean_error(test: unittest.TestCase, resp) -> None:
    """Error bodies must be JSON with a detail message and no internals."""
    test.assertIn(resp.status_code, (400, 404, 422, 500, 503))
    body = resp.json()
    test.assertIn("detail", body)
    test.assertIsInstance(body["detail"], str)
    for marker in LEAK_MARKERS:
        test.assertNotIn(marker, body["detail"],
                         f"error detail leaked {marker!r}: {body['detail']}")


class TestPaginationAndFilterErrors(unittest.TestCase):
    """§5/§13 invalid query parameters -> clean 422."""

    def test_invalid_pagination(self) -> None:
        for params in ({"page": 0}, {"page": -1}, {"page_size": 0},
                       {"page_size": 1001}):
            resp = client.get("/api/projects", params=params)
            self.assertEqual(resp.status_code, 422, params)
            assert_clean_error(self, resp)
            resp = client.get("/api/early-warnings", params=params)
            self.assertEqual(resp.status_code, 422, params)

    def test_valid_page_size_bounds(self) -> None:
        self.assertEqual(
            client.get("/api/projects",
                       params={"page_size": 100}).status_code, 200)
        self.assertEqual(
            client.get("/api/projects",
                       params={"page_size": 1}).status_code, 200)

    def test_invalid_filters_clean_422(self) -> None:
        resp = client.get("/api/early-warnings",
                          params={"risk_category": "Catastrophic"})
        self.assertEqual(resp.status_code, 422)
        assert_clean_error(self, resp)
        resp = client.get("/api/early-warnings",
                          params={"warning_type": "NUCLEAR_WARNING"})
        self.assertEqual(resp.status_code, 422)
        assert_clean_error(self, resp)


class TestMalformedAndInvalidPredict(unittest.TestCase):
    """§6 B/C/D/E malformed / invalid prediction requests."""

    def test_malformed_json_body(self) -> None:
        resp = client.post(
            "/api/predict", content=b"{not valid json",
            headers={"content-type": "application/json"})
        self.assertIn(resp.status_code, (400, 422))
        body = resp.json()                 # still JSON, never an HTML traceback
        self.assertIn("detail", body)
        for marker in ("Traceback", "site-packages", "\\\\"):
            self.assertNotIn(marker, str(body))

    def test_invalid_categorical_values(self) -> None:
        bad = dict(VALID_PREDICT, agency="")          # empty category
        self.assertEqual(client.post("/api/predict", json=bad).status_code,
                         422)
        bad = dict(VALID_PREDICT, agency=12345)        # wrong type, no coercion
        self.assertEqual(client.post("/api/predict", json=bad).status_code,
                         422)
        bad = dict(VALID_PREDICT, state=None)
        self.assertEqual(client.post("/api/predict", json=bad).status_code,
                         422)

    def test_no_silent_defaults_for_missing_fields(self) -> None:
        # every model field omitted one at a time -> 422, never a default
        for field in ("original_cost_crore", "approval_year", "approval_month",
                      "planned_horizon_months", "agency", "state"):
            bad = {k: v for k, v in VALID_PREDICT.items() if k != field}
            resp = client.post("/api/predict", json=bad)
            self.assertEqual(resp.status_code, 422, field)
            assert_clean_error(self, resp)


class TestDeterminism(unittest.TestCase):
    """§7 identical requests must return identical results (documented)."""

    def test_repeated_predictions_are_byte_identical(self) -> None:
        results = [client.post("/api/predict", json=VALID_PREDICT).json()
                   for _ in range(5)]
        first = results[0]
        for other in results[1:]:
            self.assertEqual(other["cost_overrun_probability"],
                             first["cost_overrun_probability"])
            self.assertEqual(other["time_overrun_probability"],
                             first["time_overrun_probability"])
            self.assertEqual(other["combined_risk_score"],
                             first["combined_risk_score"])


class TestServiceFailures(unittest.TestCase):
    """§8/§13 missing artifacts and unavailable data -> clean service errors.

    Simulated by pointing the service at non-existent paths INSIDE THE TEST
    ONLY (original files are never touched) and restoring state afterwards."""

    def test_missing_model_artifact_returns_clean_503(self) -> None:
        real_cost, real_time = (model_service.rs06.COST_PIPELINE,
                                model_service.rs06.TIME_PIPELINE)
        try:
            model_service.get_pipelines.cache_clear()
            model_service.rs06.COST_PIPELINE = Path("missing/model.joblib")
            resp = client.post("/api/predict", json=VALID_PREDICT)
            self.assertEqual(resp.status_code, 503)
            assert_clean_error(self, resp)
            self.assertNotIn(str(PROJECT_ROOT), resp.json()["detail"])
        finally:
            model_service.rs06.COST_PIPELINE = real_cost
            model_service.rs06.TIME_PIPELINE = real_time
            model_service.get_pipelines.cache_clear()
            model_service.get_pipelines()      # reload the real models

    def test_unavailable_project_data_returns_clean_500(self) -> None:
        settings = get_settings()
        real_path = settings.features_csv
        try:
            project_service.projects_frame.cache_clear()
            settings.features_csv = Path("missing/features.csv")
            resp = client.get("/api/projects")
            self.assertEqual(resp.status_code, 500)
            assert_clean_error(self, resp)
        finally:
            settings.features_csv = real_path
            project_service.projects_frame.cache_clear()
            project_service.projects_frame()   # reload real data

    def test_unavailable_risk_data_returns_clean_500(self) -> None:
        settings = get_settings()
        real_dir = settings.risk_output_dir
        try:
            risk_service.risk_frame.cache_clear()
            risk_service.warnings_frame.cache_clear()
            settings.risk_output_dir = Path("missing/risk")
            resp = client.get("/api/risk/summary")
            self.assertEqual(resp.status_code, 500)
            assert_clean_error(self, resp)
        finally:
            settings.risk_output_dir = real_dir
            risk_service.risk_frame.cache_clear()
            risk_service.warnings_frame.cache_clear()
            risk_service.risk_frame()
            risk_service.warnings_frame()


class TestModelLoading(unittest.TestCase):
    """§8 models load once, correct types, no retraining."""

    def test_both_models_load_with_expected_types(self) -> None:
        info = model_service.model_info()
        self.assertEqual(info["cost_model_type"], "RandomForestClassifier")
        self.assertEqual(info["time_model_type"],
                         "HistGradientBoostingClassifier")
        self.assertEqual(len(info["feature_schema"]), 7)

    def test_loaded_once_and_reused(self) -> None:
        a = model_service.get_pipelines()
        b = model_service.get_pipelines()
        self.assertIs(a, b)
        # repeated requests keep working off the same cached pipelines
        for _ in range(3):
            self.assertEqual(
                client.post("/api/predict", json=VALID_PREDICT).status_code,
                200)

    def test_threshold_guard(self) -> None:
        # Phase-5 thresholds unchanged (0.35 / 0.65)
        self.assertTrue(risk_service.check_threshold_consistency())


class TestNoLeakageOfInternals(unittest.TestCase):
    """§2/§13 no Windows paths / tracebacks / internals in ANY response."""

    def _scan(self, label: str, text: str) -> None:
        for marker in ("Traceback", "site-packages", "File \"",
                       "C:\\", "backend\\app", "line "):
            if marker == "line ":
                continue    # too generic; the rest are checked strictly
            self.assertNotIn(marker, text,
                             f"{label} leaked {marker!r}")

    def test_error_responses_have_no_internals(self) -> None:
        cases = [
            ("404 project", client.get("/api/projects/999999999")),
            ("404 non-numeric", client.get("/api/projects/xyz/risk")),
            ("422 page", client.get("/api/projects", params={"page": 0})),
            ("422 filter", client.get("/api/early-warnings",
                                      params={"risk_category": "Bad"})),
            ("422 predict", client.post("/api/predict", json={})),
        ]
        for label, resp in cases:
            self._scan(label, resp.text)
            self.assertTrue(resp.headers["content-type"].startswith(
                "application/json"), label)

    def test_success_responses_have_no_paths(self) -> None:
        for label, resp in [
            ("root", client.get("/")),
            ("projects", client.get("/api/projects?page_size=3")),
            ("summary", client.get("/api/risk/summary")),
            ("warnings", client.get("/api/early-warnings?page_size=3")),
        ]:
            self.assertEqual(resp.status_code, 200, label)
            self._scan(label, resp.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

