"""Provider interface and a deterministic mock provider.

Phase 0 makes no live model calls and imports no provider SDK. A provider
is any object with a name, a model_version, and a research(frame) method
returning a dossier-shaped dict. Real providers are a future module behind
this same interface.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Provider(Protocol):
    name: str
    model_version: str

    def research(self, frame: dict) -> dict:
        ...


class MockProvider:
    """Deterministic mock. Output is synthetic and labelled as such."""

    name = "mock"
    model_version = "mock-0"

    def research(self, frame: dict) -> dict:
        frame_id = frame.get("frame_id", "SYN-FRAME") if isinstance(frame, dict) else "SYN-FRAME"
        return {
            "artifact_type": "dossier",
            "schema_version": "0.1.0",
            "dossier_id": "SYN-DOSSIER-001",
            "frame_id": frame_id,
            "agent_id": "mock-agent",
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
