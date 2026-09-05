**English** | [中文](progress.zh.md)

# Projection progress

- Date: 2026-09-05
- Status: Implemented and locally verified; integration checkpoint

Confirmed a clean `main` at `13de3b7`, fetched and pulled `origin/main` with no new changes. Read the parent frozen goal, plan, completed checkpoints, repository, service, qualification and API contracts. The previous goal turn made verified progress by publishing the confirmation backend.

The bilingual planning baseline was committed as `9fd74de` before implementation. Parent and child frozen goal/plan files remain unchanged.

## Implemented

- Added authenticated author evidence GET with canonical UUID/query validation, default history limit 20 and maximum 50. It returns local IDs, timestamps and safe states only.
- Fresh authority checks finish under one bounded external-work deadline before a short database read transaction. Failed, incomplete, ambiguous or changed remote authority yields unknown history and cannot grant PASS; complete absence yields stale history.
- Exact current evidence is selected independently of history. At most `limit + 2` ledger rows are materialized, with no COUNT or write. A 62-row SQLite fixture proves the oldest current row remains visible beyond the newest history page. History-page truncation does not invalidate independently verified current evidence; remote lookup truncation does.
- Qualification schema v3 evaluates only an explicitly selected author. No author means `not_requested` with no evidence or remote query. Scoped PASS reflects an exact durable human attestation, not playback telemetry or platform-wide qualification.
- Updated Web response types, the 59-route authentication inventory, tests and bilingual current documentation. No migration or frontend interaction was added.

## Verification and handoff

The focused union passes 220 tests. Full Python regression: `2999 passed, 22 skipped, 1 warning in 613.66s (0:10:13)`. Web passes 69 tests and format/check/build. Exact commands, unavailable gates and final package/publication results belong in [verification](verification.md).

The user requested closeout and GitHub publication before further development, then supplied a review based on `13de3b7`. Its frontend-session gap and entrypoint migration order were confirmed by static inspection; the root-owned secret risk is conditional, not an observed host failure. The [delivery-priority addendum](../delivery-priorities.md) records the revised sequence: safe usable console and credential preflight, current Linux image baseline, then Bilibili/XHS live canaries. Finish this existing evidence increment; do not expand it or wait for more evidence UI before authorized CLI canaries.

## Still pending

Web login/session/CSRF/logout/expiry and confirmation UI, runtime-user credential-read/upgrade preflight implementation, current Linux Docker/browser integration, restart/backup-restore, real PostgreSQL races, and authorized live platform/media-server checks remain incomplete or NOT_RUN. The original seven-platform goal is unchanged; this is an integration checkpoint, not a deployable release claim. The user subsequently requested continuation: publish this checkpoint first, then resume the P0 work in the addendum.
