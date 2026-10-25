"""Provider interface and a deterministic mock provider.

A provider is any object with a name, a model_version, and a
research(frame) method returning a dossier-shaped dict. This module
holds the interface and the mock. Live providers live in
madd/providers_http.py behind the same interface and import no
provider SDK either.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Provider(Protocol):
    """The provider protocol: any object with name and model_version
    attributes and a research(frame) method returning a dossier dict.
    Structural only; nothing registers or inherits."""
    name: str
    model_version: str

    def research(self, frame: dict) -> dict:
        """Research one frame and return a dossier dict (see
        madd/schemas/dossier.json for the shape)."""
        ...


class MockProvider:
    """Deterministic mock. Output is synthetic and labelled as such.

    The label distinguishes multiple mock instances in one run (each
    gets its own dossier and agent identifiers); the default label
    keeps the original single-mock output unchanged.
    """

    name = "mock"
    model_version = "mock-0"

    def __init__(self, label: str = "001"):
        """label distinguishes multiple mock instances in one run; each
        gets its own dossier and agent identifiers."""
        self.label = label

    def research(self, frame: dict) -> dict:
        """Return the mock dossier: one invented, labelled-synthetic claim
        with no source. The evidence call strikes it by design."""
        frame_id = frame.get("frame_id", "SYN-FRAME") if isinstance(frame, dict) else "SYN-FRAME"
        return {
            "artifact_type": "dossier",
            "schema_version": "0.1.0",
            "dossier_id": "SYN-DOSSIER-" + self.label,
            "frame_id": frame_id,
            "agent_id": "mock-agent-" + self.label,
            "model_family": "mock",
            "proposed_focus_id": "SYN-T1",
            "direction": "synthetic_direction",
            "_synthetic": True,
            "synthetic_notice": "SYNTHETIC: invented mock output for code tests only. Not research.",
            "unverified_notes": ["Mock provider makes no evidence claims."],
            "claims": [
                {
                    "claim_id": "SYN-C1",
                    "text": "SYNTHETIC placeholder claim for code tests only.",
                    "load_bearing": False,
                    "evidence_tier": 0,
                    "source_kind": "model_opinion",
                    "source_identifier": None,
                    "identifier_type": "doi",
                    "verification_status": "unverified",
                    "supporting_quote": "",
                }
            ],
        }
