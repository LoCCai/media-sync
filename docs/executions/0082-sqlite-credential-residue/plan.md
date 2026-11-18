**English** | [中文](plan.zh.md)

# Plan: SQLite scratch-credential residue hardening

Status: **frozen**. This plan authorizes no deployment, platform request or
resident-process restart.

## 1. Reproduce before changing anything

- Reproduce the failing assertion in isolation: `0003` rewrites a legacy signed
  URL, the sentinel must then be absent from the file bytes.
- Confirm the mechanism rather than the symptom: rerun the same upgrade with a
  `secure_delete=ON` connection listener. If the sentinel disappears, the cause
  is freed-page retention, not a scrub logic bug.
- Record both outcomes, including the temporary-path dependence, so the
  execution log states what was actually observed.

## 2. Change the connection policy, not the migration

- Add `PRAGMA secure_delete=ON` to the SQLite connection configuration in
  `src/media_sync/infrastructure/db/database.py`, next to the existing
  `foreign_keys`, `journal_mode` and `busy_timeout` pragmas, with a comment that
  names the credential-retention reason.
- Keep the pragma value a literal, mirroring the existing
  `busy_timeout` discipline; expose it as a named constant so tests assert the
  same text.
- Do not touch `0003`, any other migration, the schema revision, or the
  downgrade guards. Migrations must remain valid against databases created by
  earlier releases.

## 3. Test the policy and the outcome

1. Assert `PRAGMA secure_delete` equals `1` on the shared engine in
   `tests/integration/test_database.py`, beside the existing pragma assertions.
2. Keep the `0003` end-to-end assertion as the outcome test; verify it now passes
   both on the short default temporary path and on the long temporary path that
   previously reproduced the leak.
3. Confirm the pragma does not disturb WAL, nested savepoints or the
   `BEGIN IMMEDIATE` writer coordination: run the database, scheduler and
   pipeline integration slices.

## 4. Gates

- Ruff lint and format (whole repository), strict mypy, `compileall`.
- Full Python suite from the repository root.
- Web `check`, `test`, `format:check` (source unaffected, still required).
- `scripts/check_docs.py`, `scripts/check_upstreams.py`, `git diff --check`.
- Record the precise commands, counts and the two reproduced outcomes in
  bilingual form.

## 5. Out of scope

- Vacuuming on upgrade, retroactive scrubbing of existing production files, or
  any claim that historical deployments already erased their freed pages. An
  operator who wants to erase existing residue must run `VACUUM` on the live
  database after this execution; that is documented, not automated here.
