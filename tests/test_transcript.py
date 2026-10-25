"""Transcript renderer tests over a mock debate record."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.debate import run_debate
from madd.providers import MockProvider
from madd.transcript import record_to_markdown

FRAME = {"artifact_type": "frame", "schema_version": "0.1.0",
         "frame_id": "T-FRAME", "question": "invented?", "round_cap": 2}


class TestTranscript(unittest.TestCase):
    def test_mock_record_renders_all_sections(self):
        record = run_debate(FRAME, [MockProvider("001"), MockProvider("002")],
                            judge_provider=MockProvider("003"))
        md = record_to_markdown(record)
        for heading in ("# Debate transcript", "## Dossiers after the evidence call",
                        "## Cross-examination", "## Ranking",
                        "## Evolution round", "## Consensus tests",
                        "## Judge swap", "## Specification and dissent"):
            self.assertIn(heading, md)
        self.assertIn("Outcome: no_go", md)
        self.assertIn("SYN-C-BAD", md)  # the struck mock claim is shown

    def test_partial_record_does_not_crash(self):
        md = record_to_markdown({"frame": {"frame_id": "X"}, "outcome": "no_go"})
        self.assertIn("Frame: X", md)


if __name__ == "__main__":
    unittest.main()
