"""HTML report tests over bundles from stub runs."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.html_report import bundle_to_html
from madd.providers import MockProvider
from madd.runner import run_frame, run_gate0
from tests.test_runner import CaseStub, DRUGS, GATE0


class TestHtmlReport(unittest.TestCase):
    """Tests for html report."""
    def test_gate0_html_is_themed_and_complete(self):
        """Gate0 html is themed and complete."""
        a = CaseStub("a", set(DRUGS.values()))
        b = CaseStub("b", set(DRUGS.values()))
        bundle = run_gate0([a, b], judge_provider=CaseStub("j", set(DRUGS.values())),
                           baseline_provider=CaseStub("base", set()),
                           gate0_dir=GATE0, run_id="test-html-1")
        page = bundle_to_html(bundle)
        self.assertIn("#0a0a16", page)
        self.assertIn("#ff71ce", page)
        self.assertIn("<svg", page)
        self.assertIn("DID NOT PASS", page)
        self.assertIn("evolocumab-pcsk9-cvd", page)
        self.assertTrue(page.startswith("<!DOCTYPE html>"))

    def test_frame_html_and_escaping(self):
        """Frame html and escaping."""
        frame = {"artifact_type": "frame", "schema_version": "0.1.0",
                 "frame_id": "F<1>", "question": "invented", "round_cap": 2}
        bundle = run_frame(frame, [MockProvider("001"), MockProvider("002")],
                           run_id="test-html-2")
        page = bundle_to_html(bundle)
        self.assertIn("no_go", page)
        self.assertIn("F&lt;1&gt;", page)
        self.assertNotIn("F<1>", page)


if __name__ == "__main__":
    unittest.main()
