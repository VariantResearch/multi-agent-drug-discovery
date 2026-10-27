"""Stage checkpoints for long runs: persist each finished
stage so an interrupted run resumes instead of restarting.

Runs are long and provider calls are the expensive part. A
run that dies at case 7 of 8 has already paid for 7 cases;
restarting from zero pays twice and, worse, can produce a
different run. This module is the persistence seam the
runners use when a checkpoint directory is configured:

- Gate 0 checkpoints each case (its debate record and
  prediction, and its baseline prediction and dossier) as the
  case completes. A resumed run reuses a case's checkpoint
  only when the checkpoint's recorded case-pack hash matches
  the pack the run just built: a changed pack invalidates the
  checkpoint, silently and completely, because a checkpoint
  from different inputs is not a shortcut, it is a different
  run wearing the same id.
- Target runs checkpoint the frame stage and the design
  stage under the run's id.
- Resumed stages make no provider calls and charge no
  budget; the run's event stream names each resumed stage,
  and the checkpoint directory's manifest records what was
  saved and when.

Checkpoints are working state, not bundles: they live in
their own directory, are never the frozen record of a run,
and a run's bundle is identical in form whether it was
resumed or not.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _safe(text) -> str:
    """One path-safe identifier from a run or stage key."""
    return "".join(ch for ch in str(text)
                   if ch.isalnum() or ch in "-_.") or "x"


def payload_hash(payload) -> str:
    """A stable hash of a checkpoint payload's guard value."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str)
        .encode("utf-8")).hexdigest()


class CheckpointStore:
    """JSON checkpoint files under one directory, keyed by
    run id and stage key."""

    def __init__(self, root):
        """Bind the root directory (created on first save)."""
        self.root = Path(root)

    def _path(self, run_id, key) -> Path:
        """The file for one (run, stage) checkpoint."""
        return self.root / _safe(run_id) / (_safe(key) + ".json")

    def save(self, run_id, key, payload, guard: str = None):
        """Persist one stage payload, with its guard value and
        save time recorded in the run's manifest."""
        path = self._path(run_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"run_id": run_id, "key": key, "guard": guard,
                  "saved_utc": datetime.now(timezone.utc).isoformat(),
                  "payload": payload}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=1), encoding="utf-8")
        tmp.replace(path)
        manifest_path = path.parent / "manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
        manifest[key] = {"saved_utc": record["saved_utc"],
                         "guard": guard}
        manifest_path.write_text(json.dumps(manifest, indent=1),
                                 encoding="utf-8")

    def load(self, run_id, key, guard: str = None):
        """The saved payload for one stage, or None: absent,
        unreadable, or guard-mismatched (a mismatched guard
        means the inputs changed and the checkpoint is not
        this run's)."""
        path = self._path(run_id, key)
        if not path.exists():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if guard is not None and record.get("guard") != guard:
            return None
        return record.get("payload")

    def keys(self, run_id) -> list:
        """The stage keys saved for one run."""
        folder = self.root / _safe(run_id)
        if not folder.is_dir():
            return []
        return sorted(p.stem for p in folder.glob("*.json")
                      if p.name != "manifest.json")
