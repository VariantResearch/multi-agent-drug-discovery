"""The research prompt and the dossier response contract.

A live model joins this system through exactly one contract: it
receives the system prompt and a frame (with a blinded case pack when
the run is a Gate 0 case), and it answers with one JSON dossier. This
module owns both sides of that contract so every provider adapter
sends the same prompt and parses answers the same way.

The parsing rule is the honesty rule of the whole project: a response
that cannot be parsed, or that fails the dossier schema, is never
repaired into something plausible. It becomes a dossier with no
claims, no proposed focus, and the failure recorded in its
unverified_notes, where the evidence call and the debate treat it as
what it is - a model that produced nothing usable.
"""
from __future__ import annotations

import json

from .artifacts import canonical_json
from .schemas import validate_artifact

SYSTEM_PROMPT = """You are a research agent in a multi-agent drug discovery system. You work alone and cannot see any other agent's work.

Your task: study the frame and the evidence supplied with it, decide which single target focus the evidence best supports, and return a dossier as JSON.

Rules you must follow:
- Use only the evidence supplied in the frame and the case pack. Do not rely on outcomes you may happen to remember: judge the program as of the evidence_as_of date.
- Every claim you mark load_bearing must carry a source_identifier and identifier_type (pmid, doi, or nct) taken from a real source in the supplied evidence, plus a short supporting_quote from that source. Never invent an identifier, a quote, or a number.
- If you cannot source a claim, either mark it load_bearing false with verification_status "unverified", or leave it out. Claims sourced from your own opinion are worthless here and will be struck.
- evidence_tier: 1 human causal genetics, 2 human clinical or randomised evidence, 3 human observational or biomarker evidence, 4 animal or in-vivo evidence, 5 in-vitro, computational, or other indirect evidence.
- verification_status: use "quote_checked" only when your supporting_quote is copied from the supplied evidence; otherwise "unverified".
- proposed_focus_id: the target identifier from the frame when you judge the program should advance; null when you judge it should not.
- Record what you could not verify in unverified_notes, plainly.

Return ONLY a JSON object with these fields:
{"dossier_id": string, "proposed_focus_id": string or null, "direction": string,
 "claims": [{"claim_id": string, "text": string, "load_bearing": boolean,
             "evidence_tier": integer 1-5, "source_kind": string,
             "source_identifier": string or null,
             "identifier_type": "pmid" | "doi" | "nct",
             "verification_status": "unverified" | "quote_checked",
             "supporting_quote": string}],
 "unverified_notes": [string]}
No prose outside the JSON object."""


def build_user_prompt(frame: dict) -> str:
    """The user message for a research call: the frame (and its case
    pack, when present) as canonical JSON, with the instruction to
    answer with the dossier JSON object only."""
    return ("Frame and evidence follow as JSON. Answer with the dossier JSON "
            "object only.\n\n" + canonical_json(frame))


def _failure_dossier(agent_id, model_family, frame_id, reason) -> dict:
    """The dossier a failed response becomes: no claims, no focus,
    the failure recorded in unverified_notes. See the module docstring
    for why nothing is repaired into something plausible."""
    return {
        "artifact_type": "dossier",
        "schema_version": "0.1.0",
        "dossier_id": "DOSSIER-FAILED-" + str(agent_id),
        "frame_id": frame_id,
        "agent_id": agent_id,
        "model_family": model_family,
        "claims": [],
        "unverified_notes": ["provider response unusable: " + reason],
        "parse_error": True,
    }


def _extract_json(text):
    """Pull the JSON object out of a model response: strip code fences,
    take the outermost braces, parse. Returns (dict, None) or
    (None, reason) - never a partial object."""
    if not isinstance(text, str):
        return None, "response was not text"
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None, "no JSON object found in the response"
    try:
        parsed = json.loads(stripped[start:end + 1])
    except Exception as exc:
        return None, "JSON parse failed: " + str(exc)
    if not isinstance(parsed, dict):
        return None, "JSON response was not an object"
    return parsed, None


def parse_dossier_response(text, agent_id: str, model_family: str,
                           frame_id) -> dict:
    """Turn a model's text answer into a dossier dict.

    Identity fields (agent, model family, frame) are set from the
    caller, never trusted from the response. Schema problems are
    recorded in unverified_notes; an unparseable response becomes a
    failure dossier with no claims and no focus.
    """
    parsed, error = _extract_json(text)
    if error is not None:
        return _failure_dossier(agent_id, model_family, frame_id, error)
    claims = parsed.get("claims")
    dossier = {
        "artifact_type": "dossier",
        "schema_version": "0.1.0",
        "dossier_id": parsed.get("dossier_id") or ("DOSSIER-" + str(agent_id)),
        "frame_id": frame_id,
        "agent_id": agent_id,
        "model_family": model_family,
        "claims": claims if isinstance(claims, list) else [],
        "unverified_notes": parsed.get("unverified_notes")
        if isinstance(parsed.get("unverified_notes"), list) else [],
    }
    # The dossier schema types these as strings when present; a null
    # focus (the model declining to endorse) is represented by absence.
    if isinstance(parsed.get("proposed_focus_id"), str):
        dossier["proposed_focus_id"] = parsed["proposed_focus_id"]
    if isinstance(parsed.get("direction"), str):
        dossier["direction"] = parsed["direction"]
    errors = validate_artifact("dossier", dossier)
    if errors:
        dossier["unverified_notes"] = list(dossier["unverified_notes"]) + [
            "schema problems in the model output: "
            + "; ".join(e["path"] + " " + e["code"] for e in errors[:5])]
    return dossier
