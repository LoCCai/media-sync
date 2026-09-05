**English** | [中文](progress.zh.md)

# Execution 0055 Phase A progress

- Status: Backend authentication and playback observation identity/persistent-ledger checkpoints published; confirmation service/API remains pending
- Date: 2026-09-05
- Planning baseline: `d0a8cc2`; authentication implementation baseline: `4564b2a`
- Published authentication commit: `f19bfaa`
- Published persistence commit: `1d5b448`
- Current revision: `0008_playback_evidence`

## Completed checkpoints

1. Committed the bilingual planning baseline as `4564b2a`, fetched `origin/main` again before implementation closeout, and preserved the original product goal: seven-platform login/subscription/capture with Emby/Jellyfin-compatible output.
2. Added bounded operator settings for one required typed browser-credential reference, an optional distinct Bearer reference, exact browser origins, and a 60-second-to-eight-hour session TTL. Resolution failures collapse to fixed startup codes without exposing secret values or locators.
3. Added a thread-safe process-local authority with constant-time comparisons, one rotating opaque session, memory-only CSRF, deterministic global bounded failure limiting, fixed audit codes, logout/expiry/restart semantics, and credential rotation that cannot leave an old-credential login valid after rotation completes.
4. Installed a pure outer ASGI boundary that checks exact Host first, admits only the exact anonymous method/path table and existing regular immutable assets, applies browser-first/Bearer-second authentication, requires exact Origin plus CSRF on unsafe cookie requests, rejects Bearer on browser-only routes, and strips every downstream HEAD body frame.
5. Added strict login/session/logout endpoints. Login accepts one bounded UTF-8 JSON object only, rejects duplicate members, non-finite values, excess fields, deep-recursion input, duplicate/invalid headers, and oversized bodies; its OpenAPI schema remains explicit and write-only. HEAD routes now have distinct schema-safe handlers.
6. Made `media-sync serve` resolve and validate the complete boundary before app/database construction or socket binding, with proxy-header trust and access logging disabled. A wildcard container bind may explicitly publish a loopback HTTP browser origin; every non-loopback HTTP origin remains rejected and non-loopback browser access therefore requires HTTPS.
7. Updated the Compose example to mount a dedicated operator credential through a Compose secret and declare the exact host-loopback origin. The image health endpoint stays anonymous. The local environment example now documents the required credential reference, optional independent Bearer reference, origin rule, and TTL.
8. Migrated all seven existing API modules to a real login/session flow. The shared client injects Origin/CSRF only on unsafe methods, so QR, archive GET/HEAD/Range, and SSE coverage exercises ambient same-origin cookies without impossible custom browser headers.
9. Closed review findings for credential-rotation linearizability, container-loopback origin policy, recursive JSON failure, raw-ASGI HEAD bodies/lengths, missing login OpenAPI input, duplicate operation IDs, and false-positive cookie-only test evidence. The focused auth/config/seven-API gate currently passes 190 tests with one pre-existing Starlette/httpx deprecation warning.
10. Completed every locally available backend-slice gate: the full Python suite passes 2811 tests with 14 skips and one existing warning; Web passes 69 tests plus format/check/build; full Ruff/format, strict mypy over 104 source files, compileall, 498-document links, two locked upstreams, and wheel/sdist build/content checks pass. Three Python skips are Windows/POSIX differences; 11 real-PostgreSQL races and Docker/Compose execution were unavailable on this workstation and are not claimed.
11. Committed and pushed the fail-closed single-operator backend boundary as `f19bfaa`. The 2811-test full-Python result above and its accompanying quality/package evidence remain the historical publication gate for that authentication commit; they are not substituted for the separate current-worktree result recorded below.
12. Added a matched-only, domain-separated observation fingerprint. A complete `not_found` result carries neither item nor observation fingerprint; a unique `matched` result binds the canonical author ID to the profile, publication, selector, and item digests without retaining the raw remote item ID. The Web `MediaServerAuthorLookup` discriminated type now mirrors that contract by requiring `observation_fingerprint` for `matched` and forbidding it for `not_found`; this is type-level preparation, not an implemented confirmation interaction.
13. Added the `PlaybackEvidence` model and revision `0008_playback_evidence`. The append-only ledger enforces schema version 1, canonical UUIDs, lowercase SHA-256 digests, ordered aware timestamps, a unique observation identity, an author/time query index, and `RESTRICT` references to Author and publication Job. Downgrade refuses offline SQL generation and refuses to discard any populated evidence table; only an audited empty table may be removed.
14. Added a dedicated create-or-replay repository. Natural replay compares the immutable evidence identity but returns the first persisted row and timestamps; a reused observation fingerprint with different immutable identity fails with a fixed conflict code. SQLite reserves the writer before the natural-key read with `BEGIN IMMEDIATE`, uses a savepoint without owning the caller's commit, and rejects an unsafe pre-existing deferred transaction. PostgreSQL relies on the unique constraint, rolls back only the savepoint after a contender, and re-reads the winner under `READ COMMITTED` semantics.
15. The current commit-3 focused union passes 129 tests with 8 skips and one existing warning. Its migration/repository subset passes 42 tests with 8 skips. The complete Python regression passes 2868 tests with 22 skips and one existing Starlette/httpx warning in 558.19 seconds (`0:09:18`): 3 skips are Windows/POSIX differences, 11 are the existing Operation PostgreSQL cases, and 8 are the new PlaybackEvidence PostgreSQL races. Both PostgreSQL groups were skipped because `MEDIA_SYNC_TEST_POSTGRESQL_URL` is unset, so real PostgreSQL remains explicitly `NOT_RUN`.
16. Current Web format, 7-file/69-test regression, Svelte check with zero errors/warnings, and production build all pass. Full Ruff check passes; Ruff format passes over 727 files after correcting one formatting-only difference; strict mypy passes over 105 source files; and compileall passes. These Web gates validate the current discriminated response type and existing console only—they do not claim that the missing Web login or confirmation interaction is implemented.
17. An isolated system-temporary `uv build` produces exactly one wheel and one sdist. The wheel has 123 entries and the sdist has 837; both contain `playback_evidence_repository.py` and `0008_playback_evidence.py`, and neither contains `.env` or SQLite output.
18. Reviewed, committed, and pushed the observation-identity/persistent-ledger checkpoint as `1d5b448`. The final fetch confirms `HEAD...origin/main` divergence `0 0`; all tracked changes are published, and only the pre-existing untracked `.mimosa/` remains excluded.

## Playback-evidence boundary clarified before implementation

1. Natural replay will compare immutable identity fields only: schema version, author/job identity, the four context digests, and observation fingerprint. Request-time `observed_at`/`confirmed_at` values are not required to equal the winning row; replay always returns the first persisted row and timestamps.
2. “Append-only” in this phase means enforced by the application, API, and repository. It does not claim database-role or trigger-level immutability.
3. An item fingerprint proves one canonical remote item identity under the resolved profile/publication/selector context. It does not prove media-byte integrity, uninterrupted playback, or that the remote item remains current later.
4. Qualification schema v3 must freeze the author aggregation scope, row/deadline bounds, source of current authority, and lookup failure/truncation semantics before implementation. PostgreSQL evidence will cover the Author/Job/PlaybackEvidence metadata and repository races only, not claim a complete PostgreSQL application deployment.

## Still pending

- The packaged Svelte console and `/legacy` do not yet provide the login shell, in-memory CSRF store, centralized 401 reset, or logout/expiry lifecycle. The backend boundary is therefore implemented, but the current Web control surface is not yet operational for authenticated writes.
- The persistence primitive is not yet connected to an authenticated confirmation service or API. The resolve → unique lookup → resolve TOCTOU boundary, qualification schema v3, and the matched-only Web confirmation interaction remain unimplemented.
- No authorized live operator credential, platform account, or real Emby/Jellyfin playback flow has run. The end-to-end playback-evidence capability remains `NOT_IMPLEMENTED`; live playback remains `NOT_RUN`.

## Next checkpoint

Implement the authenticated confirmation service/API with the required double resolution and zero-write failure paths. Qualification schema v3 and the Web login/confirmation lifecycle follow as separate checkpoints. A Linux/Docker/PostgreSQL-capable host must still execute the recorded Compose startup and eight PlaybackEvidence PostgreSQL race gates, together with the previously skipped PostgreSQL coverage.

The pre-existing `.mimosa/` directory remains untracked and excluded.
