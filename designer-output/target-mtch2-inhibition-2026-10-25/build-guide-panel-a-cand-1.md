# Build guide: panel-a-cand-1 (MTCH2 inhibitor candidate)

Status: synthesis plan for an untested model proposal. The route
below is a proposed route written for this candidate; no
retrosynthesis tool ran on it, and the compound has never been
made or assayed. Conditions are standard medicinal-chemistry
starting points, to be optimized at the bench. Research use only,
in a qualified laboratory; not for human use.

## What is being made

- Candidate: panel-a-cand-1, ranked 3 of 4, production sheet
  verdict: production-ready (confirmation assay unspecified -
  Stage 8 proposes the same plan as panel-b-cand-1).
- Name: N-[4-(trifluoromethoxy)phenyl]-2-methyl-4-phenyl-1,3-
  thiazole-5-carboxamide.
- SMILES (canonical):
  Cc1nc(-c2ccccc2)c(C(=O)Nc2ccc(OC(F)(F)F)cc2)s1
- Formula C18H13F3N2O2S, MW 378.375, InChIKey
  VPDLRLBLHTYWKA-UHFFFAOYSA-N (from the production sheet).
- Targeted process: inhibiting MTCH2 for fat reduction (source
  run target-mtch2-inhibition-2026-10-25).
- Batch target: 250 mg final compound at discovery scale.

Read the structure before starting: this is the same thiazole-
carboxamide family as panel-b-cand-1 but a different
regioisomer. The thiazole carries a methyl at C2, the phenyl at
C4, and the carboxamide at C5; there is no thiazole ring proton.
That changes both the starting materials and the NMR release
checks below - do not reuse panel-b-cand-1's checkpoints.

The molecule is an amide of two building blocks: 2-methyl-4-
phenylthiazole-5-carboxylic acid and 4-(trifluoromethoxy)
aniline. The build makes the acid first (Hantzsch thiazole
synthesis, then ester hydrolysis), then couples it.

## Stage 1 - Materials

Reagents:
- Thioacetamide (Step 1)
- Ethyl 2-bromobenzoylacetate (ethyl 2-bromo-3-oxo-3-
  phenylpropanoate) (Step 1)
- Lithium hydroxide (Step 2); 1 M hydrochloric acid (workups)
- 4-(trifluoromethoxy)aniline (Step 3)
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
throughout. Ethyl 2-bromobenzoylacetate is a lachrymator-class
alpha-bromo carbonyl; HATU is a skin sensitizer; DMF requires
glove discipline; thioacetamide is a suspected carcinogen and
must be handled with particular care. The product's own hazard
profile is unknown - handle it as an uncharacterized research
chemical.

## Stage 2 - Step 1: thiazole ring formation (Hantzsch)

Reaction: thioacetamide + ethyl 2-bromobenzoylacetate ->
ethyl 2-methyl-4-phenylthiazole-5-carboxylate.

Mapping, so the regiochemistry is checkable: the thioacetamide
carbon becomes C2 (its methyl becomes the 2-methyl); the keto
carbon of the bromo ketoester becomes C4 (its phenyl becomes the
4-phenyl); the brominated alpha carbon becomes C5 (its ester
becomes the 5-carboxylate).

1. Charge a flask with thioacetamide (1.0 eq) and ethanol
   (about 10 mL per gram).
2. Add ethyl 2-bromobenzoylacetate (1.0 eq) portionwise at room
   temperature.
3. Heat to reflux and hold 4-8 hours.
4. In-process check: TLC or LC-MS for consumption of the bromo
   ketoester; the ester product shows [M+H]+ 248.07.
5. Cool, concentrate under reduced pressure.
6. Purify: silica column (hexane / ethyl acetate gradient) or
   recrystallization from ethanol.
7. Dry under vacuum. Record yield and appearance.

Checkpoint: LC-MS [M+H]+ 248.074 (MW 247.32). 1H NMR should
show the ethyl ester quartet and triplet, a 2-methyl singlet,
and phenyl protons only in the aromatic region - no thiazole
proton exists in this isomer, so any sharp singlet near
8.4-8.6 ppm integrating to 1H means the wrong regioisomer or an
impurity; stop and identify it before proceeding.

## Stage 3 - Step 2: ester hydrolysis

Reaction: ethyl 2-methyl-4-phenylthiazole-5-carboxylate ->
2-methyl-4-phenylthiazole-5-carboxylic acid.

1. Dissolve the ester (1.0 eq) in THF / water 1:1 (or ethanol /
   water).
2. Add lithium hydroxide (2-3 eq). Stir at room temperature
   2-16 hours.
3. In-process check: LC-MS; the acid shows [M+H]+ 220.04 and
   the ester peak at 248.07 should be gone.
4. Remove the organic solvent under reduced pressure.
5. Acidify the aqueous residue to pH 2-3 with 1 M HCl, cold.
6. Collect the precipitated acid by filtration, wash with cold
   water, dry under vacuum.

Checkpoint: 1H NMR loss of the ethyl quartet / triplet; LC-MS
[M+H]+ 220.043 (MW 219.26).

## Stage 4 - Step 3: amide coupling

Reaction: 2-methyl-4-phenylthiazole-5-carboxylic acid +
4-(trifluoromethoxy)aniline -> panel-a-cand-1.

1. Charge the acid (1.0 eq), 4-(trifluoromethoxy)aniline
   (1.05 eq), and HATU (1.2 eq) in dry DMF (about 10 mL per
   gram of acid).
2. Add DIPEA (3.0 eq). Stir at room temperature 12-18 hours.
   (Alternate system: EDCI 1.2 eq + HOBt 1.2 eq + DIPEA 3 eq,
   same conditions.)
3. In-process check: LC-MS for the product at [M+H]+ 379.07 and
   disappearance of the acid at 220.04. If acid remains after
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
   of a solid (appearance to be recorded, not assumed).

## Stage 6 - Identity and purity release (against the production sheet)

All of these must pass before the batch counts as the candidate:

1. LC-MS: [M+H]+ 379.07.
2. HRMS: calculated [M+H]+ for C18H14F3N2O2S+ 379.0723; accept
   within 5 ppm.
3. 1H NMR (DMSO-d6, expected regions - confirm against the
   actual spectrum): amide NH singlet far downfield (about
   10.3-10.8 ppm, 1H); 2-methyl singlet (about 2.7-2.8 ppm,
   3H); aromatic multiplets 7.2-7.6 ppm integrating to 9H
   total; and NO thiazole proton - this isomer has none.
4. 13C NMR: amide carbonyl about 158-162 ppm; the OCF3 carbon
   as a quartet near 120 ppm with a one-bond C-F coupling of
   about 257 Hz.
5. 19F NMR: one singlet near -57.5 ppm (aryl OCF3). Note this
   differs from panel-b-cand-1's CF3 near -61 ppm; the two
   candidates are distinguishable by 19F alone.
6. HPLC purity at least 95 percent (target 98), single main
   peak.
7. Record: appearance, melting point if taken, batch weight,
   and the full spectra in the batch record.

A failure at any point means the batch is not panel-a-cand-1
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

Run this candidate side by side with panel-b-cand-1 under the
identical protocol so the two chemotypes are comparable.

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
   (panel-a-cand-1, batch 001), every stage's yields, spectra,
   and deviations.
2. Retain a sealed reference sample (at least 10 mg).
3. Update the candidate's status from designed to synthesized
   only after Stage 6 passes, and to confirmed only after
   Stage 8's advance criteria are met. Until then it remains
   what the run record says it is: an untested model proposal.

## What this guide does not cover

- The two antisense candidates from the same run: their build
  guides cannot be written yet. Their production sheets record
  the modification pattern as unspecified (it exists only in
  designer prose); a synthesizable guide needs that pattern
  fixed first, then solid-phase oligonucleotide synthesis
  planning.
- Scale-up, GMP, formulation for animals, and any human use:
  all out of scope for a discovery-stage research candidate.
