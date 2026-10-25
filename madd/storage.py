"""Run bundle persistence: one folder per run, plus an index.

Layout under the output directory:
  <out>/<run_id>/bundle.json   the full frozen bundle
  <out>/<run_id>/report.md     the plain-language report
  <out>/<run_id>/gate-report.json   Gate 0 runs only
  <out>/index.json             one entry per run, oldest first

The runs/ directory is gitignored by default: bundles are run output,
not source. Publishing a scored run's bundle to the repository, as
the Phase 1 run protocol requires, is a deliberate act of copying the
folder in, not something this module does on its own.
"""
from __future__ import annotations

import json
from pathlib import Path

from .report import bundle_to_markdown
from .runner import gate_report

BUNDLE_FILE = "bundle.json"
REPORT_FILE = "report.md"
GATE_REPORT_FILE = "gate-report.json"
INDEX_FILE = "index.json"


def write_bundle(bundle: dict, out_dir) -> Path:
    """Write a run bundle and update the index. Returns the run folder."""
    base = Path(out_dir)
    run_dir = base / str(bundle["run_id"])
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / BUNDLE_FILE).write_text(
        json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / REPORT_FILE).write_text(bundle_to_markdown(bundle),
                                       encoding="utf-8")
    if bundle.get("kind") == "gate0_run":
        (run_dir / GATE_REPORT_FILE).write_text(
            json.dumps(gate_report(bundle), indent=2, sort_keys=True),
            encoding="utf-8")
    index_path = base / INDEX_FILE
    index = []
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            index = []
    index = [e for e in index if e.get("run_id") != bundle["run_id"]]
    index.append({"run_id": bundle["run_id"], "kind": bundle.get("kind"),
                  "outcome": bundle.get("outcome"),
                  "frame_id": bundle.get("frame_id"),
                  "case_count": len(bundle.get("case_ids") or []) or None})
    index.sort(key=lambda e: str(e["run_id"]))
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True),
                          encoding="utf-8")
    return run_dir


def list_runs(out_dir) -> list:
    """The index entries for an output directory (empty when none)."""
    index_path = Path(out_dir) / INDEX_FILE
    if not index_path.exists():
        return []
    return json.loads(index_path.read_text(encoding="utf-8"))


def load_bundle(out_dir, run_id) -> dict:
    """Read back a written bundle by run id."""
    path = Path(out_dir) / str(run_id) / BUNDLE_FILE
    return json.loads(path.read_text(encoding="utf-8"))
