import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gp_pulse import storage
from gp_pulse.config import AppConfig
from gp_pulse.pipeline import run_pipeline


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.db_path = tempfile.mktemp(suffix=".sqlite3")
        self.cfg = AppConfig(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_synthetic_run_persists_expected_data(self):
        summary = run_pipeline(self.cfg, n_gps=40)
        self.assertEqual(summary["gps_total"], 40)
        self.assertEqual(summary["referral_rows"], 40 * 12)
        self.assertEqual(summary["briefs_generated"], summary["gps_flagged"])

        with storage.connect(self.db_path) as conn:
            all_gps = storage.get_all_gps(conn)
            flagged = storage.get_flagged_gps(conn)
            briefs = storage.get_all_briefs(conn)
        self.assertEqual(len(all_gps), 40)
        self.assertEqual(len(flagged), summary["gps_flagged"])
        self.assertEqual(len(briefs), summary["gps_flagged"])
        # Every flagged GP should have a brief and vice versa.
        self.assertEqual({g.gp_id for g in flagged}, {b.gp_id for b in briefs})

    def test_rerun_replaces_previous_results(self):
        run_pipeline(self.cfg, n_gps=20)
        summary2 = run_pipeline(self.cfg, n_gps=5)
        with storage.connect(self.db_path) as conn:
            all_gps = storage.get_all_gps(conn)
        # Second run should have fully replaced the first, not appended.
        self.assertEqual(len(all_gps), 5)
        self.assertEqual(summary2["gps_total"], 5)

    def test_csv_ingestion_path(self):
        csv_content = (
            "gp_name,clinic,city,month,referral_count\n"
            + "\n".join(f"Dr. X,Test Clinic,Sydney,{m},50" for m in
                        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        )
        csv_path = tempfile.mktemp(suffix=".csv")
        with open(csv_path, "w") as f:
            f.write(csv_content)
        try:
            summary = run_pipeline(self.cfg, csv_path=csv_path)
            self.assertEqual(summary["gps_total"], 1)
            self.assertEqual(summary["gps_flagged"], 0)  # flat series, nothing to flag
        finally:
            os.remove(csv_path)


if __name__ == "__main__":
    unittest.main()
