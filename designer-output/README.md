# Designer output

Published output from MADD target runs: the designer stage's ranked
candidates and their production target sheets, kept with the frozen
run bundle that produced them so every claim in the output can be
traced back to its audited record.

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
  labelled as proposal work for an untested compound.
- `README.md` - provenance for the run and the caveats that travel
  with its output.

Designer output is untested model proposal work. A production sheet
describes a candidate precisely enough to be made; it is not
evidence that the candidate works, binds, or is safe. The audit
record in the bundle, including every strike, is part of the output
and stays attached to it.
