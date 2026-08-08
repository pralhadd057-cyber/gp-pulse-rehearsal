import os
import sys
import time
import unittest

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gp_pulse import detection, ingestion
from gp_pulse.config import DetectionConfig


def _series_df(gp_id, values):
    """Build a minimal single-GP dataframe from a 12-value list, matching
    the standardized ingestion schema."""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return pd.DataFrame({
        "gp_id": [gp_id] * 12,
        "gp_name": [f"Dr. {gp_id}"] * 12,
        "clinic": ["Test Clinic"] * 12,
        "city": ["Sydney"] * 12,
        "month": months,
        "month_index": list(range(12)),
        "referral_count": values,
    })


class TestDetectionCorrectness(unittest.TestCase):
    def setUp(self):
        self.cfg = DetectionConfig()

    def test_worked_example_amanda_chen_is_flagged(self):
        # Matches the hackathon pitch's worked example: 42-ish baseline,
        # drops to 41, 38, 27, 19 by October, ~55% drop.
        df = _series_df("chen", [44, 39, 39, 44, 41, 40, 41, 38, 27, 19, 18, 18])
        results = detection.run(df, self.cfg)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertTrue(r.flagged)
        self.assertEqual(r.severity, "high")
        self.assertTrue(50 <= r.drift_pct <= 60, f"expected ~55% drift, got {r.drift_pct}")

    def test_stable_gp_not_flagged(self):
        df = _series_df("stable", [50, 48, 52, 51, 49, 50, 51, 50, 49, 52, 50, 51])
        results = detection.run(df, self.cfg)
        self.assertFalse(results[0].flagged)

    def test_seasonal_dip_not_flagged(self):
        # A dip that recovers shouldn't trigger — this is the
        # non_recovering guard doing its job.
        df = _series_df("seasonal", [50, 50, 50, 50, 50, 30, 28, 30, 50, 50, 50, 50])
        results = detection.run(df, self.cfg)
        self.assertFalse(results[0].flagged)

    def test_single_bad_month_not_flagged(self):
        # One bad month dragging the recent average down, but the other
        # two recent months are fine -- consistently_below should catch this.
        df = _series_df("blip", [50, 50, 50, 50, 50, 50, 50, 50, 10, 50, 49, 51])
        results = detection.run(df, self.cfg)
        self.assertFalse(results[0].flagged)

    def test_sharp_sustained_decline_is_flagged(self):
        df = _series_df("sharp", [60, 61, 59, 60, 62, 60, 58, 20, 18, 19, 17, 18])
        results = detection.run(df, self.cfg)
        self.assertTrue(results[0].flagged)
        self.assertEqual(results[0].severity, "high")

    def test_results_sorted_worst_first(self):
        df = pd.concat([
            _series_df("mild", [50] * 9 + [40, 39, 41]),
            _series_df("severe", [50] * 9 + [10, 9, 11]),
        ], ignore_index=True)
        results = detection.run(df, self.cfg)
        self.assertEqual(results[0].gp_id, "severe")

    def test_empty_dataframe_returns_empty_list(self):
        self.assertEqual(detection.run(pd.DataFrame(), self.cfg), [])


class TestDetectionScale(unittest.TestCase):
    def test_two_thousand_gps_runs_fast(self):
        df = ingestion.generate_synthetic(n_gps=2000, seed=42)
        cfg = DetectionConfig()
        start = time.perf_counter()
        results = detection.run(df, cfg)
        elapsed = time.perf_counter() - start
        self.assertEqual(len(results), 2000)
        self.assertLess(elapsed, 5.0, f"detection took {elapsed:.2f}s for 2000 GPs, expected < 5s")


if __name__ == "__main__":
    unittest.main()
