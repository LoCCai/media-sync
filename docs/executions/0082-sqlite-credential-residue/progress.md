**English** | [中文](progress.zh.md)

# Progress: SQLite scratch-credential residue hardening

Status: implemented and verified locally. Nothing was deployed and no platform
account was used.

## Result

Every SQLite connection owned by `media_sync.infrastructure.db` now runs
`PRAGMA secure_delete=ON`. Freed cells are overwritten when a row is deleted or
updated, so the `0003` schema rebuild can no longer leave a legacy signed media
URL readable in the database file.

## What was observed

1. The 0081 closeout gate on this workstation ended `2 failed, 7196 passed, 63
   skipped`. One failure was
   `test_0003_upgrade_preserves_only_complete_verified_legacy_asset`: the
   credential sentinel `migration-path-credential-sentinel-0003` was still
   present at byte offset 132972, inside page 32 — the page holding the
   pre-rebuild `assets` rows.
2. The failure was path-length dependent. The same test passed with
   `--basetemp` set to a short directory and failed on the default long
   temporary path, which is why the Linux gate and earlier local runs never
   showed it.
3. A reproduction that copied the pre-upgrade file and ran the same Alembic
   upgrade with a `secure_delete=ON` connect listener left no sentinel in the
   file bytes; the same upgrade without the pragma left it. That isolates the
   cause to freed-page retention rather than to the scrub logic in `0003`.
   `VACUUM` after the upgrade also removes the sentinel, confirming the residue
   lives in freed pages.

## What changed

- `src/media_sync/infrastructure/db/database.py`: added the
  `SQLITE_SECURE_DELETE_PRAGMA` constant and applied it in
  `_configure_sqlite_connection` beside `foreign_keys`, `journal_mode` and
  `busy_timeout`, with a comment naming the credential reason. Exported the
  constant in `__all__`.
- `tests/integration/test_database.py`: the pragma test now also asserts
  `PRAGMA secure_delete` is `1`, so a future connection-policy edit cannot
  silently drop the guarantee.
- `tests/integration/test_kuaishou_creator_work_delivery.py` and
  `tests/integration/test_kuaishou_creator_work_migration.py`: applied the
  formatter to two 0081 test files that had been committed unformatted, so the
  whole-repository format gate is clean.

No migration, schema revision, transaction policy, WAL setting or downgrade
guard changed.

## Not done

- No retroactive scrub of an existing deployment. An operator who wants existing
  freed pages erased must run `VACUUM` on the live database; that is documented
  in the plan as an explicit operator step, not automated here.
- Deployment, Linux host gate and every real-platform row remain `NOT_RUN`.
