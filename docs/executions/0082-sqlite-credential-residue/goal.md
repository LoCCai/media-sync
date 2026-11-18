**English** | [中文](goal.zh.md)

# Goal: SQLite scratch-credential residue hardening

## Outcome

Make the SQLite connection policy itself guarantee that a credential-bearing value
removed by a migration or a scrubbing `UPDATE` does not survive in freed pages of
the database file.

## Why this execution exists

The 0081 gate run on a Windows workstation failed one long-standing durability
test: after `0003_media_download_emby` rewrote a legacy signed media URL to a
refresh-only locator, the credential sentinel written by
`tests/integration/test_packaged_migrations.py` was still readable in the
database file. The test had passed on the Linux deployment host and on shorter
paths, which is exactly the pattern that hides a real gap: SQLite only
overwrites a freed cell when the connection has `secure_delete` enabled, and
the flag is per connection, not per file.

A schema rebuild (`batch_alter_table`) copies rows into a new table and drops the
old one. When the drop happens on a connection without `secure_delete`, the old
page is merely linked into the freelist, so the previous `source_url` — a signed
platform media URL that the product explicitly promises never to keep — stays in
the file bytes. The same applies to any future scrub-in-place migration.

## Acceptance

- Every connection created by `media_sync.infrastructure.db` has
  `PRAGMA secure_delete=ON`, asserted by a test on the shared engine.
- The `0003` upgrade test proves the credential sentinel is absent from the
  database file bytes, including on the long temporary paths that previously
  reproduced the leak.
- No on-disk format, schema revision, transaction policy or `WAL` behaviour
  changes; downgrade paths are untouched.
- The documented promise "signed media URLs never persist" stays true at the
  storage level rather than only in row values.
