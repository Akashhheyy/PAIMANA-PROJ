"""Phase 7.2 tests - ML integration API (10 required cases + guards).

Run from the project root:
    python -m unittest discover -s backend/tests -v
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402
from backend.app.services import model_service  # noqa: E402

client = TestClient(app)

VALID_PREDICT = {
    "original_cost_crore": 500.0,
    "approval_year": 2021,
    "approval_month": 6,
    "planned_horizon_months": 48.0,
    "agency": "MoRTH",
    "state": "Maharashtra",
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def band_of(score: float) -> str:
    """Phase-5 thresholds: Low < 0.35 <= Medium < 0.65 <= High."""
    if score < 0.35:
        return "Low"
    if score < 0.65:
        return "Medium"
    return "High"


class TestBasicEndpoints(unittest.TestCase):
    """(1) GET /   (2) GET /health"""

    def test_root(self) -> None:
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["service"], "PAIMANA AI Backend")
        self.assertIn("/api/predict", body["endpoints"])

    def test_health(self) -> None:
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "PAIMANA AI Backend")


class TestProjectEndpoints(unittest.TestCase):
    """(3) list  (4) valid detail  (5) invalid detail"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.list_resp = client.get("/api/projects?page=1&page_size=5")
        cls.list_body = cls.list_resp.json()

    def test_project_list(self) -> None:
        self.assertEqual(self.list_resp.status_code, 200)
        for key in ("items", "page", "page_size", "total"):
            self.assertIn(key, self.list_body)
        self.assertEqual(self.list_body["page"], 1)
        self.assertEqual(self.list_body["page_size"], 5)
        self.assertEqual(len(self.list_body["items"]), 5)
        self.assertGreater(self.list_body["total"], 1000)
        item = self.list_body["items"][0]
        for key in ("project_code", "project_name", "state", "agency",
                    "report_month", "risk_category"):
            self.assertIn(key, item)

    def test_project_list_pagination_total_matches_csv(self) -> None:
        expected = len(pd.read_csv(
            PROJECT_ROOT / "data" / "processed" / "paimana_features.csv"))
        self.assertEqual(self.list_body["total"], expected)

    def test_project_search(self) -> None:
        resp = client.get("/api/projects", params={"search": "airport"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreater(body["total"], 0)
        self.assertLessEqual(body["total"], self.list_body["total"])

        def matches(item: dict) -> bool:
            haystack = f"{item['project_name']} {item['state']} " \
                       f"{item['agency']} {item['project_code']}".lower()
            return "airport" in haystack

        # search covers name, state, agency and code - any may match
        self.assertTrue(all(matches(it) for it in body["items"]))

    def test_valid_project_detail(self) -> None:
        code = self.list_body["items"][0]["project_code"]
        resp = client.get(f"/api/projects/{code}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["project_code"], code)
        for key in ("project_name", "state", "agency", "approval_date",
                    "target_doc", "original_cost_crore",
                    "cumulative_expenditure_crore", "physical_progress_pct"):
            self.assertIn(key, body)

    def test_invalid_project_returns_404(self) -> None:
        self.assertEqual(client.get("/api/projects/999999999").status_code, 404)
        self.assertEqual(client.get("/api/projects/not-a-code").status_code, 404)


class TestRiskSummary(unittest.TestCase):
    """(6) GET /api/risk/summary - must match the existing outputs exactly."""

    def test_summary_matches_existing_outputs(self) -> None:
        resp = client.get("/api/risk/summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        risk = pd.read_csv(
            PROJECT_ROOT / "outputs" / "risk" / "project_risk_scores.csv")
        warns = pd.read_csv(
            PROJECT_ROOT / "outputs" / "risk" / "early_warning_results.csv")
        cat = risk["risk_category"].value_counts()

        def n_type(name: str) -> int:
            return int(warns["warning_type"].str.split("|").apply(
                lambda xs: name in xs).sum())

        self.assertEqual(body["total_projects"], len(risk))
        self.assertEqual(body["high_risk_count"], int(cat.get("High", 0)))
        self.assertEqual(body["medium_risk_count"], int(cat.get("Medium", 0)))
        self.assertEqual(body["low_risk_count"], int(cat.get("Low", 0)))
        self.assertEqual(body["partial_incomplete_count"],
                         int((risk["score_status"] == "partial").sum()))
        self.assertEqual(body["cost_warning_count"], n_type("COST_WARNING"))
        self.assertEqual(body["time_warning_count"], n_type("TIME_WARNING"))
        self.assertEqual(body["combined_high_risk_warning_count"],
                         n_type("COMBINED_HIGH_RISK_WARNING"))
        # categories partition the dataset
        self.assertEqual(body["high_risk_count"] + body["medium_risk_count"]
                         + body["low_risk_count"], body["total_projects"])


class TestEarlyWarnings(unittest.TestCase):
    """(7) GET /api/early-warnings with filters + pagination."""

    def test_list_warnings(self) -> None:
        resp = client.get("/api/early-warnings", params={"page_size": 7})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for key in ("items", "page", "page_size", "total"):
            self.assertIn(key, body)
        self.assertEqual(len(body["items"]), 7)
        item = body["items"][0]
        for key in ("project_code", "warning_type", "warning_priority",
                    "warning_message", "risk_indicators",
                    "recommended_action"):
            self.assertIn(key, item)

    def test_filter_by_risk_category(self) -> None:
        resp = client.get("/api/early-warnings",
                          params={"risk_category": "High", "page_size": 50})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(all(it["risk_category"] == "High"
                            for it in body["items"]))
        expected = int(pd.read_csv(
            PROJECT_ROOT / "outputs" / "risk" / "early_warning_results.csv"
        )["risk_category"].value_counts().get("High", 0))
        self.assertEqual(body["total"], expected)

    def test_filter_by_warning_type(self) -> None:
        resp = client.get("/api/early-warnings",
                          params={"warning_type": "COST_WARNING",
                                  "page_size": 10})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(all("COST_WARNING" in it["warning_type"].split("|")
                            for it in body["items"]))

    def test_invalid_filters_return_422(self) -> None:
        self.assertEqual(client.get("/api/early-warnings",
                                    params={"risk_category": "Bogus"}
                                    ).status_code, 422)
        self.assertEqual(client.get("/api/early-warnings",
                                    params={"warning_type": "MADE_UP"}
                                    ).status_code, 422)


class TestProjectRisk(unittest.TestCase):
    """(8) GET /api/projects/{code}/risk"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.code = client.get("/api/projects").json()["items"][0][
            "project_code"]
        cls.resp = client.get(f"/api/projects/{cls.code}/risk")
        cls.body = cls.resp.json()

    def test_status_and_schema(self) -> None:
        self.assertEqual(self.resp.status_code, 200)
        for key in ("project_code", "cost_overrun_probability",
                    "time_overrun_probability", "combined_risk_score",
                    "risk_category", "score_status", "missing_component",
                    "warning_type", "warning_priority", "warning_message",
                    "risk_indicators", "recommended_action"):
            self.assertIn(key, self.body)

    def test_probabilities_and_thresholds(self) -> None:
        for key in ("cost_overrun_probability", "time_overrun_probability",
                    "combined_risk_score"):
            value = self.body[key]
            if value is not None:
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)
        self.assertIn(self.body["risk_category"],
                      {"Low", "Medium", "High", "Unknown"})
        if self.body["combined_risk_score"] is not None:
            # existing Phase-5 thresholds are respected, not re-derived
            self.assertEqual(self.body["risk_category"],
                             band_of(self.body["combined_risk_score"]))

    def test_invalid_project_risk_returns_404(self) -> None:
        self.assertEqual(
            client.get("/api/projects/999999999/risk").status_code, 404)


class TestPredict(unittest.TestCase):
    """(9) valid input  (10) invalid/missing input."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.resp = client.post("/api/predict", json=VALID_PREDICT)
        cls.body = cls.resp.json()

    def test_valid_prediction(self) -> None:
        self.assertEqual(self.resp.status_code, 200)
        for key in ("cost_overrun_probability", "time_overrun_probability",
                    "cost_probability_available",
                    "time_probability_available", "combined_risk_score",
                    "score_status", "missing_component", "risk_category"):
            self.assertIn(key, self.body)
        for key in ("cost_overrun_probability", "time_overrun_probability",
                    "combined_risk_score"):
            self.assertGreaterEqual(self.body[key], 0.0, key)
            self.assertLessEqual(self.body[key], 1.0, key)
        self.assertTrue(self.body["cost_probability_available"])
        self.assertTrue(self.body["time_probability_available"])
        self.assertEqual(self.body["score_status"], "complete")
        self.assertEqual(self.body["risk_category"],
                         band_of(self.body["combined_risk_score"]))

    def test_missing_input_returns_422(self) -> None:
        bad = dict(VALID_PREDICT)
        del bad["state"]
        self.assertEqual(client.post("/api/predict", json=bad).status_code,
                         422)
        self.assertEqual(client.post("/api/predict", json={}).status_code, 422)

    def test_invalid_values_return_422(self) -> None:
        bad = dict(VALID_PREDICT, original_cost_crore=-5)
        self.assertEqual(client.post("/api/predict", json=bad).status_code, 422)
        bad = dict(VALID_PREDICT, approval_month=13)
        self.assertEqual(client.post("/api/predict", json=bad).status_code, 422)

    def test_prediction_is_deterministic(self) -> None:
        again = client.post("/api/predict", json=VALID_PREDICT).json()
        self.assertEqual(again["cost_overrun_probability"],
                         self.body["cost_overrun_probability"])
        self.assertEqual(again["time_overrun_probability"],
                         self.body["time_overrun_probability"])


class TestModelLoadingAndIntegrity(unittest.TestCase):
    """Models loaded once (cached), never retrained or modified."""

    def test_pipelines_cached_singleton(self) -> None:
        a = model_service.get_pipelines()
        b = model_service.get_pipelines()
        self.assertIs(a, b)                 # same object -> loaded once

    def test_model_files_not_modified_by_predictions(self) -> None:
        paths = [PROJECT_ROOT / "models" / "cost_overrun" / "pipeline.joblib",
                 PROJECT_ROOT / "models" / "time_overrun" / "pipeline.joblib"]
        before = [sha256_of(p) for p in paths]
        client.post("/api/predict", json=VALID_PREDICT)
        after = [sha256_of(p) for p in paths]
        self.assertEqual(before, after)     # no retraining / no writes

    def test_feature_schema_is_phase4_schema(self) -> None:
        expected = ["original_cost_crore", "log1p_original_cost",
                    "approval_year", "approval_month",
                    "planned_horizon_months", "agency", "state"]
        self.assertEqual(model_service.PLAN_ONLY_FEATURES, expected)
        self.assertEqual(
            list(model_service.get_pipelines()[
                "cost_overrun"].feature_names_in_), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)


