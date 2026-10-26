# Target run: MTCH2 inhibition for fat reduction (2026-10-25)

Target: MTCH2 (inhibition), disease context obesity. Run id
target-mtch2-inhibition-2026-10-25, protocol mode simple, outcome
**designed** (design gate pass).

## What is here

- `bundle.json` - the frozen run bundle: the debate record, the
  strike list, the locked specification, the design brief, the four
  designer candidates, their audits and ranking. The research
  dossiers, the retrieved evidence set, and the entailment
  judgments are not in the bundle; they stay in the operator's
  harness workspace.
- `production_sheets.json` - production target sheets for the four
  ranked candidates, generated mechanically from the frozen bundle
  by madd/production.py after the run (the run predates sheets
  being built into design bundles; the frozen bundle itself is
  unchanged).
- `report.md` - the run report, production targets included.
- `build-guide-panel-b-cand-1.md` and
  `build-guide-panel-a-cand-1.md` - full step-by-step build guides
  for the two small-molecule candidates: proposed synthesis route
  (Hantzsch thiazole, hydrolysis, amide coupling), release QC
  against the production sheet, and a proposed confirmation
  plan. Each guide states its own status up front: a proposed
  route for an untested compound, not a validated protocol. The
  two antisense candidates have no build guides; their sheets
  record the modification pattern as unspecified, so a
  synthesizable guide cannot be written yet.

## The output

Four candidates ranked, two modalities:

1. panel-b-cand-1 (small molecule, chemical synthesis):
   2-phenylthiazole-4-carboxanilide chemotype proposed as an MTCH2
   insertase inhibitor. Formula C17H11F3N2OS, MW 348.349, InChIKey
   UWKQXUMWIHAVOQ-UHFFFAOYSA-N. Production-ready per its sheet;
   confirmation assay not specified.
2. panel-b-cand-2 (antisense oligonucleotide): 18-mer gapmer
   sequence TGCATGACCTCATGGACT against MTCH2 mRNA, GalNAc
   conjugation described in the designer's prose. NOT
   production-ready: the modification pattern exists only in that
   prose, not in the structured record the sheet reads.
3. panel-a-cand-1 (small molecule, chemical synthesis):
   thiazole-carboxamide chemotype from an independent designer;
   the 2-methyl-4-phenylthiazole-5-carboxamide regioisomer of
   candidate 1's scaffold family (see its build guide). Formula
   C18H13F3N2O2S, MW 378.375, InChIKey VPDLRLBLHTYWKA-UHFFFAOYSA-N.
   Production-ready per its sheet; confirmation assay not
   specified.
4. panel-a-cand-2 (antisense oligonucleotide): 20-mer gapmer
   sequence TCCAGGTCATCAGTGACTGC against MTCH2 mRNA. NOT
   production-ready, same modification-pattern reason as
   candidate 2.

## Provenance and caveats (part of this output)

- Status: a sample run, published to show the progress of the
  app. No target is locked in or selected by it; MTCH2 was the
  demonstration subject.
- Staffing: the provider panel and the designers were independent
  subagents of a single model family, standing in for a commercial
  roster that has not been recorded yet. Costs are recorded as 0.0
  because subagent compute is unmetered. This is a working run of
  the production path, not a scored Gate 0 run.
- Audit: 24 panel claims, entailment 15 supported / 9 partially
  supported / 0 refuted, and **12 claims struck, all
  quote_not_in_full_text**. The struck claims include the ones
  carrying the three strongest directional papers (the EMBO
  Journal adipogenesis study, PMID 39753955; the thermogenesis
  paper, PMID 40051328; the adipocyte CPT1 paper, PMID 41044057):
  the panel marked title-level quotes as quote_checked and the
  live check struck them. The target locked on the 6 surviving
  load-bearing claims (the direction-unknown gastric-bypass
  association, an obese-mouse exercise finding, the ARMC1
  preprint, and the BAX/BAK and pleiotropy safety claims). The
  design therefore rests on a thinner, partly direction-neutral
  audited base than the outcome line alone suggests.
- The candidates are untested model proposals. No MTCH2 inhibitor
  is a known validated ligand, nothing here has been synthesized
  or assayed, and the underlying biology evidence for inhibiting
  MTCH2 for fat reduction is cell and mouse work. The safety
  claims in the locked spec (MTCH2 promotes BAX/BAK apoptotic pore
  growth; roles across metabolic, neurodegenerative, cancer, and
  developmental biology) are design constraints, not solved
  problems.
