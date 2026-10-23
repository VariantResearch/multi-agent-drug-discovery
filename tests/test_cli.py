"""CLI smoke tests: every subcommand runs and reports honestly.

Predictions and frames written here are invented test values. The
gate0-report pass case derives its prediction map from the real sealed
outcomes inside the test only, to exercise the scoring plumbing; it is
not a run result and is never reported as one.
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.artifacts import verify_frozen
from madd.cli import main
from madd.gate0 import list_case_ids, load_sealed_outcome

ROOT = Path(__file__).resolve().parent.parent
GATE0 = ROOT / "gate0"
SYNTHETIC_DOSSIER = ROOT / "examples" / "synthetic" / "dossier.json"
SYNTHETIC_FRAME = ROOT / "examples" / "synthetic" / "frame.json"


def run_cli(argv):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


class TestCli(unittest.TestCase):
    def test_audit_claims_synthetic_fixture_fails_as_designed(self):
        code, out = run_cli(["audit-claims", str(SYNTHETIC_DOSSIER)])
        self.assertEqual(code, 1)
        self.assertIn("result: FAIL", out)

    def test_check_tool_allowed_and_blocked(self):
        code, _out = run_cli(["check-tool", "Boltz-2", "--use", "commercial"])
        self.assertEqual(code, 0)
        code, out = run_cli(["check-tool", "AlphaFold 3", "--use", "commercial"])
        self.assertEqual(code, 1)
        self.assertIn("allowed: no", out)

    def test_gate0_validate_passes(self):
        code, out = run_cli(["gate0-validate"])
        self.assertEqual(code, 0)
        self.assertIn("result: PASS", out)

    def test_focus_score_runs(self):
        code, out = run_cli(["focus-score", str(SYNTHETIC_DOSSIER)])
        self.assertEqual(code, 0)
        self.assertIn("focus score:", out)

    def test_gate0_report_all_kill_predictions_fail(self):
        case_ids = list_case_ids(GATE0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "predictions.json"
            path.write_text(json.dumps({cid: "kill" for cid in case_ids}),
                            encoding="utf-8")
            code, out = run_cli(["gate0-report", str(path),
                                 "--audit-violations", "0", "--judge-swap-flips", "0"])
        self.assertEqual(code, 1)
        self.assertIn("positive_advance_rate | fail", out)
        self.assertIn("failure_kill_rate | pass", out)
        self.assertIn("baseline_margin | not_evaluable", out)

    def test_gate0_report_perfect_run_passes(self):
        case_ids = list_case_ids(GATE0)
        perfect = {}
        for cid in case_ids:
            outcome = load_sealed_outcome(cid, GATE0)
            perfect[cid] = outcome["outcome_class"]
        baseline = {cid: "positive" for cid in case_ids}
        with tempfile.TemporaryDirectory() as tmp:
            pred_path = Path(tmp) / "predictions.json"
            pred_path.write_text(json.dumps(perfect), encoding="utf-8")
            base_path = Path(tmp) / "baseline.json"
            base_path.write_text(json.dumps(baseline), encoding="utf-8")
            code, out = run_cli(["gate0-report", str(pred_path),
                                 "--baseline", str(base_path),
                                 "--audit-violations", "0", "--judge-swap-flips", "1"])
        self.assertEqual(code, 0)
        self.assertIn("result: PASS", out)

    def test_resolve_citations_bad_format_fails_without_network(self):
        doc = {"claims": [{"claim_id": "CX", "source_identifier": "not-a-pmid",
                           "identifier_type": "pmid"}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            code, out = run_cli(["resolve-citations", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("format_invalid", out)

    def test_debate_mock_writes_verifiable_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "record.json"
            code, out = run_cli(["debate-mock", str(SYNTHETIC_FRAME),
                                 "--judge", "--out", str(out_path)])
            self.assertEqual(code, 0)
            self.assertIn("outcome: no_go", out)
            record = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertTrue(verify_frozen(record["frozen_record"]))
        self.assertEqual(record["outcome"], "no_go")


if __name__ == "__main__":
    unittest.main()
