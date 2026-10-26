# Designer output

Published output from MADD target runs: the designer stage's ranked
candidates and their production target sheets, kept with the frozen
run bundle that produced them. The bundle holds the debate record,
the strike list, the locked specification, and the candidate
audits; the wider audit record (the research dossiers, the
retrieved evidence set, and the entailment judgments) stays in the
operator's harness workspace.

Each run folder contains:

- `bundle.json` - the frozen target-run bundle, byte-identical to
  the copy in the local `runs/` directory (which stays gitignored);
  its frozen envelope hash verifies.
- `production_sheets.json` - one production sheet per ranked
  candidate: exactly what would be made for the targeted process,
  its computed identity, its production route, and what the designer
  did not specify.
- `report.md` - the run report rendered from the bundle, with the
  production targets section included.
- `build-guide-<candidate>.md` - when written, a full step-by-step
  build guide for a candidate: proposed route, release QC against
  its production sheet, and a proposed confirmation plan, each
  labelled as proposal work for a compound not yet made or
  assayed.
- `README.md` - provenance for the run and the caveats that travel
  with its output.

Publication here does not select or lock in a target. These are
sample runs that show the pipeline's progress; a run's target is
its demonstration subject, not a chosen production target.

Designer output is model proposal work that carries the validation
its run actually performed: the claims were mechanically audited
(the strike list is part of the output and stays attached to it),
the small-molecule structures were RDKit-validated with computed
identities on their production sheets, the design gate passed,
and the frozen bundle's hash verifies. A production sheet
describes a candidate precisely enough to be made. None of that
is evidence that the candidate works, binds, or is safe: no
candidate here has been synthesized or assayed, and synthesis
followed by the confirmation assay is the step that would test
it. (Wording corrected 2026-10-26 after a full validation of the
written record against the code and the run artifacts; the
earlier text called the output simply "untested", which erased
the computational validation the run record shows.)
