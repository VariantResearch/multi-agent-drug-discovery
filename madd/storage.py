"""Run bundle persistence: one folder per run, plus an index.

Layout under the output directory:
  <out>/<run_id>/bundle.json   the full frozen bundle
  <out>/<run_id>/report.md     the plain-language report
  <out>/<run_id>/report.html   the styled HTML report
  <out>/<run_id>/gate-report.json   Gate 0 runs only
  <out>/<run_id>/transcripts/<case_id>.md   Gate 0 debate transcripts
  <out>/<run_id>/transcript.md   frame runs only
  <out>/index.json             one entry per run, sorted by run id

The runs/ directory is gitignored by default: bundles are run output,
not source. Publishing a scored run's bundle to the repository, as
the Phase 1 run protocol requires, is a deliberate act of copying the
folder in, not something this module does on its own.
"""
from __future__ import annotations

import json
from pathlib import Path

from .html_report import bundle_to_html
from .report import bundle_to_markdown
from .runner import gate_report
from .transcript import record_to_markdown

BUNDLE_FILE = "bundle.json"
REPORT_FILE = "report.md"
HTML_REPORT_FILE = "report.html"
GATE_REPORT_FILE = "gate-report.json"
TRANSCRIPT_FILE = "transcript.md"
TRANSCRIPTS_DIR = "transcripts"
INDEX_FILE = "index.json"


def write_bundle(bundle: dict, out_dir) -> Path:
    """Write a run bundle and update the index. Returns the run folder.

    A run folder is one execution's frozen record: when a bundle
    already exists under the same run id with different content,
    this refuses with ValueError rather than overwriting it.
    Rewriting the identical bundle (same frozen hash) is a no-op
    success, so deliberate re-saves of the same record still work.
    """
    base = Path(out_dir)
    run_dir = base / str(bundle["run_id"])
    existing_path = run_dir / BUNDLE_FILE
    if existing_path.exists():
        try:
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
        except Exception:
            existing = None
        if existing is not None:
            new_hash = bundle.get("frozen_bundle", {}).get("hash")
            old_hash = existing.get("frozen_bundle", {}).get("hash")
            if new_hash is not None and old_hash is not None:
                same = new_hash == old_hash
            else:
                same = (json.dumps(existing, sort_keys=True)
                        == json.dumps(bundle, sort_keys=True))
            if not same:
                raise ValueError(
                    "refusing to overwrite the existing run bundle at "
                    + str(run_dir) + ": a different frozen record already "
                    "exists under run id " + str(bundle["run_id"]))
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / BUNDLE_FILE).write_text(
        json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    (run_dir / REPORT_FILE).write_text(bundle_to_markdown(bundle),
                                       encoding="utf-8")
    (run_dir / HTML_REPORT_FILE).write_text(bundle_to_html(bundle),
                                            encoding="utf-8")
    if bundle.get("kind") == "gate0_run":
        (run_dir / GATE_REPORT_FILE).write_text(
            json.dumps(gate_report(bundle), indent=2, sort_keys=True),
            encoding="utf-8")
        transcripts = run_dir / TRANSCRIPTS_DIR
        transcripts.mkdir(exist_ok=True)
        for case_id, record in (bundle.get("case_records") or {}).items():
            (transcripts / (case_id + ".md")).write_text(
                record_to_markdown(record), encoding="utf-8")
    if bundle.get("kind") == "frame_run" and bundle.get("record"):
        (run_dir / TRANSCRIPT_FILE).write_text(
            record_to_markdown(bundle["record"]), encoding="utf-8")
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
    """The index entries for an output directory (empty when none).

    A corrupt index reads as empty, matching write_bundle's tolerance:
    the console's run library must not 500 on a damaged index file.
    """
    index_path = Path(out_dir) / INDEX_FILE
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def load_bundle(out_dir, run_id) -> dict:
    """Read back a written bundle by run id.

    The run id becomes a path segment, so separators and dot segments
    are refused: the console serves bundles by URL segment, and an
    unsanitized ../ segment would read bundle files outside the runs
    directory.
    """
    run_id = str(run_id)
    if run_id in ("", ".", "..") or "/" in run_id or "\\" in run_id:
        raise ValueError("invalid run id: " + run_id)
    path = Path(out_dir) / run_id / BUNDLE_FILE
    return json.loads(path.read_text(encoding="utf-8"))
