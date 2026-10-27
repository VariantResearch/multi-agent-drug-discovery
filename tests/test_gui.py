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
    """Make a request to the console test server."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8")


class TestGui(unittest.TestCase):
    """Tests for the MADD Console GUI."""

    @classmethod
    def setUpClass(cls):
        """Set up the class fixtures."""
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
        """Tear down the class fixtures."""
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def test_page_is_themed(self):
        """Page is themed."""
        page = _request(self.base + "/")
        self.assertIn("MADD // CONSOLE", page)
        self.assertIn("#ff71ce", page)
        self.assertIn("laser", page)

    def test_gate0_is_not_part_of_the_console(self):
        """The console carries no Gate 0 surface: the scoreboard,
        run, check, and dry-run endpoints are gone (404), and the
        page has no Gate 0 panel and no prefilled MTCH2."""
        import urllib.error
        for path in ("/api/gate0", "/api/run-gate0",
                     "/api/providers-check", "/api/dry-run",
                     "/api/calibration"):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                _request(self.base + path,
                         {"config": "x"} if "run" in path or "check" in path or "dry" in path else None)
            self.assertEqual(ctx.exception.code, 404)
        page = _request(self.base + "/")
        self.assertNotIn("GATE 0 SCOREBOARD", page)
        self.assertNotIn("RUN GATE 0", page)
        self.assertNotIn("MTCH2", page)
        self.assertNotIn("target-chips", page)

    def test_library_excludes_gate0_bundles(self):
        """Gate 0 bundles stored in the runs directory are not
        listed in the console library; product runs are."""
        from madd import storage
        from madd.providers import MockProvider
        from madd.runner import run_frame, run_gate0
        from tests.test_runner import CaseStub, DRUGS, GATE0
        frame = {"artifact_type": "frame", "schema_version": "0.1.0",
                 "frame_id": "F-GUI", "question": "invented",
                 "round_cap": 2}
        frame_bundle = run_frame(
            frame, [MockProvider("001"), MockProvider("002")],
            run_id="gui-frame-1")
        storage.write_bundle(frame_bundle, self.runs)
        a = CaseStub("a", set(DRUGS.values()))
        b = CaseStub("b", set(DRUGS.values()))
        gate0_bundle = run_gate0(
            [a, b], judge_provider=CaseStub("j", set(DRUGS.values())),
            baseline_provider=CaseStub("base", set()), gate0_dir=GATE0,
            run_id="gui-gate0-1")
        storage.write_bundle(gate0_bundle, self.runs)
        runs = json.loads(_request(self.base + "/api/runs"))
        ids = [entry["run_id"] for entry in runs["runs"]]
        self.assertIn("gui-frame-1", ids)
        self.assertNotIn("gui-gate0-1", ids)


if __name__ == "__main__":
    unittest.main()
