"""Tool license registry and run-use enforcement.

Entries live in madd/data/license_registry.json. Enforcement is
conservative: a tool that is unknown, non-commercial (for a commercial
run), or marked verify_terms is blocked, with a reason. Listing a tool
grants no rights in it.
"""
from __future__ import annotations

import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent / "data" / "license_registry.json"
VALID_USES = {"research", "commercial"}


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _find(registry: dict, tool_name: str):
    wanted = str(tool_name).strip().lower()
    for entry in registry.get("tools", []):
        names = [entry.get("name", "")] + list(entry.get("aliases", []))
        if wanted in [str(n).strip().lower() for n in names]:
            return entry
    return None


def check_tool(tool_name: str, use: str, registry: dict | None = None) -> dict:
    """Return {tool, use, allowed, reason, license, status} for a run use."""
    reg = registry if registry is not None else load_registry()
    use_norm = str(use).strip().lower()
    if use_norm not in VALID_USES:
        return {"tool": tool_name, "use": use, "allowed": False, "license": None,
                "status": "invalid_use",
                "reason": "use must be one of: research, commercial"}
    entry = _find(reg, tool_name)
    if entry is None:
        return {"tool": tool_name, "use": use_norm, "allowed": False, "license": None,
                "status": "unknown_tool",
                "reason": "tool not in registry; blocked by default until its terms are recorded and verified"}
    status = entry.get("status")
    base = {"tool": entry.get("name"), "use": use_norm, "license": entry.get("license"),
            "status": status}
    if status == "verify_terms":
        return dict(base, allowed=False,
                    reason="license terms not yet verified (status verify_terms); blocked until verified")
    if status == "non_commercial" and use_norm == "commercial":
        return dict(base, allowed=False,
                    reason="license is non-commercial; blocked for commercial runs")
    if entry.get("commercial_allowed") is False and use_norm == "commercial":
        return dict(base, allowed=False, reason="commercial use not allowed for this tool")
    return dict(base, allowed=True, reason="allowed for " + use_norm + " runs under the recorded license")
