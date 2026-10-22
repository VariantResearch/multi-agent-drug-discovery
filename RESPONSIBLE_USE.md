# Responsible Use

This project is a research-design and evidence-audit scaffold. Its rules
below are part of the design, not optional guidance.

## Scope exclusions

- No pathogen targets. No toxin targets. No work aimed at increasing harm,
  transmissibility, immune evasion, or environmental persistence of any
  organism, and no design of agents intended to harm humans, animals, or
  crops.
- No human dosing recommendations. Nothing produced by this software is a
  dose, a dosing schedule, or advice to administer anything to a person.
- No clinical advice. Nothing here diagnoses, treats, or recommends
  treatment for any person.
- No autonomous external submissions. The software must not submit papers,
  filings, orders, messages, or applications to any external body on its
  own.
- No autonomous lab orders. The software must not order synthesis,
  assays, materials, or services. Any wet-lab step is a handoff to named
  humans operating under their own approvals and procedures.

## Human sign-off gate

- A named human must sign off before a run moves from validation to any
  external step, including sharing a candidate with a laboratory partner.
- The sign-off, the artifact hashes signed off on, and the gate reports
  relied on must be recorded in the run manifest.

## Honest labelling rule

- Every output is labelled by the highest validation gate it has actually
  passed, using the gate names in docs/PHASE0_SPEC.md.
- An output that has passed only computational checks must say so in the
  output itself. It must not be described, in any document generated from
  it, as tested, validated in vitro, validated in vivo, or effective.
- Agent agreement, model confidence, and a generated paper draft are not
  validation gates and must never be presented as one.

## If in doubt

Stop the run, record the question in the dissent log, and leave the
decision to the human sign-off gate. A stopped run is a valid outcome.
A no-go is a valid outcome.
