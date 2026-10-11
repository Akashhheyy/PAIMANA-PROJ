"""Phase 7.4 Prompt 2 tests - dashboard graph data + preserved endpoints.

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

import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402
from backend.app.services import project_service  # noqa: E402

client = TestClient(app)
ENDPOINT = "/api/dashboard/progress-distribution"


class TestProgressDistribution(unittest.TestCase):
    """Graph 1 data: GET /api/dashboard/progress-distribution."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.resp = client.get(ENDPOINT)
        cls.body = cls.resp.json()
        cls.features = pd.read_csv(
            PROJECT_ROOT / "data" / "processed" / "paimana_features.csv")

    def test_status_and_snapshot_label(self) -> None:
        self.assertEqual(self.resp.status_code, 200)
        self.assertEqual(self.body["snapshot_label"], "April 2026")

    def test_all_projects_included(self) -> None:
        self.assertEqual(self.body["total_projects"], 1981)
        self.assertEqual(self.body["projects_included"], len(self.features))
        self.assertEqual(self.body["projects_missing_progress"], 0)
        self.assertEqual(
            self.body["projects_included"]
            + self.body["projects_missing_progress"],
            self.body["total_projects"])

    def test_ten_bins_sum_equals_included(self) -> None:
        labels = [b["label"] for b in self.body["bins"]]
        self.assertEqual(labels, [f"{i}-{i + 10}" for i in range(0, 100, 10)])
        self.assertEqual(len(self.body["bins"]), 10)
        self.assertEqual(sum(b["count"] for b in self.body["bins"]),
                         self.body["projects_included"])

    def test_bin_counts_match_csv_ground_truth(self) -> None:
        """Full independent recomputation from the CSV (right=True bins)."""
        truth = (pd.cut(self.features["physical_progress_pct"],
                        bins=list(range(0, 101, 10)), right=True,
                        include_lowest=True)
                 .value_counts().sort_index())
        for b, expected in zip(self.body["bins"], truth.tolist()):
            self.assertEqual(b["count"], expected, b["label"])
        # pitfall bins explicitly: 97 rows at exactly 100 must be counted
        by_label = {b["label"]: b["count"] for b in self.body["bins"]}
        self.assertEqual(by_label["90-100"], 589)
        self.assertEqual(by_label["0-10"], 272)

    def test_mean_median(self) -> None:
        self.assertAlmostEqual(self.body["mean_progress"], 60.21, places=1)
        self.assertAlmostEqual(self.body["median_progress"], 70.0, places=1)

    def test_no_filter_fields_none(self) -> None:
        self.assertIsNone(self.body["agency_filter"])
        self.assertIsNone(self.body["state_filter"])


class TestProgressBoundariesAndMissing(unittest.TestCase):
    """Boundary values (0/10/90/100) and missing handling via a synthetic frame."""

    SYNTH = pd.DataFrame({
        "physical_progress_pct": [0.0, 10.0, 10.0001, 90.0, 90.0001, 100.0,
                                  float("nan")],
        "agency": ["A"] * 7,
        "state": ["S"] * 7,
    })

    def test_boundary_bin_assignment(self) -> None:
        out = project_service.progress_distribution(frame=self.SYNTH)
        by_label = {b["label"]: b["count"] for b in out["bins"]}
        self.assertEqual(by_label["0-10"], 2)       # 0.0 and exactly 10.0
        self.assertEqual(by_label["10-20"], 1)      # 10.0001
        self.assertEqual(by_label["80-90"], 1)      # exactly 90.0
        self.assertEqual(by_label["90-100"], 2)     # 90.0001 and exactly 100.0
        self.assertEqual(out["projects_included"], 6)

    def test_missing_progress_counted_not_zero_filled(self) -> None:
        out = project_service.progress_distribution(frame=self.SYNTH)
        self.assertEqual(out["total_projects"], 7)
        self.assertEqual(out["projects_missing_progress"], 1)
        self.assertEqual(out["projects_included"], 6)
        self.assertEqual(sum(b["count"] for b in out["bins"]),
                         out["projects_included"])


class TestProgressFilters(unittest.TestCase):
    """Agency/state filters + empty results + invalid params."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.features = pd.read_csv(
            PROJECT_ROOT / "data" / "processed" / "paimana_features.csv")

    def test_agency_filter(self) -> None:
        resp = client.get(ENDPOINT, params={"agency": "MoRTH"})
        body = resp.json()
        expected = int((self.features.agency == "MoRTH").sum())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["total_projects"], expected)
        self.assertEqual(sum(b["count"] for b in body["bins"]),
                         body["projects_included"])
        self.assertEqual(body["agency_filter"], "MoRTH")

    def test_state_filter(self) -> None:
        resp = client.get(ENDPOINT, params={"state": "Assam"})
        body = resp.json()
        expected = int((self.features.state == "Assam").sum())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["total_projects"], expected)
        self.assertEqual(sum(b["count"] for b in body["bins"]),
                         body["projects_included"])

    def test_combined_filters(self) -> None:
        resp = client.get(ENDPOINT, params={"agency": "MoRTH",
                                            "state": "Maharashtra"})
        body = resp.json()
        expected = int(((self.features.agency == "MoRTH")
                        & (self.features.state == "Maharashtra")).sum())
        self.assertEqual(body["total_projects"], expected)
        self.assertEqual(sum(b["count"] for b in body["bins"]),
                         body["projects_included"])

    def test_empty_filtered_result_is_safe(self) -> None:
        resp = client.get(ENDPOINT,
                          params={"agency": "NO-SUCH-AGENCY-XYZ"})
        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["total_projects"], 0)
        self.assertEqual(body["projects_included"], 0)
        self.assertEqual(body["projects_missing_progress"], 0)
        self.assertEqual(sum(b["count"] for b in body["bins"]), 0)
        self.assertIsNone(body["mean_progress"])
        self.assertIsNone(body["median_progress"])

    def test_invalid_query_params_422(self) -> None:
        for params in ({"agency": ""}, {"state": ""},
                       {"agency": "x" * 250}):
            resp = client.get(ENDPOINT, params=params)
            self.assertEqual(resp.status_code, 422, params)


class TestPreservedEndpoints(unittest.TestCase):
    """Step 3: the existing risk endpoints must behave EXACTLY as before."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.risk = pd.read_csv(
            PROJECT_ROOT / "outputs" / "risk" / "project_risk_scores.csv")

    def test_project_risk_complete_row_contract(self) -> None:
        """706724 (Guwahati, High) - full contract preserved."""
        resp = client.get("/api/projects/706724/risk")
        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["project_code"], 706724)
        truth = self.risk[self.risk.project_code == 706724].iloc[0]
        self.assertEqual(body["risk_category"], "High")
        self.assertEqual(body["score_status"], "complete")
        self.assertEqual(body["missing_component"], "none")
        self.assertAlmostEqual(body["cost_overrun_probability"],
                               truth.cost_overrun_probability)
        self.assertAlmostEqual(body["time_overrun_probability"],
                               truth.time_overrun_probability)
        self.assertAlmostEqual(body["combined_risk_score"],
                               truth.combined_risk_score)

    def test_project_risk_partial_row_keeps_null_time_probability(self) -> None:
        """612183 - unknown time label: time_p stays NULL, never 0."""
        resp = client.get("/api/projects/612183/risk")
        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(body["time_overrun_probability"])
        self.assertEqual(body["score_status"], "partial")
        self.assertEqual(body["missing_component"], "time_overrun_probability")
        self.assertIn("time_p=n/a", body["risk_indicators"])
        self.assertIsNotNone(body["combined_risk_score"])  # cost-only, as Phase 5

    def test_risk_summary_counts_unchanged(self) -> None:
        body = client.get("/api/risk/summary").json()
        cat = self.risk["risk_category"].value_counts()
        self.assertEqual(body["total_projects"], 1981)
        self.assertEqual(body["high_risk_count"], int(cat.get("High", 0)))
        self.assertEqual(body["medium_risk_count"], int(cat.get("Medium", 0)))
        self.assertEqual(body["low_risk_count"], int(cat.get("Low", 0)))
        self.assertEqual(body["partial_incomplete_count"],
                         int((self.risk["score_status"] == "partial").sum()))

    def test_dashboard_route_listed_in_root(self) -> None:
        body = client.get("/").json()
        self.assertIn("/api/dashboard/progress-distribution",
                      body["endpoints"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


