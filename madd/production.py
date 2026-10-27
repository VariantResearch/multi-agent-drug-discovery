"""Production target sheets: what a ranked candidate would be made as.

The end goal of the design stage is not a ranked list of ideas; it
is a set of production targets - the exact compound, peptide, or
oligonucleotide to make for the targeted process, specified tightly
enough that a synthesis lab or manufacturer could start from it.
This module builds one sheet per ranked candidate, mechanically,
from the candidate record and the design brief:

- identity: the structure exactly as proposed, and for SMILES the
  RDKit-canonical form, molecular formula, molecular weight, and
  InChIKey, all computed, never designer-asserted;
- composition for sequence candidates (length and residue counts),
  with an alphabet check against the declared modality;
- the production route the modality implies (chemical synthesis,
  solid-phase peptide synthesis, biologic production), with the
  retrosynthesis result when a route search ran on the candidate;
- the targeted process the candidate serves (the brief's target,
  disease, and design constraints, carried verbatim);
- and an explicit not_specified list: production-critical details
  the designer did not supply (a modification pattern, a
  confirmation assay, stereochemistry) are named as missing rather
  than filled in plausibly. A sheet whose structure cannot be
  validated, or whose route cannot be assigned, is marked not
  production-ready, with the reason stated.
"""
from __future__ import annotations

from . import design_rdkit

_ROUTES = {
    "small_molecule": "chemical synthesis",
    "peptide": "solid-phase peptide synthesis",
    "biologic": ("biologic production (oligonucleotide synthesis for "
                 "antisense or siRNA constructs, recombinant expression "
                 "for protein constructs)"),
}

_AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")
_NUCLEOTIDES = set("ACGTUN")


def _computed(candidate: dict) -> dict:
    """The candidate's RDKit-computed properties, by name."""
    out = {}
    for prop in candidate.get("predicted_properties") or []:
        if isinstance(prop, dict) and str(prop.get("basis", "")).startswith(
                "computed:RDKit"):
            out[prop.get("name")] = prop.get("value")
    return out


def _smiles_identity(candidate: dict, value: str) -> dict:
    """Computed identity for a SMILES structure: canonical form,
    formula, InChIKey, and unspecified-stereocenter count. Fields
    RDKit cannot produce here are left absent, never guessed."""
    identity = {"format": "smiles", "value_as_proposed": value}
    structure = candidate.get("structure") or {}
    if structure.get("canonical_smiles"):
        identity["canonical_smiles"] = structure["canonical_smiles"]
    if design_rdkit.available():
        result = design_rdkit.describe_smiles(value)
        identity["structure_valid"] = bool(result.get("valid"))
        if result.get("valid"):
            identity.setdefault("canonical_smiles",
                                result.get("canonical_smiles"))
            key = design_rdkit.inchikey(value)
            if key:
                identity["inchikey"] = key
            if result.get("structural_alerts"):
                # Computed triage information for whoever would
                # make this: PAINS/Brenk flags on the structure,
                # recorded on the sheet, never hidden and never a
                # readiness input on their own.
                identity["structural_alerts"] = result["structural_alerts"]
            try:
                from rdkit import Chem
                from rdkit.Chem import rdMolDescriptors
                mol = Chem.MolFromSmiles(value)
                identity["molecular_formula"] = (
                    rdMolDescriptors.CalcMolFormula(mol))
                centers = Chem.FindMolChiralCenters(
                    mol, includeUnassigned=True)
                identity["unspecified_stereocenters"] = sum(
                    1 for _, tag in centers if tag == "?")
            except Exception:
                pass
    else:
        identity["structure_valid"] = None
    return identity


def _sequence_identity(candidate: dict, value: str) -> dict:
    """Composition for a sequence structure: length, residue counts,
    and an alphabet check against the declared modality (amino-acid
    letters for peptides, nucleotide letters otherwise)."""
    seq = "".join(str(value).split()).upper()
    counts = {}
    for ch in seq:
        counts[ch] = counts.get(ch, 0) + 1
    modality = str(candidate.get("modality") or "")
    alphabet = _AMINO_ACIDS if modality == "peptide" else _NUCLEOTIDES
    off_alphabet = sorted(set(seq) - alphabet)
    return {"format": "sequence", "value_as_proposed": value,
            "length": len(seq), "composition": counts,
            "alphabet_check": ("pass" if seq and not off_alphabet
                               else "fail"),
            "off_alphabet_characters": off_alphabet}


def build_production_sheet(candidate: dict, brief: dict,
                           rank: int = None) -> dict:
    """Build the production target sheet for one candidate.

    Mechanical throughout: every value is copied from the candidate
    or brief, or computed by RDKit. Anything production-critical
    that neither source supplies lands in not_specified by name.
    """
    structure = candidate.get("structure") or {}
    fmt = str(structure.get("format") or "").lower()
    value = structure.get("value")
    modality = str(candidate.get("modality") or "unspecified")
    notes = candidate.get("production_notes")
    notes = notes if isinstance(notes, dict) else {}
    not_specified = []

    blockers = []
    if fmt == "smiles" and isinstance(value, str) and value.strip():
        identity = _smiles_identity(candidate, value)
        if identity.get("structure_valid") is False:
            not_specified.append("a valid structure (RDKit rejected "
                                 "the proposed SMILES)")
            blockers.append("structure")
        elif identity.get("structure_valid") is None:
            # Readiness requires positive validation: with RDKit
            # unavailable the structure's validity is unknown, and a
            # sheet must not call an unvalidated structure ready.
            not_specified.append("structure validation (RDKit was not "
                                 "available to validate the proposed "
                                 "structure)")
            blockers.append("structure")
        if identity.get("unspecified_stereocenters"):
            not_specified.append(
                "stereochemistry (" + str(identity["unspecified_stereocenters"])
                + " stereocenter(s) unassigned in the proposed structure)")
            # An unassigned stereocenter means the exact product is
            # not determined: two different compounds share the sheet.
            blockers.append("stereochemistry")
        computed = _computed(candidate)
        if computed.get("molecular_weight") is not None:
            identity["molecular_weight"] = computed["molecular_weight"]
    elif fmt == "sequence" and isinstance(value, str) and value.strip():
        identity = _sequence_identity(candidate, value)
        if identity.get("alphabet_check") == "fail":
            not_specified.append(
                "a sequence on the " + modality + " alphabet (characters "
                + ", ".join(identity["off_alphabet_characters"])
                + " do not belong to it)")
            blockers.append("structure")
        if not notes.get("modifications"):
            not_specified.append(
                "the modification pattern (backbone and sugar or terminal "
                "modifications, conjugation) a synthesized sequence "
                "candidate is made with")
            # An unmodified sequence and a modified one are different
            # products; without the pattern there is no single thing
            # to make, so the sheet is not production-ready.
            blockers.append("modifications")
    else:
        identity = {"format": fmt or "none", "value_as_proposed": value}
        not_specified.append("a structure (no usable structure was "
                             "proposed for this candidate)")
        blockers.append("structure")

    route = _ROUTES.get(modality)
    if route is None:
        not_specified.append("a production route (modality "
                             + repr(modality) + " maps to none)")
        blockers.append("route")
    retro = candidate.get("retrosynthesis")
    if not notes.get("confirmation_assay"):
        not_specified.append(
            "the confirmation assay that would verify the targeted "
            "process for this candidate")
    ready = not blockers
    sheet = {
        "artifact_type": "production_sheet",
        "schema_version": "0.1.0",
        "candidate_id": candidate.get("candidate_id"),
        "rank": rank,
        "modality": modality,
        "design_tool": candidate.get("design_tool"),
        "targeted_process": {
            "target": brief.get("target"),
            "disease": brief.get("disease"),
            "question": brief.get("question"),
            "design_constraints": list(brief.get("design_constraints") or []),
        },
        "identity": identity,
        "production_route": route,
        "production_notes": notes,
        "not_specified": not_specified,
        "production_ready": bool(ready),
    }
    if isinstance(retro, dict):
        sheet["retrosynthesis"] = {"status": retro.get("status"),
                                   "solved": retro.get("solved"),
                                   "reason": retro.get("reason")}
    return sheet


def build_production_sheets(bundle: dict) -> list:
    """Sheets for a design bundle's ranked candidates, in ranking
    order. Excluded candidates get no sheet: a production target is
    something the run actually stands behind."""
    by_id = {c.get("candidate_id"): c
             for c in bundle.get("candidates") or []}
    brief = bundle.get("brief") or {}
    sheets = []
    for position, cid in enumerate(
            (bundle.get("ranking") or {}).get("ranked") or [], start=1):
        candidate = by_id.get(cid)
        if candidate is not None:
            sheets.append(build_production_sheet(candidate, brief,
                                                 rank=position))
    return sheets
