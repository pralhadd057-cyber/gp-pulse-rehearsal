import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gp_pulse import ingestion


class TestGenerateSynthetic(unittest.TestCase):
    def test_schema_and_row_count(self):
        df = ingestion.generate_synthetic(n_gps=10, seed=1)
        self.assertEqual(len(df), 10 * 12)
        for col in ["gp_id", "gp_name", "clinic", "city", "month", "month_index", "referral_count"]:
            self.assertIn(col, df.columns)
        self.assertEqual(df["gp_id"].nunique(), 10)

    def test_deterministic_for_seed(self):
        a = ingestion.generate_synthetic(n_gps=5, seed=99)
        b = ingestion.generate_synthetic(n_gps=5, seed=99)
        self.assertTrue(a.equals(b))

    def test_referral_counts_are_positive(self):
        df = ingestion.generate_synthetic(n_gps=50, seed=7)
        self.assertTrue((df["referral_count"] >= 1).all())

    def test_decline_fraction_produces_some_declining_gps(self):
        # Not a statistical proof, just a sanity check that mixing patterns
        # actually happens rather than everyone being flat.
        df = ingestion.generate_synthetic(n_gps=200, seed=3, decline_fraction=0.5)
        by_gp = df.groupby("gp_id")["referral_count"]
        # crude proxy: last month lower than first month for a meaningful share
        declined = 0
        for _, series in by_gp:
            vals = series.tolist()
            if vals[-1] < vals[0] * 0.7:
                declined += 1
        self.assertGreater(declined, 20)


class TestLoadFromCsv(unittest.TestCase):
    def _write_csv(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_valid_csv_loads(self):
        path = self._write_csv(
            "gp_name,clinic,city,month,referral_count\n"
            "Dr. Test One,Test Clinic,Sydney,Jan,40\n"
            "Dr. Test One,Test Clinic,Sydney,Feb,42\n"
        )
        df = ingestion.load_from_csv(path)
        self.assertEqual(len(df), 2)
        self.assertIn("gp_id", df.columns)
        os.unlink(path)

    def test_missing_column_raises(self):
        path = self._write_csv("gp_name,clinic,month,referral_count\nDr. X,Clinic,Jan,10\n")
        with self.assertRaises(ValueError):
            ingestion.load_from_csv(path)
        os.unlink(path)

    def test_bad_month_label_raises(self):
        path = self._write_csv(
            "gp_name,clinic,city,month,referral_count\nDr. X,Clinic,Sydney,Smarch,10\n"
        )
        with self.assertRaises(ValueError):
            ingestion.load_from_csv(path)
        os.unlink(path)


if __name__ == "__main__":
    unittest.main()
