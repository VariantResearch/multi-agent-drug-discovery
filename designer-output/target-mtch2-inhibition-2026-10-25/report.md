# MADD target run target-mtch2-inhibition-2026-10-25

- Target: MTCH2 (target)
- Molecular target: MTCH2
- Disease context: obesity
- Protocol mode: simple
- Debate outcome: locked
- Outcome: designed

## Research stage

# Frame run report

Run: target-mtch2-inhibition-2026-10-25-frame
Frame: TARGET-mtch2
Outcome: locked
Focus: MTCH2

## Consensus tests

- agreement: pass (focus identifiers seen: MTCH2)
- survival: pass (load-bearing claim audit errors: 0)
- evidence_floor: pass (best audited tier: 3)
- dissent_log: pass (dissent entries: 0)
- stability: not applied (protocol mode has no judge; the judge-swap stability test is not applied)

Strikes at the evidence call: 12
Dissent entries: 0


## Design stage

# Design run design-spec-target-mtch2

Target: MTCH2 (inhibition) | Disease: obesity | Spec: SPEC-TARGET-mtch2
Designer: model-panel | Gate: pass

## Gate checks
- spec_locked: pass (brief built from locked spec SPEC-TARGET-mtch2)
- candidates_ranked: pass (4 ranked, 0 excluded)
- real_candidates_ranked: pass (4 non-synthetic candidates ranked)
- tools_license_clean: pass (no blocked tool runs)

## Ranked candidates
1. panel-b-cand-1 - audited load-bearing claims: 0, unverified predictions: 3
2. panel-b-cand-2 - audited load-bearing claims: 0, unverified predictions: 3
3. panel-a-cand-1 - audited load-bearing claims: 0, unverified predictions: 3
4. panel-a-cand-2 - audited load-bearing claims: 0, unverified predictions: 3

## Excluded candidates
(none)

## Tool runs
- RDKit: completed (checked 2, valid 2, invalid 0)
- ADMET-AI: completed (0 outputs)

## Designer notes
- provider panel-c: design call failed: RuntimeError: no design completion recorded for panel-c

## Production targets

### panel-b-cand-1 (small_molecule)
- Structure (smiles): O=C(Nc1ccc(C(F)(F)F)cc1)c2csc(n2)c3ccccc3
- Canonical SMILES: O=C(Nc1ccc(C(F)(F)F)cc1)c1csc(-c2ccccc2)n1
- InChIKey: UWKQXUMWIHAVOQ-UHFFFAOYSA-N
- Formula: C17H11F3N2OS | MW: 348.349
- Production route: chemical synthesis
- Production ready: yes
- Not specified: the confirmation assay that would verify the targeted process for this candidate

### panel-b-cand-2 (biologic)
- Structure (sequence): TGCATGACCTCATGGACT
- Length: 18 | Alphabet check: pass
- Production route: biologic production (oligonucleotide synthesis for antisense or siRNA constructs, recombinant expression for protein constructs)
- Production ready: no
- Not specified: the modification pattern (backbone and sugar or terminal modifications, conjugation) a synthesized sequence candidate is made with
- Not specified: the confirmation assay that would verify the targeted process for this candidate

### panel-a-cand-1 (small_molecule)
- Structure (smiles): Cc1nc(c2ccccc2)c(C(=O)Nc2ccc(OC(F)(F)F)cc2)s1
- Canonical SMILES: Cc1nc(-c2ccccc2)c(C(=O)Nc2ccc(OC(F)(F)F)cc2)s1
- InChIKey: VPDLRLBLHTYWKA-UHFFFAOYSA-N
- Formula: C18H13F3N2O2S | MW: 378.375
- Production route: chemical synthesis
- Production ready: yes
- Not specified: the confirmation assay that would verify the targeted process for this candidate

### panel-a-cand-2 (biologic)
- Structure (sequence): TCCAGGTCATCAGTGACTGC
- Length: 20 | Alphabet check: pass
- Production route: biologic production (oligonucleotide synthesis for antisense or siRNA constructs, recombinant expression for protein constructs)
- Production ready: no
- Not specified: the modification pattern (backbone and sugar or terminal modifications, conjugation) a synthesized sequence candidate is made with
- Not specified: the confirmation assay that would verify the targeted process for this candidate

