"""Pre-registration for target runs.

Before a target run starts, the run's question is declared in a
small record: the target, the protocol mode, the panel's model
identities, and what will count as a lock and as a design. The
record is hashed with the same canonical scheme the frozen
bundles use, written to disk before the debate begins, and the
finished bundle carries the hash. Anyone can later recompute
the hash and confirm the run answered the question that was
declared up front, rather than one chosen after the fact.

This is the prospective counterpart to Gate 0's sealed
outcomes. It proves declaration-before-execution; it does not
prove the declarer did not run undeclared runs, and the record
says so.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .artifacts import canonical_hash

PREREG_DIR = "preregistrations"

LOCK_CRITERIA = (
    "the run counts as a lock only when the debate record's "
    "outcome is locked under the run's own consensus tests; it "
    "counts as designed only when the design gate passes with "
    "at least one real ranked candidate")
HONEST_LIMIT = (
    "a pre-registration proves this run's question was declared "
    "before it ran; it cannot prove no undeclared runs happened")


def build_preregistration(frame: dict, providers, mode=None) -> dict:
    """Build the pre-registration record for one target run.

    The record names the frame's target fields, the frame's
    question, the protocol mode, and the panel's provider and
    model identities, then stamps its own sha256 (the canonical
    hash of the record without the hash field).
    """
    record = {
        "artifact_type": "preregistration",
        "schema_version": "0.1.0",
        "created_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "target": {"name": frame.get("target_name"),
                   "kind": frame.get("target_kind"),
                   "target": frame.get("target"),
                   "disease": frame.get("disease"),
                   "focus_id": frame.get("focus_id")},
        "frame_id": frame.get("frame_id"),
        "question": frame.get("question"),
        "mode": mode or "legacy",
        "providers": [{"name": getattr(p, "name", None),
                       "model_version": getattr(p, "model_version", None)}
                      for p in providers],
        "lock_criteria": LOCK_CRITERIA,
        "limit": HONEST_LIMIT,
    }
    record["sha256"] = canonical_hash(record)
    return record


def write_preregistration(record: dict, out_dir) -> Path:
    """Write a pre-registration record under out_dir's
    preregistrations folder, named by its hash. Returns the path."""
    folder = Path(out_dir) / PREREG_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("prereg-" + record["sha256"][:12] + ".json")
    path.write_text(json.dumps(record, indent=2, sort_keys=True),
                    encoding="utf-8")
    return path


def verify_preregistration(record: dict) -> bool:
    """Recompute a pre-registration record's hash and compare."""
    if not isinstance(record, dict) or not record.get("sha256"):
        return False
    body = {k: v for k, v in record.items() if k != "sha256"}
    return canonical_hash(body) == record["sha256"]


def preregistration_ref(record: dict, path) -> dict:
    """The reference a finished bundle carries: hash + file name."""
    return {"sha256": record["sha256"],
            "file": Path(path).name,
            "created_utc": record.get("created_utc")}
