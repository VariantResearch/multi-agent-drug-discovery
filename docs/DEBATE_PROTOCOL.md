# Debate Protocol

Status: implemented in madd/debate.py on 2026-10-23. Debates have
been run against mock and stub providers in the test suite, and end
to end with agent-staffed providers in the 2026-10-25 validation
runs (docs/VALIDATION_RUN_2026-10-25.md). No debate with live
commercial model accounts has taken place, and no research result
in this repository comes from a debate.

## Participants and roles

- Research agents: two or more agents from different model families, each
  assigned the same frame independently.
- Evidence auditor: a tool-based checker (code, not an agent vote) that
  runs the claim and citation audits. Its strike decisions are not subject
  to agent vote.
- Judge: an agent or deterministic scorer that applies the consensus tests
  in madd/consensus.py. The judge produces scores; it does not supply
  evidence.
- Human sign-off: see RESPONSIBLE_USE.md. The protocol ends at a
  recommendation to a human, never at an external action.

## Protocol modes

A run declares one of three protocol modes in its configuration
(the mode field; madd/config.py and madd/runner.py enforce the
shapes). The modes count distinct models, not agents: every mode
fields a research panel of at least two agents, and the steps and
the evidence call are the same in all three. What changes is how
many models the panel spans and whether a judge model sits over it.

- simple: every research agent runs one and the same model. There
  is no judge, so the judge-swap stability test is recorded as not
  applied; a specification locks on agreement, survival, and the
  evidence floor among the same-model agents. This is the cheapest
  configuration and the one the 2026-10-25 agent-panel validation
  runs effectively staffed.
- dual: the research agents span two models. Still no judge, so
  stability is likewise recorded as not applied; the gain over
  simple is a second model's independent read of the same evidence.
- dual_judge: the research agents span two models and a judge
  model supplies the swap dossier, so all four consensus tests are
  applied, stability included. This is the full protocol, and the
  mode a scored Gate 0 run uses, because the approved thresholds
  judge judge-swap stability.

A run that declares no mode keeps the original behaviour: a panel
of two or more providers of any composition, a judge when one is
supplied, and stability unestablished (outcome no_go) when none is.

## Steps

1. Blinded dossiers. Each research agent works alone, cannot see any other
   dossier, and submits a sealed dossier: claims with sources, a proposed
   focus, and an explicit list of what it could not verify.
2. Evidence call. Before any argument, the auditor checks every claim in
   every dossier. Claims that fail the ledger rules or the citation format
   checks are struck and listed. Struck claims are out of the debate.
   When the run config enables them, the evidence call also runs live
   checks, each striking only on positive evidence: identifier resolution
   against the owning registries (an identifier that does not resolve
   strikes; a lookup failure strikes nothing), Crossref retraction flags,
   full-text quote checks against the record abstract and Europe PMC
   open text (a quote absent from both, with the full text retrieved,
   strikes; unavailable text strikes nothing, and the abstract alone
   never strikes), judged
   entailment (a claim refuted by its own cited passage strikes), and,
   in retrieval-first runs, confinement to the identifiers in the
   evidence the run supplied.
3. Cross-examination. Each agent must state, for each rival dossier, the
   strongest objection it can support from surviving claims, and must
   answer objections to its own dossier by pointing to surviving claims
   or by withdrawing the point. New claims introduced here enter the
   ledger and are audited before they can be used.
4. Pairwise ranking. Surviving dossiers are ranked pairwise on the
   pre-declared rubric: tier-weighted audited evidence and number of
   struck claims (fewer is better). Prose quality is not a rubric item.
   A third item, coverage of the frame, is recorded in every record's
   rubric as not_applied: it is not scored until an implementation
   exists, and the record says so rather than implying a score.
5. Evolution round. The top-ranked dossier may be revised once, using only
   surviving claims from any dossier, with every reused claim keeping its
   original identifier. The merged specification's claim ledger is
   re-audited by the survival consensus test; its claims already
   survived the step 2 evidence call, and no second citation audit runs
   on the merge.
6. Consensus tests. The revised (or top) dossier is tested as a candidate
   specification under the four tests below, implemented in
   madd/consensus.py.
7. Record. The outcome is a locked specification or a no-go, plus the
   dissent log, plus the auditor's strike list. All three are frozen and
   hashed together.

## The four consensus tests

- Agreement - all research dossiers propose the same focus identifier.
  When the frame declares a canonical focus_id, each dossier's proposal
  is first read against it (canonical_focus_id in madd/debate.py): a
  proposal that is the frame's own target string, or a shortening or
  expansion of it, counts as the canonical identifier, and the model's
  original string is preserved in the record as proposed_focus_raw. The
  test therefore judges whether the dossiers name the same target, not
  whether they spell it identically. Disagreement is not papered over by
  the judge; it is recorded and the specification, if any, must come
  from the evolution round.
- Survival - every load-bearing claim in the candidate specification
  passes the claim ledger audit. One failed load-bearing claim fails the
  test.
- Evidence floor - the candidate specification rests on at least one
  audited claim at tier 3 or better. A specification resting only on
  tier 4 or tier 5 claims, or on no audited claims, fails.
- Stability - re-running the judging step with a different judge (judge
  swap) selects the same focus identifier. If the answer changes with the
  judge, the consensus is a property of the judge, not of the evidence,
  and the test fails.

All four tests must pass to lock a specification. Any failure produces a
no-go or a return to step 3, within the round cap below.

## Anti-groupthink rules

- Round cap: cross-examination and evolution together are capped at a
  number of rounds fixed in the frame, before the run starts. Reaching the
  cap without passing all four tests is a no-go, not a prompt to keep
  arguing. Implementation note: the engine runs a single pass of steps
  1 to 7, so the cap is enforced as a validity floor (a frame whose
  round_cap is below 1 is refused before any provider is called) and
  recorded in the record; multi-pass iteration is not implemented.
- Mandatory dissent log: every run produces a dissent log, including
  runs that end in agreement. Unresolved objections are recorded verbatim,
  with the dissenting agent and the claim identifiers involved. An empty
  dissent log is valid only if a dissent_none_reason is recorded.
- No agent may cite another agent as evidence. A claim whose source is an
  agent, a model, or the debate transcript is tier 0 and cannot be
  load-bearing.
- Instant agreement triggers a red-team round: if all dossiers agree on
  the focus in the blinded round, one extra cross-examination round is
  run in which each agent is assigned to argue against the agreed focus
  using surviving claims only. Agreement that survives an assigned attack
  is recorded; agreement is still not evidence.
- No confidence language in outputs: dossiers and specifications record
  tiers, counts, and audit outcomes. Words asserting confidence are not a
  field in any schema and play no part in scoring.
