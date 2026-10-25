# Contributing

Contributions are welcome if they keep the project's evidence standard.
A change that weakens an evidence rule will not be merged, however useful
it looks.

## Evidence rules for contributions

- No real-world factual claim in code, docs, fixtures, or commit text
  without a primary-source identifier recorded next to it. If a fact is
  not yet established, write "not yet established" instead of filling in a
  plausible value.
- Do not add invented people, firms, certifications, statistics, event
  dates, or precedent claims to documentation.
- Documentation may describe only what this repository actually contains,
  the protocol design labelled as design, and the rules themselves.

## Synthetic fixture rule

- All example and fixture data must be invented, must carry
  "_synthetic": true where the format allows it, and must state in the file
  itself that the data is invented for code tests only.
- Use obviously fake identifiers: synthetic codes, fake target labels, and
  sources on example.org, or a null identifier with verification status
  "unverified".
- Never copy a real identifier, name, sequence, value, or quotation into a
  fixture to make it look realistic.

## Pull request checklist

- [ ] Tests added or updated, and the full suite passes:
      python3 -m pytest tests/
      (pytest, not unittest discovery: unittest silently skips the
      pytest-style test files and reports a smaller, misleading green)
- [ ] Citation audit run on any fixture or example changed:
      python3 -m madd audit-claims <file>
- [ ] No load-bearing claim without a primary-source identifier.
- [ ] No tier-0 (model opinion) source used as load-bearing evidence.
- [ ] No new dependency added to the core package. The core is Python
      standard library only.
- [ ] Any new tool entry added to the license registry with its license
      and allowed uses stated, and blocked by default until verified.
- [ ] Outputs labelled by the highest validation gate actually passed.
- [ ] No network call, provider SDK, or API key added without a separate
      design discussion recorded in docs/.

## Style

- Python 3.11 or newer, standard library only in madd/.
- Prefer small pure functions that return structured results over code
  that raises on the first problem. Auditors must report all errors found.
- Keep identifiers and error codes stable; tests depend on them.
