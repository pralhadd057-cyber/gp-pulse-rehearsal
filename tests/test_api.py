import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gp_pulse.api import ThreadingHTTPServer, make_handler
from gp_pulse.config import AppConfig
from gp_pulse.pipeline import run_pipeline


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def _post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read())


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = tempfile.mktemp(suffix=".sqlite3")
        cls.cfg = AppConfig(db_path=cls.db_path, api_host="127.0.0.1", api_port=0)
        run_pipeline(cls.cfg, n_gps=25)

        handler = make_handler(cls.cfg)
        cls.server = ThreadingHTTPServer((cls.cfg.api_host, 0), handler)
        cls.port = cls.server.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def test_health(self):
        status, body = _get(f"{self.base}/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_gps_list(self):
        status, body = _get(f"{self.base}/api/gps")
        self.assertEqual(status, 200)
        self.assertEqual(len(body), 25)

    def test_flagged_subset_of_all(self):
        _, all_gps = _get(f"{self.base}/api/gps")
        _, flagged = _get(f"{self.base}/api/gps/flagged")
        all_ids = {g["gp_id"] for g in all_gps}
        self.assertTrue({g["gp_id"] for g in flagged}.issubset(all_ids))
        self.assertTrue(all(g["flagged"] for g in flagged))

    def test_gp_detail_and_brief_consistency(self):
        _, flagged = _get(f"{self.base}/api/gps/flagged")
        self.assertGreater(len(flagged), 0, "expected at least one flagged GP in a 25-GP synthetic run")
        gp_id = flagged[0]["gp_id"]
        status, detail = _get(f"{self.base}/api/gps/{gp_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["gp_id"], gp_id)

        status, brief = _get(f"{self.base}/api/briefs/{gp_id}")
        self.assertEqual(status, 200)
        self.assertEqual(brief["gp_id"], gp_id)
        self.assertIn("brief_text", brief)

    def test_unknown_gp_returns_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            _get(f"{self.base}/api/gps/does-not-exist")
        self.assertEqual(ctx.exception.code, 404)

    def test_recompute_changes_gp_count(self):
        status, summary = _post(f"{self.base}/api/recompute", {"n_gps": 8})
        self.assertEqual(status, 200)
        self.assertEqual(summary["gps_total"], 8)
        status, all_gps = _get(f"{self.base}/api/gps")
        self.assertEqual(len(all_gps), 8)

    def test_dashboard_served_at_root(self):
        req = urllib.request.Request(f"{self.base}/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode()
        self.assertIn("<html", html.lower())


if __name__ == "__main__":
    unittest.main()
