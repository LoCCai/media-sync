**English** | [中文](progress.zh.md)

# Execution 0055 Phase A progress

- Status: Backend authentication boundary implemented; Web login and playback evidence pending
- Date: 2026-09-05
- Planning baseline: `d0a8cc2`; implementation baseline: `4564b2a`
- Planned revision: `0008_playback_evidence`

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

## Playback-evidence boundary clarified before implementation

1. Natural replay will compare immutable identity fields only: schema version, author/job identity, the four context digests, and observation fingerprint. Request-time `observed_at`/`confirmed_at` values are not required to equal the winning row; replay always returns the first persisted row and timestamps.
2. “Append-only” in this phase means enforced by the application, API, and repository. It does not claim database-role or trigger-level immutability.
3. An item fingerprint proves one canonical remote item identity under the resolved profile/publication/selector context. It does not prove media-byte integrity, uninterrupted playback, or that the remote item remains current later.
4. Qualification schema v3 must freeze the author aggregation scope, row/deadline bounds, source of current authority, and lookup failure/truncation semantics before implementation. PostgreSQL evidence will cover the Author/Job/PlaybackEvidence metadata and repository races only, not claim a complete PostgreSQL application deployment.

## Still pending

- The packaged Svelte console and `/legacy` do not yet provide the login shell, in-memory CSRF store, centralized 401 reset, or logout/expiry lifecycle. The backend boundary is therefore implemented, but the current Web control surface is not yet operational for authenticated writes.
- Observation fingerprinting, revision `0008_playback_evidence`, the evidence repository/service/API, qualification schema v3, and the Web playback-confirmation interaction do not exist yet.
- No authorized live operator credential, platform account, or real Emby/Jellyfin playback flow has run. Playback evidence remains `NOT_IMPLEMENTED`; live playback remains `NOT_RUN`.

## Next checkpoint

Commit and publish the backend authentication boundary with its bilingual evidence. Then implement the domain-separated observation fingerprint, revision `0008_playback_evidence`, and repository replay/concurrency boundary before the confirmation API, qualification v3, and Web surfaces. A Linux/Docker host must still execute the recorded Compose startup and real-PostgreSQL gates.

The pre-existing `.mimosa/` directory remains untracked and excluded.
