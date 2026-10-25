"""Debate engine: docs/DEBATE_PROTOCOL.md, steps 1 to 7, as code.

The protocol existed as a design document only. This module runs it
against any objects satisfying the Provider interface in
madd/providers.py (today that is the deterministic mock provider; real
providers sit behind the same interface once the Phase 1 roster is
chosen). The engine is deterministic wherever the protocol is
mechanical: the evidence call, the pairwise ranking, the evolution
merge, and the consensus tests are code, not agent judgement. Free-text
argument between live agents is a provider concern; what the engine
guarantees is the auditable structure around it: nothing enters a
locked specification without surviving the claim audit, and every run
ends in a frozen, hashed record.

What the engine does not do: it does not make agents argue in free
text. Cross-examination here is the structured objection record the
protocol's outcome depends on (who objected, to which dossier, over
which surviving claims). The argumentative prose of a live debate
belongs to the providers, when real ones are connected.

Steps, matching the protocol:
1. Blinded dossiers: each provider researches the frame alone.
2. Evidence call: every claim is audited; failures are struck and
   listed, and struck claims take no further part.
3. Cross-examination: recorded as structured objections between
   dossiers with different focuses. When every dossier agrees on the
   focus, the protocol's instant-agreement rule fires instead: a
   red-team round is recorded against the agreed focus.
4. Pairwise ranking on the pre-declared rubric: focus score from
   audited surviving claims, then fewer struck claims. Prose quality
   is not a rubric item and is never scored.
5. Evolution round: the top dossier is revised once, merging surviving
   claims from all dossiers (original claim identifiers kept), and the
   merged specification is what the consensus tests judge.
6. Consensus tests from madd/consensus.py, including judge swap when a
   judge provider is supplied.
7. Record: outcome (locked or no_go), the specification, the strike
   list, the ranking, the transcript, and the dissent log, frozen and
   hashed together with a run manifest.

An optional BudgetTracker (madd/budget.py) caps the run: provider calls
that would cross the cap are never made.
"""
from __future__ import annotations

import copy
import re

from .artifacts import (build_manifest, canonical_hash, canonical_json,
                        freeze_artifact, prompt_hash)
from .budget import BudgetExceeded, BudgetTracker
from .citation_auditor import audit_citations
from .claims import validate_claim
from .consensus import run_consensus_tests
from .focus import focus_score

_FOCUS_TOKEN = re.compile(r"[a-z0-9]+")


def _focus_tokens(text) -> frozenset:
    """The word tokens of a focus string, casefolded: the comparison
    basis for deciding whether two focus strings name the same target."""
    if not isinstance(text, str):
        return frozenset()
    return frozenset(_FOCUS_TOKEN.findall(text.casefold()))


def canonical_focus_id(proposed, frame):
    """Map a proposed focus onto the frame's canonical focus_id.

    A frame may declare one canonical focus_id for its target. Models
    asked for "the target identifier" render that target in different
    surface forms (the full descriptive string, an abbreviation, the
    gene symbol), and the 2026-10-25 validation run 2 showed the
    agreement test reading those spellings as different focuses: two
    unanimous advance panels failed agreement on spelling alone, and
    two unanimous advances were blocked by the same accident. Agreement
    must judge whether dossiers name the same target, not whether they
    spell it identically.

    The mapping is deliberately narrow. It applies only when the frame
    declares a focus_id, and a proposed focus maps onto it only when
    it is the focus_id itself (up to case, spacing, and punctuation),
    or when its word tokens and the frame target's word tokens contain
    one another, so the proposal is the frame's own target string or a
    shortening or expansion of it. Anything else is a genuinely
    different focus and is returned unchanged. Frames without a
    focus_id get the previous behaviour exactly: the proposed string
    is returned as it stands.
    """
    if not isinstance(frame, dict):
        return proposed
    focus_id = frame.get("focus_id")
    if not isinstance(focus_id, str) or not focus_id.strip():
        return proposed
    if not isinstance(proposed, str) or not proposed.strip():
        return proposed
    if proposed.strip() == focus_id.strip():
        return focus_id
    proposed_tokens = _focus_tokens(proposed)
    if not proposed_tokens:
        return proposed
    if proposed_tokens == _focus_tokens(focus_id):
        return focus_id
    target_tokens = _focus_tokens(frame.get("target"))
    if target_tokens and (proposed_tokens <= target_tokens
                          or target_tokens <= proposed_tokens):
        return focus_id
    return proposed


def _canonicalize_dossier_focus(dossier: dict, frame) -> None:
    """Rewrite one dossier's proposed focus to the frame's canonical
    focus_id in place, keeping the model's own string under
    proposed_focus_raw whenever the mapping changed it, so the record
    shows both what the model wrote and what it was read as."""
    proposed = dossier.get("proposed_focus_id")
    canonical = canonical_focus_id(proposed, frame)
    if canonical != proposed:
        dossier["proposed_focus_raw"] = proposed
        dossier["proposed_focus_id"] = canonical


def audit_dossier(dossier: dict, resolver=None, quote_checker=None,
                  entailment_checker=None, allowed_identifiers=None) -> dict:
    """Evidence call for one dossier: split claims into surviving/struck.

    A claim is struck when the claim ledger rules fail it (no source,
    model-opinion source, tier 0 load-bearing, already struck) or when
    its citation fails the offline auditor (bad identifier format, or a
    quote_checked claim carrying no quote). Struck claims are returned
    with their reason codes and take no further part in the debate.

    resolver, when given, is a callable(identifier, identifier_type)
    returning a live resolution status (see madd/resolve.py). A claim
    whose identifier the registry reports as not_found is struck with
    reason citation_not_found_live, and one the registry reports as
    retracted is struck with reason citation_retracted_live. Any other
    status (resolved, lookup_error, format problems already handled
    above) never strikes on its own: a registry that cannot be reached
    proves nothing about the claim.

    quote_checker, when given, is a callable(claim) returning a quote
    check status (see madd/resolve.check_quote_against_source). It is
    consulted only for quote_checked claims that survived everything
    above, and only the quote_not_found status strikes, with reason
    quote_not_in_full_text: the source's open full text was retrieved
    and the quote the claim carries is not in it. Unavailable full
    text, like an unreachable registry, proves nothing.

    entailment_checker, when given, is a callable(claim) returning an
    entailment verdict (see madd/entailment.py). It is consulted only
    for surviving quote_checked claims, and only the refuted verdict
    strikes, with reason claim_refuted_by_its_quote: the passage the
    claim itself cites contradicts it. An unverifiable verdict, like
    an unreachable registry, proves nothing.

    allowed_identifiers, when given, is the retrieval-first rule: a
    set of (identifier_type, identifier) pairs drawn from the
    evidence the agents were actually given. A load-bearing claim
    citing anything outside that set is struck with reason
    citation_not_in_evidence, however real the outside source may be:
    the run's evidence, not the model's memory, is what may be cited.
    """
    claims = dossier.get("claims") if isinstance(dossier, dict) else None
    if not isinstance(claims, list):
        claims = []
    citation_entries = {}
    for entry in audit_citations({"claims": claims})["entries"]:
        citation_entries[entry["claim_id"]] = entry
    id_counts = {}
    for claim in claims:
        if isinstance(claim, dict) and claim.get("claim_id") is not None:
            id_counts[claim["claim_id"]] = id_counts.get(claim["claim_id"], 0) + 1
    surviving = []
    struck = []
    for claim in claims:
        if not isinstance(claim, dict):
            struck.append({"claim_id": "<not an object>", "reasons": ["claim_not_object"]})
            continue
        reasons = [e["code"] for e in validate_claim(claim)]
        if id_counts.get(claim.get("claim_id"), 0) > 1:
            # A duplicated claim_id makes the citation entry ambiguous:
            # the dict above can only hold one entry per id, so a clean
            # copy could mask a malformed twin. Every copy is struck,
            # matching the document-level duplicate rule in claims.py.
            reasons.append("duplicate_claim_id")
        entry = citation_entries.get(claim.get("claim_id", "<missing claim_id>"))
        if entry is not None:
            if not entry["format"]["ok"]:
                reasons.append("citation_" + entry["format"]["code"])
            for problem in entry["problems"]:
                reasons.append(problem["code"])
        if resolver is not None and not reasons:
            status = resolver(claim.get("source_identifier"),
                              claim.get("identifier_type"))
            if status == "not_found":
                reasons.append("citation_not_found_live")
            elif status == "retracted":
                reasons.append("citation_retracted_live")
        if (quote_checker is not None and not reasons
                and claim.get("verification_status") == "quote_checked"):
            if quote_checker(claim) == "quote_not_found":
                reasons.append("quote_not_in_full_text")
        if (entailment_checker is not None and not reasons
                and claim.get("verification_status") == "quote_checked"):
            if entailment_checker(claim) == "refuted":
                reasons.append("claim_refuted_by_its_quote")
        if (allowed_identifiers is not None and not reasons
                and claim.get("load_bearing")
                and claim.get("source_identifier")):
            key = (str(claim.get("identifier_type") or "").strip().lower(),
                   str(claim.get("source_identifier")).strip())
            if key not in allowed_identifiers:
                reasons.append("citation_not_in_evidence")
        if reasons:
            struck.append({"claim_id": claim.get("claim_id", "<missing claim_id>"),
                           "reasons": sorted(set(reasons))})
        else:
            surviving.append(copy.deepcopy(claim))
    return {"dossier_id": dossier.get("dossier_id"),
            "agent_id": dossier.get("agent_id"),
            "proposed_focus_id": dossier.get("proposed_focus_id"),
            "direction": dossier.get("direction"),
            "surviving_claims": surviving, "struck": struck}


def _rank_key(audited: dict) -> tuple:
    """Pairwise ranking key: audited focus score first (higher wins),
    then fewer struck claims, then dossier id for determinism."""
    score = focus_score({"claims": audited["surviving_claims"]})["score"]
    return (score, -len(audited["struck"]))


def rank_dossiers(audited_dossiers: list) -> list:
    """Pairwise ranking on the protocol rubric. Returns ranked summaries.

    Each dossier scores a win against every dossier it beats on
    (focus score, then fewer struck claims) and half a win on a tie.
    Sorting is by wins, then rubric key, then dossier_id, so the result
    is fully deterministic for the same inputs.
    """
    keys = {a["dossier_id"]: _rank_key(a) for a in audited_dossiers}
    summaries = []
    for a in audited_dossiers:
        wins = 0.0
        for b in audited_dossiers:
            if b["dossier_id"] == a["dossier_id"]:
                continue
            if keys[a["dossier_id"]] > keys[b["dossier_id"]]:
                wins += 1.0
            elif keys[a["dossier_id"]] == keys[b["dossier_id"]]:
                wins += 0.5
        summary = {"dossier_id": a["dossier_id"], "agent_id": a["agent_id"],
                   "proposed_focus_id": a["proposed_focus_id"],
                   "focus_score": keys[a["dossier_id"]][0],
                   "struck_count": len(a["struck"]), "wins": wins}
        if "proposed_focus_raw" in a:
            summary["proposed_focus_raw"] = a["proposed_focus_raw"]
        summaries.append(summary)
    summaries.sort(key=lambda s: (-s["wins"], -s["focus_score"], s["struck_count"],
                                  str(s["dossier_id"])))
    return summaries


def _cross_examination(audited_dossiers: list, ranking: list) -> tuple:
    """Structured cross-examination record (protocol step 3).

    Focus disagreement produces an objection from each dossier against
    each dossier arguing a different focus, naming the rival's
    surviving load-bearing claims as the ground that must be answered.
    Instant agreement triggers the red-team rule instead.
    """
    focuses = {a["proposed_focus_id"] for a in audited_dossiers}
    transcript = []
    if len(focuses) == 1:
        top_id = ranking[0]["dossier_id"]
        for a in audited_dossiers:
            transcript.append({
                "kind": "red_team_assigned_attack",
                "objector_agent_id": a["agent_id"],
                "target_dossier_id": top_id,
                "agreed_focus_id": next(iter(focuses)),
                "note": "instant agreement: agent assigned to argue against the "
                        "agreed focus using surviving claims only",
                "claim_ids": [c.get("claim_id") for c in a["surviving_claims"]
                              if c.get("load_bearing")],
            })
        return transcript, True
    for a in audited_dossiers:
        for b in audited_dossiers:
            if a["dossier_id"] == b["dossier_id"]:
                continue
            if a["proposed_focus_id"] == b["proposed_focus_id"]:
                continue
            transcript.append({
                "kind": "focus_disagreement",
                "objector_agent_id": a["agent_id"],
                "objector_focus_id": a["proposed_focus_id"],
                "target_dossier_id": b["dossier_id"],
                "target_agent_id": b["agent_id"],
                "target_focus_id": b["proposed_focus_id"],
                "claim_ids": [c.get("claim_id") for c in b["surviving_claims"]
                              if c.get("load_bearing")],
            })
    return transcript, False


def _evolve_spec(frame: dict, audited_dossiers: list, ranking: list,
                 dissent_log: list, dissent_none_reason) -> tuple:
    """Evolution round (step 5): merge surviving claims, ranked order first."""
    by_id = {a["dossier_id"]: a for a in audited_dossiers}
    top = by_id[ranking[0]["dossier_id"]]
    merged = []
    seen = set()
    duplicates = 0
    contributors = []
    for summary in ranking:
        source = by_id[summary["dossier_id"]]
        contributed = False
        for claim in source["surviving_claims"]:
            cid = claim.get("claim_id")
            if cid in seen:
                duplicates += 1
                continue
            seen.add(cid)
            merged.append(copy.deepcopy(claim))
            contributed = True
        if contributed:
            contributors.append(source["dossier_id"])
    spec = {
        "artifact_type": "consensus_spec",
        "schema_version": "0.1.0",
        "spec_id": "SPEC-" + str(frame.get("frame_id", "FRAME")),
        "frame_id": frame.get("frame_id"),
        "focus_id": top["proposed_focus_id"],
        "direction": top.get("direction"),
        "claims": merged,
        "dissent_log": dissent_log,
        "outcome": "no_go",
    }
    if dissent_none_reason is not None:
        spec["dissent_none_reason"] = dissent_none_reason
    evolution = {"base_dossier_id": top["dossier_id"],
                 "contributing_dossiers": contributors,
                 "claims_merged": len(merged),
                 "duplicate_claim_ids_skipped": duplicates}
    return spec, evolution


def frame_identifier_set(frame) -> set | None:
    """The (identifier_type, identifier) pairs a frame's evidence carries.

    Drawn from the Gate 0 case pack's claims and from any evidence
    entries on a prospective frame (including retrieved evidence).
    Returns None when the frame carries no identifiable evidence, so
    callers can tell "no evidence supplied" from "evidence supplied".
    """
    pairs = set()
    carriers = []
    if isinstance(frame, dict):
        pack = frame.get("case_pack")
        if isinstance(pack, dict):
            carriers += pack.get("claims") or []
        carriers += frame.get("evidence") or []
    for entry in carriers:
        if isinstance(entry, dict):
            ident = entry.get("source_identifier") or entry.get("identifier")
            itype = entry.get("identifier_type") or entry.get("type")
            if ident and itype:
                pairs.add((str(itype).strip().lower(), str(ident).strip()))
    return pairs or None


def run_debate(frame: dict, providers: list, judge_provider=None,
               budget: dict | None = None, budget_tracker=None,
               resolver=None, quote_checker=None, entailment_checker=None,
               retrieval_first: bool = False) -> dict:
    """Run the full debate protocol over a frame. Returns the run record.

    providers: at least two Provider objects (see madd/providers.py).
    judge_provider: optional third provider whose dossier, produced from
    the same frame, supplies the judge-swap stability comparison.
    budget: optional budget dict for madd.budget.BudgetTracker.
    budget_tracker: optional pre-built BudgetTracker, shared across
    calls by a runner so the cap applies to a whole multi-case run
    rather than to each debate separately. Takes precedence over
    budget when both are given.
    resolver: optional live citation resolver, callable(identifier,
    identifier_type) returning a status string; see audit_dossier.
    """
    if not isinstance(frame, dict) or not frame.get("frame_id"):
        raise ValueError("frame must be a dict with a frame_id")
    round_cap = frame.get("round_cap")
    if round_cap is not None and (isinstance(round_cap, bool)
                                  or not isinstance(round_cap, int)
                                  or round_cap < 1):
        raise ValueError("frame round_cap must be a positive integer when "
                         "present; a cap below 1 would forbid the debate "
                         "the protocol requires")
    providers = list(providers)
    if len(providers) < 2:
        raise ValueError("the debate protocol needs at least two research providers")
    tracker = budget_tracker if budget_tracker is not None else (
        BudgetTracker(budget) if budget is not None else None)

    def research(provider):
        """One provider call, reserved against the run budget first.

        The reserve is atomic (BudgetTracker.reserve), so parallel case
        debates sharing one tracker cannot overshoot the cap together.
        Transport retries the provider made inside the call are settled
        afterwards from its last_attempts count: they cost real calls,
        and if settling them crosses the cap the run stops there rather
        than absorbing them silently.
        """
        cost = float(getattr(provider, "cost_per_call_usd", 0.0) or 0.0)
        if tracker is not None:
            tracker.reserve(cost, note="research:" + str(getattr(provider, "name", "?")))
        dossier = provider.research(copy.deepcopy(frame))
        if not isinstance(dossier, dict):
            raise ValueError("provider " + str(getattr(provider, "name", "?"))
                             + " returned a non-dict dossier")
        if tracker is not None:
            extra = int(getattr(provider, "last_attempts", 1) or 1) - 1
            if extra > 0:
                tracker.record(cost * extra, calls=extra,
                                note="transport retries:" + str(getattr(provider, "name", "?")))
        return dossier

    # Step 1: blinded dossiers. Providers receive only the frame.
    dossiers = [research(p) for p in providers]
    dossier_ids = [d.get("dossier_id") for d in dossiers]
    if len(set(dossier_ids)) != len(dossier_ids):
        raise ValueError("two providers returned the same dossier_id ("
                         + ", ".join(str(x) for x in dossier_ids)
                         + "); dossier identifiers must be unique within a run, "
                           "or the ranking and the record would silently merge them")
    # Focus canonicalization: when the frame declares a focus_id, each
    # dossier's proposed focus is read against it before any comparison
    # is made (see canonical_focus_id), so agreement, ranking, and the
    # judge swap all judge the target named, not the spelling used.
    for d in dossiers:
        _canonicalize_dossier_focus(d, frame)
    # Step 2: evidence call.
    allowed = None
    if retrieval_first:
        # Retrieval-first: only the evidence this run actually supplied
        # (case pack or retrieved set) may be cited. A frame with no
        # identifiable evidence allows nothing, by design.
        allowed = frame_identifier_set(frame) or set()
    audited = [audit_dossier(d, resolver=resolver, quote_checker=quote_checker,
                             entailment_checker=entailment_checker,
                             allowed_identifiers=allowed)
               for d in dossiers]
    for d, a in zip(dossiers, audited):
        if "proposed_focus_raw" in d:
            a["proposed_focus_raw"] = d["proposed_focus_raw"]
    strike_list = [{"dossier_id": a["dossier_id"], "claim_id": s["claim_id"],
                    "reasons": s["reasons"]}
                   for a in audited for s in a["struck"]]
    # Ranking (protocol step 4) is computed before the cross-examination
    # record (step 3) is written because the red-team target and the
    # evolution base are both the top-ranked dossier. The two steps use
    # disjoint inputs (audited claims; dossier focuses), so the order
    # changes nothing in either result.
    ranking = rank_dossiers(audited)
    # Step 3: cross-examination record.
    transcript, red_team = _cross_examination(audited, ranking)
    dissent_log = [{"objector_agent_id": t["objector_agent_id"],
                    "target_dossier_id": t["target_dossier_id"],
                    "objection": "focus disagreement: objector proposes "
                                 + str(t.get("objector_focus_id"))
                                 + ", target proposes " + str(t.get("target_focus_id")),
                    "claim_ids": t["claim_ids"]}
                   for t in transcript if t["kind"] == "focus_disagreement"]
    dissent_none_reason = None
    if not dissent_log:
        dissent_none_reason = ("no unresolved objections: every dossier proposed "
                               "the same focus, and the instant-agreement red-team "
                               "round was run and recorded")
    # Step 5: evolution round.
    spec, evolution = _evolve_spec(frame, audited, ranking, dissent_log,
                                   dissent_none_reason)
    # Step 6: consensus tests, with judge swap when a judge is supplied.
    swapped_spec = None
    judge_info = None
    if judge_provider is not None:
        judge_dossier = research(judge_provider)
        _canonicalize_dossier_focus(judge_dossier, frame)
        judge_audited = audit_dossier(judge_dossier, resolver=resolver,
                                      quote_checker=quote_checker,
                                      entailment_checker=entailment_checker,
                                      allowed_identifiers=allowed)
        if "proposed_focus_raw" in judge_dossier:
            judge_audited["proposed_focus_raw"] = judge_dossier[
                "proposed_focus_raw"]
        swapped_spec = dict(spec)
        swapped_spec["focus_id"] = judge_audited["proposed_focus_id"]
        judge_info = {"provider": getattr(judge_provider, "name", None),
                      "model_version": getattr(judge_provider, "model_version", None),
                      "dossier_id": judge_audited["dossier_id"],
                      "proposed_focus_id": judge_audited["proposed_focus_id"],
                      "struck": judge_audited["struck"]}
        if "proposed_focus_raw" in judge_audited:
            judge_info["proposed_focus_raw"] = judge_audited[
                "proposed_focus_raw"]
        if judge_audited["proposed_focus_id"] != spec["focus_id"]:
            spec["dissent_log"] = list(spec["dissent_log"]) + [{
                "objector_agent_id": judge_audited["agent_id"],
                "target_dossier_id": ranking[0]["dossier_id"],
                "objection": "judge swap selected a different focus: "
                             + str(judge_audited["proposed_focus_id"]),
                "claim_ids": [],
            }]
    consensus = run_consensus_tests(dossiers, spec, swapped_spec)
    outcome = "locked" if consensus["all_passed"] else "no_go"
    spec["outcome"] = outcome

    # Step 7: frozen record.
    frame_prompt_hash = prompt_hash(canonical_json(frame))
    calls = [{"role": "research",
              "provider": getattr(p, "name", None),
              "model_version": getattr(p, "model_version", None),
              "agent_id": a["agent_id"], "dossier_id": a["dossier_id"],
              "prompt_hash": frame_prompt_hash}
             for p, a in zip(providers, audited)]
    if judge_info is not None:
        calls.append({"role": "judge",
                      "provider": judge_info["provider"],
                      "model_version": judge_info["model_version"],
                      "agent_id": None, "dossier_id": judge_info["dossier_id"],
                      "prompt_hash": frame_prompt_hash})
    manifest = build_manifest(
        model_name=", ".join(str(getattr(p, "name", "?")) for p in providers),
        model_version=", ".join(str(getattr(p, "model_version", "?")) for p in providers),
        prompt_text=canonical_json(frame),
        budget=tracker.to_dict() if tracker is not None else {},
        declared_use="research")
    manifest["calls"] = calls
    record = {
        "artifact_type": "debate_record",
        "schema_version": "0.1.0",
        "frame_id": frame.get("frame_id"),
        "round_cap": frame.get("round_cap"),
        "providers": [{"name": getattr(p, "name", None),
                       "model_version": getattr(p, "model_version", None),
                       "agent_id": a["agent_id"], "dossier_id": a["dossier_id"]}
                      for p, a in zip(providers, audited)],
        "strike_list": strike_list,
        "ranking": ranking,
        "rubric": {"applied": ["tier-weighted audited focus score",
                               "struck claim count"],
                   "not_applied": ["frame coverage: named in the protocol "
                                   "rubric but not mechanically defined, "
                                   "so it is not scored"]},
        "cross_examination": transcript,
        "red_team_round": red_team,
        "evolution": evolution,
        "judge_swap": judge_info,
        "consensus": consensus,
        "spec": spec,
        "outcome": outcome,
        "manifest": manifest,
        "budget": tracker.to_dict() if tracker is not None else None,
    }
    record["frozen_record"] = freeze_artifact(record)
    record["record_hash"] = canonical_hash(record["frozen_record"]["artifact"])
    return record
