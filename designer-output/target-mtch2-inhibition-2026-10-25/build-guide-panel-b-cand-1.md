# Build guide: panel-b-cand-1 (MTCH2 inhibitor candidate)

Status: synthesis plan for a model-proposed candidate. The
candidate's structure and computed identity were validated in
its run record (RDKit checks, mechanical audit, design gate);
the compound itself has never been made or assayed. The route
below is a proposed route written for this candidate; no
retrosynthesis tool ran on it. Conditions are standard medicinal-chemistry
starting points, to be optimized at the bench. Research use only,
in a qualified laboratory; not for human use.

## What is being made

- Candidate: panel-b-cand-1, ranked 1 of 4, production sheet
  verdict: production-ready (confirmation assay unspecified -
  Stage 8 proposes one).
- Name: N-[4-(trifluoromethyl)phenyl]-2-phenyl-1,3-thiazole-4-
  carboxamide.
- SMILES: O=C(Nc1ccc(C(F)(F)F)cc1)c1csc(-c2ccccc2)n1
- Formula C17H11F3N2OS, MW 348.349, InChIKey
  UWKQXUMWIHAVOQ-UHFFFAOYSA-N (from the production sheet).
- Targeted process: inhibiting MTCH2 for fat reduction (source
  run target-mtch2-inhibition-2026-10-25).
- Batch target: 250 mg final compound at discovery scale.

The molecule is an amide of two building blocks: 2-phenylthiazole-
4-carboxylic acid and 4-(trifluoromethyl)aniline. The build makes
the acid first (Hantzsch thiazole synthesis, then ester
hydrolysis), then couples it. Candidate panel-a-cand-1 is the same
chemotype with a different aniline and a 5-methyl thiazole acid;
the same route family applies.

## Stage 1 - Materials

Reagents:
- Thiobenzamide (Step 1)
- Ethyl bromopyruvate (ethyl 3-bromo-2-oxopropanoate) (Step 1)
- Lithium hydroxide (Step 2); 1 M hydrochloric acid (workups)
- 4-(trifluoromethyl)aniline (Step 3)
- HATU (Step 3 coupling) or EDCI + HOBt as the alternate coupling
  system; DIPEA (base)
- Solvents: ethanol, THF, DMF, ethyl acetate, hexane (column),
  DMSO (Stage 7)
- Silica gel for chromatography, or ethanol for recrystallization
- Drying agent: anhydrous sodium sulfate

Equipment: standard reflux setup, rotary evaporator, filtration,
column chromatography, TLC and LC-MS access, NMR and HRMS access,
analytical HPLC.

Safety, briefly: work in a fume hood with standard PPE
throughout. Ethyl bromopyruvate is a lachrymator; HATU is a skin
sensitizer; DMF requires glove discipline; thiobenzamide and the
aniline are harmful if swallowed. The product's own hazard
profile is unknown - handle it as an uncharacterized research
chemical.

## Stage 2 - Step 1: thiazole ring formation (Hantzsch)

Reaction: thiobenzamide + ethyl bromopyruvate ->
ethyl 2-phenylthiazole-4-carboxylate.

1. Charge a flask with thiobenzamide (1.0 eq) and ethanol
   (about 10 mL per gram).
2. Add ethyl bromopyruvate (1.05 eq) portionwise at room
   temperature.
3. Heat to reflux and hold 4-8 hours.
4. In-process check: TLC or LC-MS for consumption of
   thiobenzamide; the ester shows [M+H]+ 234.06.
5. Cool, concentrate under reduced pressure.
6. Purify: silica column (hexane / ethyl acetate gradient) or
   recrystallization from ethanol.
7. Dry under vacuum. Record yield and appearance (expected:
   pale solid).

Checkpoint: LC-MS [M+H]+ 234.058 (MW 233.29). 1H NMR should show
the ethyl ester quartet and triplet plus the thiazole and phenyl
protons; do not proceed on mass alone if the NMR shows a second
major component.

## Stage 3 - Step 2: ester hydrolysis

Reaction: ethyl 2-phenylthiazole-4-carboxylate ->
2-phenylthiazole-4-carboxylic acid.

1. Dissolve the ester (1.0 eq) in THF / water 1:1 (or ethanol /
   water).
2. Add lithium hydroxide (2-3 eq). Stir at room temperature
   2-16 hours.
3. In-process check: LC-MS; the acid shows [M+H]+ 206.03 and the
   ester peak at 234.06 should be gone.
4. Remove the organic solvent under reduced pressure.
5. Acidify the aqueous residue to pH 2-3 with 1 M HCl, cold.
6. Collect the precipitated acid by filtration, wash with cold
   water, dry under vacuum.

Checkpoint: 1H NMR loss of the ethyl quartet / triplet; LC-MS
[M+H]+ 206.027 (MW 205.24).

## Stage 4 - Step 3: amide coupling

Reaction: 2-phenylthiazole-4-carboxylic acid +
4-(trifluoromethyl)aniline -> panel-b-cand-1.

1. Charge the acid (1.0 eq), 4-(trifluoromethyl)aniline
   (1.05 eq), and HATU (1.2 eq) in dry DMF (about 10 mL per
   gram of acid).
2. Add DIPEA (3.0 eq). Stir at room temperature 12-18 hours.
   (Alternate system: EDCI 1.2 eq + HOBt 1.2 eq + DIPEA 3 eq,
   same conditions.)
3. In-process check: LC-MS for the product at [M+H]+ 349.06 and
   disappearance of the acid at 206.03. If acid remains after
   18 hours, add 0.2 eq HATU and 1 eq DIPEA and continue
   4 hours before working up.
4. Workup: dilute with ethyl acetate; wash with 1 M HCl, then
   saturated sodium bicarbonate, then brine.
5. Dry the organic layer over sodium sulfate, filter,
   concentrate.

## Stage 5 - Purification

1. Silica column, hexane / ethyl acetate gradient (start 4:1,
   move to 1:1 as the product elutes).
2. Pool clean fractions by TLC / LC-MS; concentrate.
3. If purity is already at target, a recrystallization from hot
   ethanol can replace or follow the column.
4. Dry to constant weight under vacuum. Target: at least 250 mg
   of an off-white to white solid (appearance to be recorded,
   not assumed).

## Stage 6 - Identity and purity release (against the production sheet)

All five must pass before the batch counts as the candidate:

1. LC-MS: [M+H]+ 349.06.
2. HRMS: calculated [M+H]+ for C17H12F3N2OS+ 349.0617; accept
   within 5 ppm.
3. 1H NMR (DMSO-d6, expected regions - confirm against the actual
   spectrum): amide NH singlet far downfield (about 10.5-11 ppm,
   1H); thiazole H-5 singlet (about 8.4-8.6 ppm, 1H); aromatic
   multiplets 7.4-8.1 ppm integrating to 9H total.
4. 13C NMR: amide carbonyl about 160 ppm; the CF3 carbon as a
   quartet near 124 ppm with a large one-bond C-F coupling
   (about 272 Hz).
5. 19F NMR: one singlet near -61 ppm (aryl CF3).
6. HPLC purity at least 95 percent (target 98), single main
   peak.
7. Record: appearance, melting point if taken, batch weight,
   and the full spectra in the batch record.

A failure at any point means the batch is not panel-b-cand-1
yet: re-purify once; if HRMS or NMR still disagrees, stop and
re-examine the route rather than re-labeling the material.

## Stage 7 - Test preparation

1. Prepare a 10 mM stock in DMSO; confirm complete dissolution
   (warm gently and sonicate if needed; record what it took).
2. Check kinetic solubility in the assay buffer at the top test
   concentration; note any precipitation.
3. Aliquot to avoid freeze-thaw cycles; store at -20 C,
   desiccated, labeled with candidate id, batch id, date, and
   concentration.

## Stage 8 - Proposed biological confirmation

The production sheet records the confirmation assay as not
specified; this stage proposes one. It is a plan, not a validated
protocol: no MTCH2 inhibitor assay is established, and binding
of this compound to MTCH2 is unproven. The plan tests the
expected on-mechanism phenotype plus genetic dependence, in a
qualified cell-biology setting. Any animal work is out of scope
here and would need its own approvals.

1. Model: adipocyte differentiation system (3T3-L1 or human
   preadipocytes).
2. Dose the compound across differentiation, 0.1-30 uM,
   half-log steps, vehicle control (0.1 percent DMSO).
3. Positive control: MTCH2 siRNA knockdown arm.
4. Readouts:
   - Lipid accumulation (Oil Red O or BODIPY staining) -
     inhibiting MTCH2 is expected to reduce adipogenesis.
   - Mitochondrial morphology by imaging - the expected
     on-mechanism phenotype is network fragmentation.
   - Respiration (Seahorse or equivalent): basal and maximal
     oxygen consumption and fuel preference.
   - Cytotoxicity counter-screen (for example CellTiter-Glo)
     at every dose.
   - Apoptosis markers (caspase activity): the locked
     specification carries a BAX/BAK liability for MTCH2, so
     cell death must be measured, not assumed absent.
5. Specificity check: repeat the key doses in MTCH2-knockdown
   cells; a genuinely MTCH2-mediated effect should shrink when
   the target is already depleted.
6. Proposed advance criteria: dose-dependent reduction in lipid
   accumulation with mitochondrial fragmentation, at
   concentrations with under 20 percent cytotoxicity, and the
   effect blunted in MTCH2-low cells.
7. Proposed kill criteria: activity that tracks only the
   cytotoxicity curve, no phenotype separation from vehicle, or
   no genetic-dependence signal.

## Stage 9 - Records and status

1. Batch record: batch id tied to candidate id
   (panel-b-cand-1, batch 001), every stage's yields, spectra,
   and deviations.
2. Retain a sealed reference sample (at least 10 mg).
3. Update the candidate's status from designed to synthesized
   only after Stage 6 passes, and to confirmed only after
   Stage 8's advance criteria are met. Until then it remains
   what the run record says it is: a computationally validated model proposal, not yet made or assayed.

## What this guide does not cover

- The two antisense candidates from the same run: their build
  guides cannot be written yet. Their production sheets record
  the modification pattern as unspecified (it exists only in
  designer prose); a synthesizable guide needs that pattern
  fixed first, then solid-phase oligonucleotide synthesis
  planning.
- Scale-up, GMP, formulation for animals, and any human use:
  all out of scope for a discovery-stage research candidate.
