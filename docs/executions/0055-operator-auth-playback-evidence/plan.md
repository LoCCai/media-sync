**English** | [中文](plan.zh.md)

# Execution 0055 Phase A plan

- Status: Frozen before implementation
- Date: 2026-09-05
- Baseline: `d0a8cc2`
- Planned revision: `0008_playback_evidence`

## Delivery sequence

1. Commit this bilingual eight-file planning baseline separately from implementation. Keep the pre-existing untracked `.mimosa/` directory excluded.
2. Add bounded operator-auth settings and reuse typed `SecretReference`, `SecretValue`, and the local resolver. Resolve required browser credentials and optional distinct bearer credentials before API bind, without putting values or complete references in settings projections, exceptions, repr, logs, or support bundles.
3. Implement a small process-local auth runtime: constant-time credential checks, one rotating opaque browser session, bounded TTL, memory-only CSRF, fixed-code audit logging, a deterministic global login-failure limiter, and exact logout/expiry/restart behavior. Inject clocks/randomness only through private test seams; provide no production bypass.
4. Install one outer ASGI authentication/Host/Origin middleware in `create_api_app`. It owns the exact public-route table and rejects everything else before endpoint work. Preserve HEAD semantics, security/no-store headers, and body/stream non-entry on rejection.
5. Add strict `/api/v1/operator-auth/login`, `/session`, and `/logout` contracts. Update `media-sync serve` diagnostics and deployment startup so absent/unresolved auth configuration fails before listening. Keep CORS disabled and forwarded headers untrusted.
6. Move all seven existing API test modules onto a shared authenticated-client helper that performs the real login and CSRF flow. Do not use an environment-name bypass or skip middleware in tests. Add a route-enumeration test covering all 51 baseline routes plus each newly introduced route.
7. Add the domain-separated observation fingerprint to matched author lookup results. It binds only existing safe digests and the canonical author UUID; raw provider/path/item data remains process-local and not representable in the public fingerprint helper.
8. Add the `PlaybackEvidence` model, revision `0008_playback_evidence`, and a dedicated repository. The table is append-only and contains `id`, `schema_version`, `author_id`, `publication_job_id`, `profile_fingerprint`, `publication_fingerprint`, `selector_fingerprint`, `item_fingerprint`, unique `observation_fingerprint`, `observed_at`, and `confirmed_at`; it has no mutable timestamp, state, raw payload, or requester fields.
9. Implement insertion as a natural-identity replay. SQLite reserves the writer before the initial read; insertion uses a nested savepoint. PostgreSQL lets the unique constraint serialize contenders. After `IntegrityError`, expire state and re-read the fingerprint; return replay only when every persisted field matches exactly.
10. Implement `PlaybackEvidenceService.confirm(author_id, observation_fingerprint)`: resolve target A, execute one complete unique lookup, resolve target B, compare A/B and the recomputed fingerprint, then open only the short insertion transaction. Network and filesystem work never holds the database writer/row lock.
11. Add authenticated browser-session-only POST confirmation and an authenticated safe by-author evidence projection. Reject `Authorization: Bearer` for confirmation even when valid. Do not accept `Idempotency-Key`, selectors, remote IDs, paths, profile values, timestamps, or explanatory text.
12. Upgrade qualifications to schema v3. Project bounded current/stale evidence without exposing selectors. `playback_evidence` becomes `IMPLEMENTED`, remains `NOT_RUN` with no current live row, and becomes `PASS` only for current exact authority. Keep provider task completion and automatic chaining unchanged.
13. Add the Web login shell and session store, memory-only CSRF header injection, centralized 401 reset, and logout. Verify EventSource, direct archive/media elements, QR retrieval, docs, legacy, and deep SPA navigation continue to work through the HttpOnly cookie without URL tokens.
14. Add the Library confirmation interaction after a matched lookup. Require an explicit modal acknowledgment, submit only author UUID plus observation fingerprint, display current versus stale safe evidence, and avoid progress percentages or claims of remote telemetry.
15. Update architecture, deployment, operations/backup/upgrade, security review, status, roadmap, platform capabilities, README/index, 0047 live checklist, and this execution's progress/verification. Preserve the distinction among automated evidence, implementation status, and authorized human qualification.
16. Run focused auth/evidence/migration/API/Web gates, SQLite and real PostgreSQL race matrices, complete Python and serial Web suites, Ruff/format/mypy/compileall, wheel/sdist and container/static packaging checks, docs/upstreams, tracked-output/host-path/private-key/assigned-secret scans, frozen goal/plan diff, whitespace, and Git publication reconciliation.

## Authentication contract

`Settings` gains only bounded immutable inputs: required `operator_credential_secret_ref` for `serve`, optional `operator_api_token_secret_ref`, bounded `operator_allowed_origins`, and bounded `operator_session_ttl_seconds` defaulting to eight hours. A loopback bind may derive one exact local HTTP origin; a non-loopback bind requires explicit HTTPS origins. Schemes, hosts, ports, Unicode/IDNA form, userinfo, paths, queries, fragments, duplicates, wildcard hosts, nulls, and list bounds are validated before the app starts.

The auth runtime retains only resolved `SecretValue` objects and random session/CSRF material in process memory. It accepts one browser session at a time; a new login rotates the session. Session cookie and CSRF comparison are constant-time. Failed login work has a deterministic minimum duration and a process-global bounded limiter that does not retain client identifiers. Fixed log codes are `operator_login_succeeded`, `operator_login_failed`, `operator_login_rate_limited`, `operator_logout_succeeded`, `operator_session_expired`, `playback_evidence_created`, and `playback_evidence_replayed`; context contains no request-derived text.

The middleware's public table matches method plus exact path or an already-resolved regular static file under `/_app/immutable/`. It never allowlists all `/api`, all non-API paths, the SPA fallback, or an arbitrary filesystem prefix. Authentication precedence is: valid browser cookie, otherwise valid Bearer for routes that permit automation, otherwise 401. Unsafe cookie requests then require exact Origin and CSRF; login requires exact Origin without a prior session. All requests pass the Host gate first.

## Playback evidence identity

The observation fingerprint uses a canonical length-prefixed payload and a dedicated `media-sync:media-server-playback-observation:v1` domain. It binds canonical author UUID, profile fingerprint, publication fingerprint, selector fingerprint, and item fingerprint. It excludes `observed_at`, so repeated complete lookup of the unchanged identity produces one natural evidence row; the stored `observed_at` is the server timestamp from the confirmation-time lookup.

The public lookup response includes the fingerprint only for `matched`. Confirmation redoes all authoritative work and compares with `hmac.compare_digest`; the response cannot be used as a bearer capability without an authenticated browser session and CSRF. The table's four digests deliberately duplicate safe identity components for bounded current/stale queries and exact conflict checking, not raw selectors.

## Migration and rollback

Revision 0008 creates one table, a unique constraint on `observation_fingerprint`, an `(author_id, confirmed_at, id)` index, UUID/digest/schema/timestamp checks, and RESTRICT foreign keys to `authors.id` and `jobs.id`. It alters no existing row or vocabulary. Metadata/create-all and Alembic schemas must remain equivalent.

Downgrade is online-only. It first audits for evidence; a non-empty table raises `playback_evidence_rows_prevent_downgrade` without changing the revision, table, or rows. An empty table may drop the index/table and return to 0007. Future author/Job deletion must explicitly account for the RESTRICT evidence; cascade deletion is forbidden.

Because the old API has no auth, application rollback is also a security boundary: stop traffic, retain the revision-0008 database, deploy an auth-compatible binary or enforce a separately reviewed external authentication layer, then resume. Never delete evidence or force the Alembic revision to make an old binary start.

## Verification matrix

- Configuration: missing/invalid/unresolved/weak/duplicate secret refs, loopback derivation, non-loopback HTTPS origins, hostile Host and forwarded headers, bounded TTL/list/text inputs, repr/error/support-bundle redaction.
- Auth: correct/incorrect credentials, constant-time comparison seam, rotation, logout, expiry, restart, 401/403/429 fixed shapes, GET/HEAD, cookie flags, bearer grammar, credential/bearer separation, rate-limit recovery, and zero secret retention.
- Route inventory: every `app.routes` entry unauthenticated; exact public methods pass, every other method/path rejects before dependencies/DB/files/stream. Include automatic OpenAPI/docs/redoc, SPA fallback, `/legacy`, QR, archive GET/HEAD/Range, support bundle, deep readiness, and SSE.
- CSRF/origin: missing/null/duplicate/wrong/stale headers, absent/wrong Origin, cross-origin form/JSON, allowed exact origin, Bearer behavior, and no query token.
- Evidence identity: matched-only fingerprint, domain separation, canonicalization, every context component drift, no raw selector leakage, repr/redaction, and unchanged repeated lookup stability.
- Service TOCTOU: not-found/ambiguous/incomplete; target A/B publication/profile/selector/item drift; forged fingerprint; database failure; duplicate confirmation returns original `confirmed_at`; no network/file work under DB locks.
- SQLite persistence: fresh and populated 0007→0008, schema parity, all constraints/FKs, serial and two-thread replay, outer rollback, RESTRICT deletion, empty/non-empty downgrade, foreign-key check, and packaged-wheel upgrade.
- PostgreSQL persistence: same-identity unique-lock wait then replay, winner rollback then create, conflicting fields, different identities, insert versus parent delete in both orders, timeout/retry, no orphan, and one row.
- Qualification: schema v3 no-evidence `IMPLEMENTED/NOT_RUN`, current exact PASS, stale retained but not PASS, provider completion unchanged, automatic scan unchanged, and no mock-to-live promotion in checked-in status.
- Web: login/session/logout, CSRF injection, session-expiry reset, no localStorage/token URL, EventSource reconnect, QR/blob, archive media/new-tab, docs/legacy, deep links, matched-only confirmation, modal focus/keyboard behavior, and truthful labels.

## Commit boundaries

1. Planning baseline.
2. Operator auth configuration/runtime/middleware and backend tests.
3. Playback fingerprint, revision 0008, repository, and cross-database persistence tests.
4. Confirmation service/API and qualification v3.
5. Web login and playback-attestation surfaces.
6. Review fixes, complete verification, documentation closeout, and push reconciliation.

Each commit uses a bilingual subject, contains only its reviewed boundary, and excludes `.mimosa/` and all runtime/generated output.
