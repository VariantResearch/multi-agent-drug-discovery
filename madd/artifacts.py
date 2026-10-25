"""Canonical JSON hashing, freeze/thaw helpers, and run manifests.

Standard library only. Freezing an artifact records the SHA-256 of its
canonical JSON form (sorted keys, compact separators, UTF-8), so any later
edit changes the hash and is detectable.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict


def canonical_json(obj) -> str:
    """Deterministic JSON: sorted keys, compact separators, no ASCII escape."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_hash(obj) -> str:
    """SHA-256 hex digest of the canonical JSON form of obj."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def prompt_hash(prompt_text: str) -> str:
    """SHA-256 hex digest of a prompt's text alone, as recorded in manifests."""
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def freeze_artifact(artifact: dict) -> dict:
    """Return a frozen envelope: a deep copy plus its canonical hash."""
    frozen_copy = copy.deepcopy(artifact)
    return {"artifact": frozen_copy, "sha256": canonical_hash(frozen_copy), "frozen": True}


def verify_frozen(envelope: dict) -> bool:
    """True only when the envelope is a frozen record whose stored hash
    matches a fresh canonical hash of its artifact. Anything else,
    tampered, truncated, or wrongly typed, returns False."""
    if not isinstance(envelope, dict) or envelope.get("frozen") is not True:
        return False
    artifact = envelope.get("artifact")
    recorded = envelope.get("sha256")
    if not isinstance(artifact, dict) or not isinstance(recorded, str):
        return False
    return canonical_hash(artifact) == recorded


def thaw_artifact(envelope: dict) -> dict:
    """Return a mutable deep copy of a frozen artifact, after verification."""
    if not verify_frozen(envelope):
        raise ValueError("frozen artifact failed hash verification")
    return copy.deepcopy(envelope["artifact"])


@dataclass
class RunManifest:
    """In-memory shape of a run manifest. build_manifest is the normal
    way to create one; this class exists so the field set has one
    definition."""
    run_id: str
    model_name: str
    model_version: str
    prompt_hash: str
    tool_versions: dict = field(default_factory=dict)
    budget: dict = field(default_factory=dict)
    declared_use: str = "research"
    artifact_type: str = "run_manifest"
    schema_version: str = "0.1.0"

    def to_dict(self) -> dict:
        """The manifest as a plain dict, the form stored in records and
        validated against the run_manifest schema."""
        return asdict(self)


def build_manifest(model_name: str, model_version: str, prompt_text: str,
                   tool_versions: dict | None = None, budget: dict | None = None,
                   declared_use: str = "research", run_id: str | None = None) -> dict:
    """Build a run manifest dict recording model, prompt hash, tools, budget."""
    manifest = RunManifest(
        run_id=run_id or ("run-" + uuid.uuid4().hex[:12]),
        model_name=model_name,
        model_version=model_version,
        prompt_hash=prompt_hash(prompt_text),
        tool_versions=dict(tool_versions or {}),
        budget=dict(budget or {}),
        declared_use=declared_use,
    )
    return manifest.to_dict()
