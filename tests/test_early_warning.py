"""
PAIMANA AI - Phase 6 unit tests: explainable early-warning layer.

Covers the 10 required cases:
 1 high cost probability -> COST_WARNING            6 partial labelled correctly
 2 high time probability -> TIME_WARNING            7 missing score != false Low
 3 high combined         -> COMBINED warning        8 thresholds exactly respected
 4 medium score          -> MEDIUM warning          9 output columns exist
 5 missing time prob != 0                          10 results reproducible
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


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ew = _load("paimana_ew07", "ml/07_early_warning.py")
rs06 = ew.rs06  # Phase-5 thresholds module re-exported through 07


class TestThresholdConsistency(unittest.TestCase):
    def test_thresholds_unchanged_from_phase5(self):
        self.assertEqual(rs06.LOW_MAX, 0.35)
        self.assertEqual(rs06.HIGH_MIN, 0.65)
        self.assertEqual(ew.LOW_MAX, 0.35)
        self.assertEqual(ew.HIGH_MIN, 0.65)
        self.assertEqual(ew.COST_WARNING_MIN, 0.65)
        self.assertEqual(ew.TIME_WARNING_MIN, 0.65)


class TestWarningTypes(unittest.TestCase):
    """Required tests 1-5 and 8 (pure functions)."""

    def _types(self, cost, time, combined, status="complete"):
        return ew.warning_types_for(cost, time, combined, status)

    # 1 - high cost probability
    def test_high_cost_generates_cost_warning(self):
        t = self._types(0.70, 0.30, 0.50)
        self.assertIn(ew.COST_WARNING, t)
        self.assertNotIn(ew.TIME_WARNING, t)

    # 2 - high time probability
    def test_high_time_generates_time_warning(self):
        t = self._types(0.30, 0.90, 0.60)
        self.assertIn(ew.TIME_WARNING, t)
        self.assertNotIn(ew.COST_WARNING, t)

    # 3 - high combined requires BOTH probabilities
    def test_high_combined_generates_combined_warning(self):
        t = self._types(0.70, 0.70, 0.70)
        self.assertIn(ew.COMBINED_HIGH_RISK_WARNING, t)
        self.assertNotIn(ew.DATA_COMPLETENESS_WARNING, t)
        t2 = self._types(0.70, np.nan, 0.70, "partial")   # partial: no combined
        self.assertNotIn(ew.COMBINED_HIGH_RISK_WARNING, t2)
        self.assertIn(ew.COST_WARNING, t2)
        self.assertIn(ew.DATA_COMPLETENESS_WARNING, t2)

    # 4 - medium score
    def test_medium_score_generates_medium_warning(self):
        t = self._types(0.50, 0.50, 0.50)
        self.assertIn(ew.MEDIUM_RISK_WARNING, t)
        self.assertNotIn(ew.COMBINED_HIGH_RISK_WARNING, t)
        self.assertEqual(ew.priority_for(t, 0.50), "MEDIUM")

    # 5 - missing time probability is NOT treated as zero
    def test_missing_time_probability_not_zero(self):
        t = self._types(0.50, np.nan, 0.50, "partial")
        self.assertNotIn(ew.TIME_WARNING, t)
        self.assertNotIn(ew.COMBINED_HIGH_RISK_WARNING, t)
        self.assertIn(ew.DATA_COMPLETENESS_WARNING, t)
        # zero-filling time would give combined 0.25 -> LOW/no warning;
        # the real partial combined of 0.50 must keep the MEDIUM warning
        self.assertIn(ew.MEDIUM_RISK_WARNING, t)
        self.assertEqual(ew.priority_for(t, 0.50), "MEDIUM")


    # 7 - missing score does not create false low risk
    def test_missing_score_is_not_low(self):
        t = self._types(np.nan, np.nan, np.nan, "missing")
        prio = ew.priority_for(t, np.nan)
        self.assertEqual(prio, "NOT_AVAILABLE")
        self.assertNotEqual(prio, "LOW")
        self.assertIn(ew.DATA_COMPLETENESS_WARNING, t)
        self.assertEqual(ew.risk_category_for(np.nan, "missing"), "Unknown")

    # 8 - thresholds exactly respected
    def test_thresholds_exactly_respected(self):
        self.assertNotIn(ew.COST_WARNING, self._types(0.6499999, 0.2, 0.4))
        self.assertIn(ew.COST_WARNING, self._types(0.65, 0.2, 0.4))
        self.assertNotIn(ew.TIME_WARNING, self._types(0.2, 0.6499999, 0.4))
        self.assertIn(ew.TIME_WARNING, self._types(0.2, 0.65, 0.4))
        self.assertEqual(
            ew.priority_for(self._types(0.2, 0.2, 0.3499999), 0.3499999), "LOW")
        self.assertIn(ew.MEDIUM_RISK_WARNING, self._types(0.35, 0.35, 0.35))
        self.assertIn(ew.MEDIUM_RISK_WARNING, self._types(0.6, 0.6, 0.6499999))
        self.assertNotIn(ew.MEDIUM_RISK_WARNING, self._types(0.65, 0.65, 0.65))
        self.assertEqual(ew.priority_for([ew.MEDIUM_RISK_WARNING], 0.35), "MEDIUM")
        self.assertEqual(ew.priority_for([ew.COST_WARNING], 0.30), "HIGH")


class TestMessagesAndActions(unittest.TestCase):
    """Steps 4/6 wording: model-estimated risk, never causation."""

    def test_partial_message_flagged(self):                 # required test 6
        t = ew.warning_types_for(0.5, np.nan, 0.5, "partial")
        msg = ew.warning_message(t, 0.5, np.nan, 0.5, "partial",
                                 "time_overrun_probability")
        self.assertTrue(
            msg.startswith("Warning based on incomplete model evidence."))
        self.assertIn("NOT scored as zero risk", msg)

    def test_partial_score_is_labelled_correctly(self):     # required test 6
        t = ew.warning_types_for(0.1, np.nan, 0.1, "partial")
        self.assertIn(ew.DATA_COMPLETENESS_WARNING, t)
        self.assertEqual(ew.priority_for(t, 0.1), "LOW")
        self.assertIn("incomplete", ew.warning_message(
            t, 0.1, np.nan, 0.1, "partial", "time_overrun_probability").lower())

    def test_high_probability_is_model_estimated_not_causal(self):
        t = ew.warning_types_for(0.8, 0.9, 0.85, "complete")
        msg = ew.warning_message(t, 0.8, 0.9, 0.85, "complete", "none")
        self.assertIn("MODEL-ESTIMATED RISK, not a confirmed future event", msg)
        self.assertIn("The model estimates", msg)
        for word in (" causes ", " will overrun", "guaranteed", "causes "):
            self.assertNotIn(word, msg)

    def test_recommended_actions(self):
        both = [ew.COST_WARNING, ew.TIME_WARNING, ew.COMBINED_HIGH_RISK_WARNING]
        self.assertIn("both cost and schedule", ew.recommended_action(both))
        self.assertIn("cost escalation status",
                      ew.recommended_action([ew.COST_WARNING]))
        self.assertIn("implementation schedule",
                      ew.recommended_action([ew.TIME_WARNING]))
        self.assertIn("regular monitoring",
                      ew.recommended_action([ew.MEDIUM_RISK_WARNING]))
        self.assertIn("routine periodic review",
                      ew.recommended_action([]))
        data = ew.recommended_action([ew.MEDIUM_RISK_WARNING,
                                      ew.DATA_COMPLETENESS_WARNING])
        self.assertIn("Obtain/update missing project information", data)


class TestRealOutput(unittest.TestCase):
    """Tests 9-10 against the real Phase-5 risk output (no SHAP needed)."""

    @classmethod
    def setUpClass(cls):
        if not ew.RISK_CSV.exists():
            raise unittest.SkipTest("Phase-5 risk output not present")
        cls.risk_df = pd.read_csv(ew.RISK_CSV)
        cls.out = ew.assemble_results(cls.risk_df, explanations=None)

    def test_output_columns_exist(self):                    # required test 9
        # all 17 Phase-5 columns preserved + all new warning columns
        for c in self.risk_df.columns:
            self.assertIn(c, self.out.columns, f"Phase-5 column dropped: {c}")
        for c in ew.NEW_COLUMNS:
            self.assertIn(c, self.out.columns, f"missing output column: {c}")
        required = ["sl_no", "project_code", "project_name", "state", "agency",
                    "report_month", "cost_overrun_probability",
                    "time_overrun_probability", "combined_risk_score",
                    "score_status", "risk_category", "warning_type",
                    "warning_priority", "warning_message", "risk_indicators",
                    "recommended_action"]
        for c in required:
            self.assertIn(c, self.out.columns)
        self.assertGreaterEqual(len(self.out.columns),
                                len(self.risk_df.columns) + len(ew.NEW_COLUMNS))
        self.assertEqual(len(self.out), len(self.risk_df))

    def test_partial_rows_flagged_and_not_zero(self):        # required test 5/6
        partial = self.out["score_status"] == "partial"
        self.assertTrue(partial.any(), "expected partial rows in Phase-5 data")
        sub = self.out[partial]
        self.assertTrue(sub["warning_type"].str.contains(
            ew.DATA_COMPLETENESS_WARNING).all())
        self.assertTrue(sub["risk_indicators"].str.contains("time_p=n/a").all())
        # time probability must remain NaN in the output (not zero-filled)
        self.assertTrue(sub["time_overrun_probability"].isna().all())
        self.assertTrue(sub["warning_message"].str.contains(
            "incomplete model evidence").all())
        # and no false 'unknown category' - category must stay Phase-5 value
        self.assertTrue((sub["risk_category"] ==
                         self.risk_df.loc[partial, "risk_category"]).all())

    def test_results_are_reproducible(self):                 # required test 10
        a = ew.assemble_results(self.risk_df, explanations=None)
        b = ew.assemble_results(self.risk_df, explanations=None)
        pd.testing.assert_frame_equal(a, b)
        with tempfile.TemporaryDirectory() as td:
            p1, p2 = Path(td) / "a.csv", Path(td) / "b.csv"
            a.to_csv(p1, index=False)
            b.to_csv(p2, index=False)
            self.assertEqual(p1.read_bytes(), p2.read_bytes())

    def test_warning_priorities_valid(self):
        self.assertTrue(self.out["warning_priority"].isin(
            ["HIGH", "MEDIUM", "LOW", "NOT_AVAILABLE"]).all())
        # a project with a high component probability must be HIGH
        high_cost = self.out["cost_overrun_probability"] >= 0.65
        self.assertTrue(
            self.out.loc[high_cost, "warning_priority"].eq("HIGH").all())

    def test_saved_output_columns_if_present(self):
        if not ew.RESULTS_CSV.exists():
            self.skipTest("early_warning_results.csv not generated yet")
        saved = pd.read_csv(ew.RESULTS_CSV)
        for c in ew.NEW_COLUMNS:
            self.assertIn(c, saved.columns)


if __name__ == "__main__":
    unittest.main(verbosity=2)


