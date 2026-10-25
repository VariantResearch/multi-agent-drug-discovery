"""GUI tests: the console server over loopback HTTP, mock config only."""
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.gui import create_server

MOCK_CONFIG = {
    "providers": [{"name": "panel-a", "kind": "mock", "label": "a"},
                  {"name": "panel-b", "kind": "mock", "label": "b"}],
    "judge": {"name": "judge", "kind": "mock", "label": "j"},
    "baseline": {"name": "base", "kind": "mock", "label": "base"},
    "budget": None, "live_resolution": False,
}


def _request(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8")


class TestGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.tmp.name) / "config.json"
        cls.config.write_text(json.dumps(MOCK_CONFIG), encoding="utf-8")
        cls.runs = Path(cls.tmp.name) / "runs"
        cls.server = create_server("127.0.0.1", 0, runs_dir=str(cls.runs))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def test_page_is_themed(self):
        page = _request(self.base + "/")
        self.assertIn("MADD // CONSOLE", page)
        self.assertIn("#ff71ce", page)
        self.assertIn("laser", page)

    def test_gate0_api(self):
        data = json.loads(_request(self.base + "/api/gate0"))
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["cases"]), 8)

    def test_check_dry_run_and_full_run_flow(self):
        checked = json.loads(_request(self.base + "/api/providers-check",
                                      {"config": str(self.config)}))
        self.assertTrue(checked["ok"])
        dry = json.loads(_request(self.base + "/api/dry-run",
                                  {"config": str(self.config)}))
        self.assertEqual(dry["estimate"]["total_calls"], 32)
        started = json.loads(_request(self.base + "/api/run-gate0",
                                      {"config": str(self.config)}))
        self.assertTrue(started["started"])
        deadline = time.time() + 30
        progress = {}
        while time.time() < deadline:
            progress = json.loads(_request(self.base + "/api/progress"))
            if not progress["running"] and progress["result"]:
                break
            time.sleep(0.2)
        self.assertIsNotNone(progress["result"])
        self.assertEqual(progress["result"]["outcome"], "fail")
        self.assertTrue(any(e["event"] == "debate_case_done"
                            for e in progress["events"]))
        runs = json.loads(_request(self.base + "/api/runs"))
        self.assertEqual(len(runs["runs"]), 1)
        run_id = runs["runs"][0]["run_id"]
        report = _request(self.base + "/api/runs/" + run_id + "/report.html")
        self.assertIn("#0a0a16", report)
        transcript = _request(self.base + "/api/runs/" + run_id
                              + "/transcript/evolocumab-pcsk9-cvd")
        self.assertIn("Debate transcript", transcript)


if __name__ == "__main__":
    unittest.main()
