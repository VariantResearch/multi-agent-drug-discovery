"""Storage and report tests over bundles produced by stub runs."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.artifacts import verify_frozen
from madd.providers import MockProvider
from madd.report import bundle_to_markdown
from madd.runner import run_frame, run_gate0
from madd.storage import list_runs, load_bundle, write_bundle
from tests.test_runner import CaseStub, DRUGS, GATE0


class TestStorageReport(unittest.TestCase):
    """Tests for storage report."""
    def _frame_bundle(self):
        """Build a frame run bundle for the storage tests."""
        frame = {"artifact_type": "frame", "schema_version": "0.1.0",
                 "frame_id": "TEST-FRAME", "question": "invented",
                 "round_cap": 2}
        return run_frame(frame, [MockProvider("001"), MockProvider("002")],
                         judge_provider=MockProvider("003"),
                         run_id="test-store-1")

    def test_write_and_reload_frame_bundle(self):
        """Write and reload frame bundle."""
        bundle = self._frame_bundle()
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_bundle(bundle, tmp)
            self.assertTrue((run_dir / "bundle.json").exists())
            self.assertTrue((run_dir / "report.md").exists())
            self.assertFalse((run_dir / "gate-report.json").exists())
            loaded = load_bundle(tmp, "test-store-1")
            self.assertTrue(verify_frozen(loaded["frozen_bundle"]))
            runs = list_runs(tmp)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["outcome"], "no_go")

    def test_gate0_bundle_writes_gate_report(self):
        """Gate0 bundle writes gate report."""
        a = CaseStub("a", set(DRUGS.values()))
        b = CaseStub("b", set(DRUGS.values()))
        judge = CaseStub("judge", set(DRUGS.values()))
        baseline = CaseStub("base", set())
        bundle = run_gate0([a, b], judge_provider=judge,
                           baseline_provider=baseline, gate0_dir=GATE0,
                           run_id="test-store-2")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_bundle(bundle, tmp)
            report = json.loads((run_dir / "gate-report.json")
                                .read_text(encoding="utf-8"))
            self.assertEqual(report["subject_id"], "test-store-2")
            md = (run_dir / "report.md").read_text(encoding="utf-8")
            self.assertIn("Gate 0 run report", md)
            self.assertIn("did not pass", md)

    def test_markdown_reports_numbers_from_the_bundle(self):
        """Markdown reports numbers from the bundle."""
        bundle = self._frame_bundle()
        md = bundle_to_markdown(bundle)
        self.assertIn("Outcome: no_go", md)
        self.assertIn("evidence_floor", md)


if __name__ == "__main__":
    unittest.main()
