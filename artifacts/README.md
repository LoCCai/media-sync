# Local test-run artifacts

This directory holds workstation-local test artifacts (junit XML and similar).
It is git-ignored: raw junit files embed local filesystem paths and must not be
committed verbatim.

## Convention (execution 0049)

Before the phase-B Linux rerun, each station captures:

```bash
uv run pytest -q --junitxml=artifacts/pytest-<host>-<execution>.xml
```

Then records only the **sanitized summary** (tests/failures/errors/skipped plus,
when failures exist, the exact node IDs with local paths stripped) in the
corresponding execution `verification.md`. The per-test Linux-vs-Windows diff
compares those recorded summaries and node IDs, never the raw XML.

Authoring-station captures so far:

- `pytest-windows-0049.xml` — green run: `tests=2067 failures=0 errors=0 skipped=1`
  (0048's runs on the same station recorded 33/35 failures — see execution 0049
  verification for the nondeterminism analysis).
