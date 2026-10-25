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
    """Run the CLI in-process with the given arguments."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


class TestCli(unittest.TestCase):
    """Tests for the CLI."""
    def test_audit_claims_synthetic_fixture_fails_as_designed(self):
        """Audit claims synthetic fixture fails as designed."""
        code, out = run_cli(["audit-claims", str(SYNTHETIC_DOSSIER)])
        self.assertEqual(code, 1)
        self.assertIn("result: FAIL", out)

    def test_check_tool_allowed_and_blocked(self):
        """Check tool allowed and blocked."""
        code, _out = run_cli(["check-tool", "Boltz-2", "--use", "commercial"])
        self.assertEqual(code, 0)
        code, out = run_cli(["check-tool", "AlphaFold 3", "--use", "commercial"])
        self.assertEqual(code, 1)
        self.assertIn("allowed: no", out)

    def test_gate0_validate_passes(self):
        """Gate0 validate passes."""
        code, out = run_cli(["gate0-validate"])
        self.assertEqual(code, 0)
        self.assertIn("result: PASS", out)

    def test_focus_score_runs(self):
        """Focus score runs."""
        code, out = run_cli(["focus-score", str(SYNTHETIC_DOSSIER)])
        self.assertEqual(code, 0)
        self.assertIn("focus score:", out)

    def test_gate0_report_all_kill_predictions_fail(self):
        """Gate0 report all kill predictions fail."""
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
        """Gate0 report perfect run passes."""
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
        """Resolve citations bad format fails without network."""
        doc = {"claims": [{"claim_id": "CX", "source_identifier": "not-a-pmid",
                           "identifier_type": "pmid"}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            code, out = run_cli(["resolve-citations", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("format_invalid", out)

    def _mock_config(self, tmp):
        """Build a mock run config for the CLI tests."""
        config = {
            "providers": [{"name": "panel-a", "kind": "mock", "label": "a"},
                          {"name": "panel-b", "kind": "mock", "label": "b"}],
            "judge": {"name": "judge", "kind": "mock", "label": "j"},
            "baseline": {"name": "base", "kind": "mock", "label": "base"},
            "budget": None, "live_resolution": False,
        }
        path = Path(tmp) / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def test_providers_check_mock_config(self):
        """Providers check mock config."""
        with tempfile.TemporaryDirectory() as tmp:
            config = self._mock_config(tmp)
            code, out = run_cli(["providers-check", "--config", str(config)])
        self.assertEqual(code, 0)
        self.assertIn("panel-a", out)
        self.assertIn("No network calls were made", out)

    def test_providers_check_missing_key_variable(self):
        """Providers check missing key variable."""
        config = {
            "providers": [
                {"name": "a", "kind": "anthropic", "model": "m",
                 "api_key_env": "MADD_TEST_DEFINITELY_UNSET_VAR"},
                {"name": "b", "kind": "mock"}],
            "judge": None, "baseline": None, "budget": None,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            code, out = run_cli(["providers-check", "--config", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("MADD_TEST_DEFINITELY_UNSET_VAR", out)

    def test_run_gate0_with_mocks_completes_and_writes_bundle(self):
        """Run gate0 with mocks completes and writes bundle."""
        with tempfile.TemporaryDirectory() as tmp:
            config = self._mock_config(tmp)
            out_dir = Path(tmp) / "runs"
            code, out = run_cli(["run-gate0", "--config", str(config),
                                 "--out", str(out_dir)])
            self.assertEqual(code, 1)
            self.assertIn("outcome: FAIL", out)
            index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index), 1)
            self.assertEqual(index[0]["kind"], "gate0_run")

    def test_run_gate0_dry_run_estimates_without_running(self):
        """Run gate0 dry run estimates without running."""
        with tempfile.TemporaryDirectory() as tmp:
            config = self._mock_config(tmp)
            code, out = run_cli(["run-gate0", "--config", str(config),
                                 "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("total calls: 32", out)
        self.assertIn("cases: 8", out)

    def test_estimate_gate0_run_math(self):
        """Estimate gate0 run math."""
        from madd.runner import estimate_gate0_run
        from tests.test_runner import CaseStub, GATE0
        a = CaseStub("a", set(), cost=0.50)
        b = CaseStub("b", set(), cost=0.25)
        est = estimate_gate0_run([a, b], judge_provider=CaseStub("j", set(), cost=1.0),
                                 baseline_provider=CaseStub("base", set(), cost=0.10),
                                 gate0_dir=GATE0)
        self.assertEqual(est["total_calls"], 32)
        self.assertAlmostEqual(est["estimated_cost_usd"], 8 * 1.85)

    def test_run_frame_with_mocks(self):
        """Run frame with mocks."""
        with tempfile.TemporaryDirectory() as tmp:
            config = self._mock_config(tmp)
            code, out = run_cli(["run-frame", str(SYNTHETIC_FRAME),
                                 "--config", str(config)])
        self.assertEqual(code, 0)
        self.assertIn("outcome: no_go", out)

    def test_debate_mock_writes_verifiable_record(self):
        """Debate mock writes verifiable record."""
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
