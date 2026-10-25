"""Phase 2 candidate design: briefs, designers, candidate audit, ranking.

The design stage starts only from a locked consensus spec and applies
the research layer's discipline to what it produces: every candidate
claim is validated like any other claim, every predicted property names
its basis, candidates that fail audit or a recorded constraint are
excluded from the ranking with their reasons preserved, and the ranking
itself is a fixed deterministic rule stated in docs/PHASE2_SPEC.md.

Designers: the deterministic mock (synthetic, structure-free, for
pipeline exercise), the model panel (ModelDesigner: the run config's
providers propose real candidates with structures through their
complete() method, under a strict response contract), and
license-gated external tools through madd/design_tools.py, whose
outputs enter as candidates with provenance recorded. Before audit,
madd/design_rdkit.py validates every SMILES structure with RDKit and
attaches computed descriptors, so a cycle ends with ranked candidates
carrying real structures, calculated properties, and audited claims -
or an honest gate failure explaining why not.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import json as _json

from . import citation_auditor
from . import claims as claims_mod
from . import design_admet
from . import design_rdkit
from . import design_sources
from . import schemas
from .artifacts import freeze_artifact
from .providers import MockProvider


def _slug(text: str) -> str:
    """Filesystem and id safe slug for ids built from spec ids."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "spec"


def build_brief(spec: dict, source: str,
                design_constraints: tuple = (),
                target: str = None, disease: str = None) -> dict:
    """Build a design brief from a locked consensus spec.

    Raises ValueError when the spec is not locked: no design work
    starts from a killed, parked, or unresolved target. Evidence
    constraints are the spec's surviving load-bearing claims, carried
    by claim id so candidates can be checked against them.

    The target comes from the spec's focus_id (the field debate-locked
    specs actually carry); the spec records no disease, so disease is
    taken from the operator's override when given and otherwise left
    empty rather than guessed.
    """
    if not isinstance(spec, dict) or spec.get("artifact_type") != "consensus_spec":
        raise ValueError("design requires a consensus_spec artifact")
    if spec.get("outcome") != "locked":
        raise ValueError(
            "design requires a locked spec; this spec's outcome is "
            + repr(spec.get("outcome")))
    evidence = []
    for c in spec.get("claims", []):
        if c.get("load_bearing"):
            evidence.append({
                "claim_id": c.get("claim_id"),
                "text": c.get("text"),
                "evidence_tier": c.get("evidence_tier"),
            })
    focus = spec.get("focus")
    if isinstance(focus, dict):
        focus_label = focus.get("label") or focus.get("focus_id") or ""
    else:
        focus_label = spec.get("focus_id") or ""
    brief = {
        "artifact_type": "design_brief",
        "schema_version": "0.1.0",
        "brief_id": "brief-" + _slug(spec.get("spec_id", "spec")),
        "spec_id": spec.get("spec_id"),
        "target": target or focus_label,
        "disease": disease or spec.get("disease_context") or spec.get("disease") or "",
        "question": ("Design candidates against " + (target or focus_label or "the locked target")
                     + " consistent with the surviving evidence."),
        "evidence_constraints": evidence,
        "design_constraints": [str(c) for c in design_constraints],
        "source": source,
    }
    errors = schemas.validate_artifact("design_brief", brief)
    if errors:
        raise ValueError("built brief failed its schema: "
                         + "; ".join(e["path"] + ": " + e["message"] for e in errors))
    return brief


class MockDesigner:
    """Deterministic synthetic designer: pipeline exercise only.

    Returns two labelled synthetic candidates with no structure, no
    claims, and no evaluated constraints. It exists so the design
    pipeline, audit, ranking, and reporting can be verified without a
    real design tool, and it must never be presented as a designer of
    actual candidates.
    """

    name = "mock"

    def design(self, brief: dict) -> list[dict]:
        """Return the two fixed synthetic candidates for a brief.

        Every list and dict is built fresh per candidate: an earlier
        version shallow-copied a shared base dict, so both candidates
        held the same constraint_results and predicted_properties list
        objects and mutating one mutated the other.
        """
        out = []
        for suffix, modality in (("a", "small_molecule"), ("b", "biologic")):
            out.append({
                "artifact_type": "candidate",
                "schema_version": "0.1.0",
                "candidate_id": brief["brief_id"] + "-" + suffix,
                "spec_id": brief["spec_id"],
                "modality": modality,
                "design_tool": "mock",
                "description": ("Synthetic " + modality.replace("_", " ")
                                + " placeholder for "
                                + (brief.get("target") or "the target") + "."),
                "claims": [],
                "structure": None,
                "structure_note": ("The mock designer invents no structures; a real "
                                   "candidate's structure comes from a recorded tool run."),
                "predicted_properties": [{
                    "name": "target_engagement",
                    "value": "unknown",
                    "basis": "designer_prediction",
                    "note": "Synthetic placeholder; not a measurement or a calculation.",
                }],
                "constraint_results": (
                    [{"constraint": c["claim_id"], "kind": "evidence", "status": "unknown",
                      "basis": "mock designer does not evaluate constraints"}
                     for c in brief.get("evidence_constraints", [])]
                    + [{"constraint": c, "kind": "design", "status": "unknown",
                        "basis": "mock designer does not evaluate constraints"}
                       for c in brief.get("design_constraints", [])]
                ),
                "_synthetic": True,
                "synthetic_notice": ("Synthetic pipeline-test candidate. Not a real "
                                     "designed molecule."),
            })
        return out


DESIGN_SYSTEM_PROMPT = """You are a medicinal chemistry design agent in an evidence-audited drug discovery system. You are given a design brief for a target whose evidence survived independent audit. Propose candidate compounds or biologics against that target.

Rules you cannot escape:
- Every candidate must carry a real structure: a SMILES string for a small molecule, an amino acid sequence for a peptide or biologic.
- Any factual claim you attach follows the claim ledger: a load-bearing claim needs a real primary-source identifier (PubMed id, DOI, NCT number, PMCID, preprint PPR id, GWAS GCST or rsID, ChEMBL id, PubChem CID, or UniProt accession), an identifier_type, a supporting_quote, and an evidence_tier. Claims that cannot meet that bar must be marked load_bearing false or omitted. Unsourced assertions presented as support are struck by mechanical audit and exclude the candidate.
- Predicted properties are your estimates: give each a basis of "designer_prediction". Never present an estimate as a measurement or a calculation.
- Assess the brief's constraints honestly in constraint_results: status pass, fail, or unknown, with the basis for the assessment. A failed constraint excludes the candidate, and hiding one is worse than reporting it.
Answer with the JSON object specified in the user message and nothing else."""

_DESIGN_CONTRACT = """Design brief (JSON):
{brief}

Answer with a JSON object of exactly this shape, no prose outside it:
{{"candidates": [{{"modality": "small_molecule" | "peptide" | "biologic",
  "structure": {{"format": "smiles" | "sequence", "value": string}},
  "description": string,
  "claims": [claim objects following the ledger rules],
  "predicted_properties": [{{"name": string, "value": any, "basis": "designer_prediction"}}],
  "constraint_results": [{{"constraint": string, "kind": "evidence" | "design",
                           "status": "pass" | "fail" | "unknown", "basis": string}}]}}]}}
Propose between one and four candidates."""


def _parse_design_response(text) -> dict | None:
    """Parse a provider's design response into a dict, or None.

    Mirrors the dossier contract's strictness: the whole text as JSON,
    else the outermost JSON object inside it. Anything else is not a
    response the pipeline can use, and the provider contributes
    nothing rather than something repaired into plausibility.
    """
    if not isinstance(text, str):
        return None
    for candidate_text in (text, text[text.find("{"):text.rfind("}") + 1]):
        try:
            parsed = _json.loads(candidate_text)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


class ModelDesigner:
    """The real designer: a panel of model providers proposing candidates.

    Each provider receives the design brief and the candidate contract
    and answers through its complete() method (the HTTP adapters'
    generic completion; the research dossier contract is not reused).
    Responses are normalized mechanically: candidate ids are scoped to
    the provider, provenance is stamped, and a candidate from a real
    provider that carries no structure is dropped with the reason
    recorded - a designed candidate without a structure is not a
    candidate. Candidates from a MockProvider are marked synthetic so
    they can exercise the pipeline without ever passing a gate.
    Provider failures and unparseable responses contribute nothing and
    are recorded in notes, never silently repaired.
    """

    name = "model-panel"

    def __init__(self, providers):
        """providers: provider objects with a complete(system, user)
        method and a name, as built by madd.config.build_providers."""
        self.providers = list(providers)
        self.notes = []

    def design(self, brief: dict) -> list[dict]:
        """Ask every provider for candidates; return normalized records."""
        user = _DESIGN_CONTRACT.format(
            brief=_json.dumps(brief, indent=2, sort_keys=True))
        out = []
        seen_labels = {}
        for provider in self.providers:
            label = str(getattr(provider, "name", "?"))
            # Candidate ids are scoped by provider label; providers can
            # share a name (every MockProvider is named "mock"), so
            # repeated labels get an occurrence suffix to keep ids
            # unique across the panel.
            seen_labels[label] = seen_labels.get(label, 0) + 1
            scope = label if seen_labels[label] == 1 else (
                label + "-" + str(seen_labels[label]))
            try:
                text = provider.complete(DESIGN_SYSTEM_PROMPT, user)
            except Exception as exc:
                self.notes.append("provider " + label + ": design call failed: "
                                  + type(exc).__name__ + ": " + str(exc))
                continue
            parsed = _parse_design_response(text)
            if not parsed or not isinstance(parsed.get("candidates"), list):
                self.notes.append("provider " + label + ": response was not a "
                                  "candidate list; contributed nothing")
                continue
            synthetic = isinstance(provider, MockProvider)
            for i, raw in enumerate(parsed["candidates"]):
                if not isinstance(raw, dict):
                    self.notes.append("provider " + label + ": candidate "
                                      + str(i + 1) + " was not an object; skipped")
                    continue
                structure = raw.get("structure")
                if not isinstance(structure, dict) or not structure.get("value"):
                    structure = None
                if structure is None and not synthetic:
                    self.notes.append(
                        "provider " + label + ": candidate " + str(i + 1)
                        + " carried no structure and was dropped; a real "
                          "candidate must carry one")
                    continue
                cand = {
                    "artifact_type": "candidate",
                    "schema_version": "0.1.0",
                    "candidate_id": scope + "-cand-" + str(i + 1),
                    "spec_id": brief["spec_id"],
                    "modality": raw.get("modality") or "unspecified",
                    "design_tool": "model:" + label,
                    "description": raw.get("description") or "",
                    "structure": structure,
                    "claims": raw.get("claims") if isinstance(raw.get("claims"), list) else [],
                    "predicted_properties": (raw.get("predicted_properties")
                                             if isinstance(raw.get("predicted_properties"), list) else []),
                    "constraint_results": (raw.get("constraint_results")
                                           if isinstance(raw.get("constraint_results"), list) else []),
                }
                if synthetic:
                    cand["_synthetic"] = True
                    cand["synthetic_notice"] = ("Synthetic candidate from a mock "
                                                "provider; pipeline exercise only.")
                out.append(cand)
        return out


def audit_candidate(candidate: dict) -> dict:
    """Audit one candidate's claims and constraint results.

    The claim audit is the research layer's, not a weaker local copy
    (an earlier version ran only the ledger presence checks, so a
    load-bearing claim with a malformed identifier, no quote, and an
    unverified status scored as audited support). Here every claim
    goes through the document claim audit (ledger rules plus duplicate
    claim_id detection) and the citation auditor (identifier format
    and quote rules), and a claim counts toward audited_load_bearing
    only when it is error-free and claims.is_audited - counted once
    per claim_id. A load-bearing claim carrying any audit error, a
    non-object claim entry, or any constraint recorded as failed is a
    hard failure: the candidate is excluded from ranking. Predicted
    properties based on a designer prediction (rather than a recorded
    tool run) are counted as unverified, never silently treated as
    data.
    """
    reasons = []
    claim_errors = []
    raw_claims = candidate.get("claims", [])
    claims_list = [c for c in raw_claims if isinstance(c, dict)]
    if len(claims_list) != len(raw_claims):
        reasons.append("candidate carries a claim entry that is not an object")
    codes_by_id = {}
    for err in claims_mod.audit_claims(candidate)["errors"]:
        codes_by_id.setdefault(err["claim_id"], set()).add(err["code"])
    entries = citation_auditor.audit_citations(candidate)["entries"]
    for claim, entry in zip(claims_list, entries):
        codes = codes_by_id.setdefault(claim.get("claim_id"), set())
        if not entry["format"]["ok"]:
            codes.add("citation_" + entry["format"]["code"])
        for problem in entry["problems"]:
            codes.add(problem["code"])
    audited_ids = set()
    unaudited_load_bearing = 0
    for claim in claims_list:
        cid = claim.get("claim_id")
        codes = codes_by_id.get(cid, set())
        if codes:
            claim_errors.append({"claim_id": cid, "errors": sorted(codes)})
            if claim.get("load_bearing"):
                reasons.append("load-bearing claim " + str(cid)
                               + " failed audit: " + ", ".join(sorted(codes)))
        elif claim.get("load_bearing"):
            if claims_mod.is_audited(claim):
                audited_ids.add(cid)
            else:
                unaudited_load_bearing += 1
    unverified = 0
    for prop in candidate.get("predicted_properties", []):
        if isinstance(prop, dict) and prop.get("basis") == "designer_prediction":
            unverified += 1
    failed_constraints = []
    unknown_constraints = 0
    for cr in candidate.get("constraint_results", []):
        if not isinstance(cr, dict):
            continue
        if cr.get("status") == "fail":
            failed_constraints.append(cr.get("constraint"))
            reasons.append("constraint failed: " + str(cr.get("constraint")))
        elif cr.get("status") == "unknown":
            unknown_constraints += 1
    errors = schemas.validate_artifact("candidate", candidate)
    if errors:
        reasons.append("candidate failed its schema: "
                       + "; ".join(e["path"] + ": " + e["message"] for e in errors))
    return {
        "candidate_id": candidate.get("candidate_id"),
        "claim_errors": claim_errors,
        "audited_load_bearing": len(audited_ids),
        "unaudited_load_bearing": unaudited_load_bearing,
        "unverified_predictions": unverified,
        "failed_constraints": failed_constraints,
        "unknown_constraints": unknown_constraints,
        "hard_fail": bool(reasons),
        "reasons": reasons,
    }


def rank_candidates(candidates: list[dict], audits: list[dict]) -> dict:
    """Apply the fixed ranking rule from docs/PHASE2_SPEC.md.

    Hard-failed candidates are excluded with reasons. The rest sort by
    audited load-bearing claim count descending, then fewer unknown
    constraints, then candidate id, so the ranking is reproducible.
    """
    by_id = {a["candidate_id"]: a for a in audits}
    ranked, excluded = [], []
    for cand in candidates:
        audit = by_id.get(cand.get("candidate_id"))
        if audit and audit["hard_fail"]:
            excluded.append({"candidate_id": cand.get("candidate_id"),
                             "reasons": audit["reasons"]})
        else:
            ranked.append(cand.get("candidate_id"))
    ranked.sort(key=lambda cid: (
        -(by_id.get(cid) or {}).get("audited_load_bearing", 0),
        (by_id.get(cid) or {}).get("unknown_constraints", 0),
        str(cid)))
    return {"ranked": ranked, "excluded": excluded}


def run_design(spec: dict, source: str, designer=None,
               design_constraints: tuple = (), tool_runs: tuple = (),
               extra_candidates: tuple = (),
               target: str = None, disease: str = None,
               use: str = "research", rdkit: bool = True,
               source_check: bool = False, admet: bool = True,
               retro_config=None, retro_work_dir=None) -> dict:
    """Run the design stage for a locked spec and freeze the bundle.

    The gate passes only when the brief came from a locked spec (which
    build_brief enforces), at least one candidate is ranked, at least
    one ranked candidate is real (not a synthetic mock or fixture), no
    tool run in the bundle was license-blocked, and every requested
    tool run completed. A mock-only run therefore fails the gate while
    still recording its ranked placeholders: the pipeline exercised is
    not a design result.
    """
    brief = build_brief(spec, source, design_constraints,
                        target=target, disease=disease)
    designer = designer or MockDesigner()
    candidates = list(designer.design(brief)) + list(extra_candidates)
    all_tool_runs = list(tool_runs)
    if rdkit:
        # Real computation before audit: RDKit validates every SMILES
        # structure and attaches computed descriptors, so an invalid
        # structure enters audit as a failed computed constraint and a
        # valid one carries calculated properties, not estimates.
        all_tool_runs.append(design_rdkit.enrich_candidates(candidates, use=use))
    if source_check:
        # Operator-requested network step: ask ChEMBL and PubChem
        # whether each candidate compound is already known there. The
        # result is recorded on the candidate; it never excludes one.
        source_record = design_sources.check_candidates(candidates)
        source_record["requested"] = True
        all_tool_runs.append(source_record)
    if admet:
        # Trained-model ADMET predictions (ADMET-AI) for every SMILES
        # candidate, recorded as unverified predictions from a named
        # tool - more than a designer's guess, less than a measurement.
        all_tool_runs.append(design_admet.enrich_candidates(candidates, use=use))
    if retro_config:
        # Operator-requested retrosynthesis: one AiZynthFinder route
        # search per SMILES candidate, recorded on the candidate as
        # information (route found or not), never as an exclusion.
        from .design_tools import run_retrosynthesis
        work_base = Path(retro_work_dir or "retro-work")
        for cand in candidates:
            structure = cand.get("structure") or {}
            if structure.get("format") != "smiles" or not structure.get("value"):
                continue
            manifest = run_retrosynthesis(
                structure["value"], retro_config,
                work_base / str(cand.get("candidate_id")), use=use)
            manifest["requested"] = True
            manifest["candidate_id"] = cand.get("candidate_id")
            all_tool_runs.append(manifest)
            cand["retrosynthesis"] = {
                "status": manifest["status"],
                "solved": manifest.get("solved"),
                "reason": manifest.get("reason")}
    candidate_ids = [c.get("candidate_id") for c in candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("duplicate candidate_id in one design run: "
                         + ", ".join(str(x) for x in candidate_ids
                                     if candidate_ids.count(x) > 1)
                         + "; audits and ranking are keyed by candidate_id, "
                           "so duplicates would silently merge two candidates")
    audits = [audit_candidate(c) for c in candidates]
    ranking = rank_candidates(candidates, audits)
    blocked_tools = [t for t in all_tool_runs if t.get("status") == "blocked_license"]
    by_id = {c.get("candidate_id"): c for c in candidates}
    real_ranked = [cid for cid in ranking["ranked"]
                   if not (by_id.get(cid) or {}).get("_synthetic")]
    checks = [
        {"name": "spec_locked", "status": "pass",
         "detail": "brief built from locked spec " + str(spec.get("spec_id"))},
        {"name": "candidates_ranked",
         "status": "pass" if ranking["ranked"] else "fail",
         "detail": str(len(ranking["ranked"])) + " ranked, "
         + str(len(ranking["excluded"])) + " excluded"},
        {"name": "real_candidates_ranked",
         "status": "pass" if real_ranked else "fail",
         "detail": (str(len(real_ranked)) + " non-synthetic candidates ranked")
         if real_ranked else ("every ranked candidate is synthetic (the mock "
                             "designer or a labelled fixture): the pipeline ran, "
                             "but no real candidate exists, so the gate cannot pass")},
        {"name": "tools_license_clean",
         "status": "fail" if blocked_tools else "pass",
         "detail": ("blocked tool attempts: "
                    + ", ".join(t.get("tool", "?") for t in blocked_tools))
         if blocked_tools else "no blocked tool runs"},
    ]
    requested_runs = [t for t in all_tool_runs if t.get("requested")]
    if requested_runs:
        completed = [t for t in requested_runs if t.get("status") == "completed"]
        checks.append(
            {"name": "requested_tools_produced",
             "status": "pass" if completed else "fail",
             "detail": (str(len(completed)) + " of " + str(len(requested_runs))
                        + " requested tool runs completed")
             if completed else ("tool runs were requested and none completed: "
                                + ", ".join(str(t.get("tool")) + "=" + str(t.get("status"))
                                            for t in requested_runs))})
    result = "pass" if all(c["status"] == "pass" for c in checks) else "fail"
    run_id = "design-" + _slug(spec.get("spec_id", "spec"))
    bundle = {
        "kind": "design_run",
        "run_id": run_id,
        "outcome": result,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "designer": getattr(designer, "name", "unknown"),
        "brief": brief,
        "candidates": candidates,
        "audits": audits,
        "ranking": ranking,
        "tool_runs": all_tool_runs,
        "designer_notes": list(getattr(designer, "notes", []) or []),
        "gate_report": {
            "artifact_type": "gate_report",
            "schema_version": "0.1.0",
            "gate_id": run_id,
            "gate_name": "phase2-design",
            "subject_id": spec.get("spec_id"),
            "result": result,
            "checks": checks,
        },
    }
    bundle["frozen_bundle"] = freeze_artifact(
        {k: v for k, v in bundle.items() if k != "frozen_bundle"})
    return bundle
