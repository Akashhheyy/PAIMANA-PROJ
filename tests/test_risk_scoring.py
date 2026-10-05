"""
PAIMANA AI - Phase 5 unit tests for the risk-scoring module.

Covers (as required):
  * probability ranges [0,1]
  * missing values / missing component handling (never zero-filled)
  * risk threshold boundaries (Low/Medium/High)
  * unknown time labels preserved (-1) with NO time probability
  * repeatable (deterministic) output
Run:  python -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    """ml/06_risk_scoring.py - digits prevent a normal import."""
    path = ROOT / "ml" / "06_risk_scoring.py"
    spec = importlib.util.spec_from_file_location("paimana_risk06", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["paimana_risk06"] = mod
    spec.loader.exec_module(mod)
    return mod


rs = _load_module()


class TestCombineProbabilities(unittest.TestCase):
    """Pure-function tests: formula, missing handling, statuses."""

    def test_both_available_weighted_mean(self):
        out = rs.combine_probabilities([0.2], [0.8])
        self.assertAlmostEqual(out["combined_risk_score"].iloc[0], 0.5)
        self.assertEqual(out["score_status"].iloc[0], "complete")
        self.assertEqual(out["missing_component"].iloc[0], "none")

    def test_both_available_custom_weights(self):
        out = rs.combine_probabilities([0.2], [0.8], w_cost=0.75, w_time=0.25)
        self.assertAlmostEqual(out["combined_risk_score"].iloc[0],
                               0.75 * 0.2 + 0.25 * 0.8)

    def test_missing_time_is_not_zero_filled(self):
        out = rs.combine_probabilities([0.6], [np.nan])
        self.assertAlmostEqual(out["combined_risk_score"].iloc[0], 0.6)
        self.assertEqual(out["score_status"].iloc[0], "partial")
        self.assertEqual(out["missing_component"].iloc[0],
                         "time_overrun_probability")

    def test_missing_cost_recorded(self):
        out = rs.combine_probabilities([None], [0.4])
        self.assertAlmostEqual(out["combined_risk_score"].iloc[0], 0.4)
        self.assertEqual(out["score_status"].iloc[0], "partial")
        self.assertEqual(out["missing_component"].iloc[0],
                         "cost_overrun_probability")

    def test_both_missing(self):
        out = rs.combine_probabilities([np.nan], [np.nan])
        self.assertTrue(np.isnan(out["combined_risk_score"].iloc[0]))
        self.assertEqual(out["score_status"].iloc[0], "missing")
        self.assertEqual(out["missing_component"].iloc[0], "both")

    def test_invalid_weights_rejected(self):
        with self.assertRaises(ValueError):
            rs.combine_probabilities([0.5], [0.5], w_cost=0.0, w_time=0.0)


class TestRiskThresholds(unittest.TestCase):
    """Boundary tests for Low / Medium / High / Unknown."""

    def test_boundaries_scalar(self):
        self.assertEqual(rs.risk_category(0.0), "Low")
        self.assertEqual(rs.risk_category(0.3499), "Low")
        self.assertEqual(rs.risk_category(0.35), "Medium")     # LOW_MAX edge
        self.assertEqual(rs.risk_category(0.6499), "Medium")
        self.assertEqual(rs.risk_category(0.65), "High")       # HIGH_MIN edge
        self.assertEqual(rs.risk_category(1.0), "High")

    def test_nan_unknown(self):
        self.assertEqual(rs.risk_category(np.nan), "Unknown")
        self.assertEqual(rs.risk_category(None), "Unknown")

    def test_custom_thresholds(self):
        self.assertEqual(rs.risk_category(0.4, low_max=0.6, high_min=0.8),
                         "Low")
        self.assertEqual(rs.risk_category(0.7, low_max=0.6, high_min=0.8),
                         "Medium")

    def test_vectorised_matches_scalar(self):
        scores = pd.Series([0.0, 0.34, 0.35, 0.64, 0.65, 1.0, np.nan])
        got = rs.assign_risk_categories(scores)
        want = [rs.risk_category(s) for s in scores]
        self.assertEqual(list(got), want)


class TestRealScoring(unittest.TestCase):
    """Integration tests against the actual saved Phase-4 artifacts."""

    @classmethod
    def setUpClass(cls):
        needed = [rs.FEATURES_CSV, rs.COST_PIPELINE, rs.TIME_PIPELINE]
        if not all(p.exists() for p in needed):
            raise unittest.SkipTest("Phase-4 artifacts not present")
        cls.df = pd.read_csv(rs.FEATURES_CSV)
        cls.pipelines = rs.load_pipelines()
        cls.table = rs.build_risk_table(df=cls.df, pipelines=cls.pipelines)

    def test_probability_ranges(self):
        for col in ("cost_overrun_probability", "time_overrun_probability"):
            s = self.table[col].dropna()
            self.assertGreater(len(s), 0, f"no probabilities in {col}")
            self.assertTrue(((s >= 0.0) & (s <= 1.0)).all(),
                            f"{col} outside [0,1]: {s.min()}..{s.max()}")
        c = self.table["combined_risk_score"].dropna()
        self.assertTrue(((c >= 0.0) & (c <= 1.0)).all())

    def test_unknown_time_labels_preserved(self):
        unknown = self.table["time_overrun_label"] == -1
        self.assertEqual(int(unknown.sum()), 354, "expected 354 unknown rows")
        self.assertTrue(self.table.loc[unknown,
                                       "time_overrun_probability"].isna().all(),
                        "unknown rows must have NO time probability")
        self.assertTrue(self.table.loc[unknown, "score_status"].eq("partial").all())
        self.assertTrue(self.table.loc[unknown, "missing_component"].eq(
            "time_overrun_probability").all())
        # not silently treated as negative: partial score == cost probability
        self.assertTrue(np.allclose(
            self.table.loc[unknown, "combined_risk_score"],
            self.table.loc[unknown, "cost_overrun_probability"]))

    def test_known_time_rows_have_time_probability(self):
        known = self.table["time_overrun_label"] != -1
        self.assertEqual(int(known.sum()), 1627)
        self.assertTrue(self.table.loc[known,
                                       "time_overrun_probability"].notna().all())
        self.assertTrue(self.table.loc[known, "score_status"].eq("complete").all())
        self.assertTrue(self.table.loc[known, "missing_component"].eq("none").all())

    def test_probability_available_flags_match_labels(self):
        self.assertTrue(self.table["cost_probability_available"].all())
        self.assertEqual(
            list(self.table["time_probability_available"]),
            list(self.table["time_overrun_label"] != -1))

    def test_no_missing_component_hidden_as_zero(self):
        partial = self.table["score_status"] == "partial"
        self.assertTrue(
            (self.table.loc[partial, "combined_risk_score"] ==
             self.table.loc[partial, "cost_overrun_probability"]).all())
        self.assertFalse(
            (self.table["missing_component"] == "none")[partial].any())

    def test_schema_has_no_forbidden_inputs(self):
        for pipe in self.pipelines.values():
            schema = set(rs.schema_of(pipe))
            self.assertEqual(schema & rs.FORBIDDEN_INPUTS, set())

    def test_required_output_columns(self):
        required = ["sl_no", "project_code", "project_name", "state", "agency",
                    "cost_overrun_probability", "time_overrun_probability",
                    "combined_risk_score", "risk_category", "score_status",
                    "missing_component", "time_overrun_label"]
        for col in required:
            self.assertIn(col, self.table.columns, f"missing column {col}")

    def test_categories_valid(self):
        self.assertTrue(self.table["risk_category"].isin(
            ["Low", "Medium", "High", "Unknown"]).all())
        counts = self.table["risk_category"].value_counts().to_dict()
        self.assertGreater(sum(counts.values()), 0)

    def test_repeatable_output(self):
        t1 = rs.build_risk_table(df=self.df, pipelines=self.pipelines)
        t2 = rs.build_risk_table(df=self.df, pipelines=self.pipelines)
        pd.testing.assert_frame_equal(t1, t2)
        with tempfile.TemporaryDirectory() as td:
            p1, p2 = Path(td) / "a.csv", Path(td) / "b.csv"
            t1.to_csv(p1, index=False)
            t2.to_csv(p2, index=False)
            self.assertEqual(p1.read_bytes(), p2.read_bytes(),
                             "CSV output is not byte-identical across runs")


if __name__ == "__main__":
    unittest.main(verbosity=2)

