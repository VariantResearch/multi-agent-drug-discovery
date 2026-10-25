"""Add-case scaffolding tests in a scratch Gate 0 directory."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.gate0 import scaffold_case, validate_dataset


class TestScaffold(unittest.TestCase):
    """Tests for scaffold."""
    def test_scaffold_creates_templates_and_ledger_section(self):
        """Scaffold creates templates and ledger section."""
        with tempfile.TemporaryDirectory() as tmp:
            created = scaffold_case("newcase-x", tmp)
            self.assertEqual(len(created), 3)
            pack = json.loads((Path(tmp) / "input" / "newcase-x.json")
                              .read_text(encoding="utf-8"))
            self.assertEqual(pack["case_id"], "newcase-x")
            self.assertEqual(pack["claims"], [])
            self.assertIn("_scaffold", pack)
            outcome = json.loads((Path(tmp) / "sealed" / "newcase-x.outcome.json")
                                 .read_text(encoding="utf-8"))
            self.assertIn("TODO", outcome["outcome_class"])
            ledger = (Path(tmp) / "VERIFICATION_LEDGER.md").read_text(encoding="utf-8")
            self.assertIn("Scaffold: newcase-x", ledger)
            # An unfinished scaffold must not validate as a dataset.
            report = validate_dataset(tmp)
            self.assertFalse(report["ok"])
            self.assertGreater(report["error_count"], 0)

    def test_scaffold_refuses_to_overwrite(self):
        """Scaffold refuses to overwrite."""
        with tempfile.TemporaryDirectory() as tmp:
            scaffold_case("newcase-x", tmp)
            with self.assertRaises(FileExistsError):
                scaffold_case("newcase-x", tmp)


if __name__ == "__main__":
    unittest.main()
