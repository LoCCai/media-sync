**English** | [中文](goal.zh.md)

# Execution 0055 Phase A goal

- Status: Frozen planning baseline; implementation has not started
- Date: 2026-09-05
- Baseline: `d0a8cc2`
- Planned database revision: `0008_playback_evidence`

## Objective

Add a fail-closed single-operator authentication boundary to `media-sync serve`, then add an append-only, authenticated human playback-attestation ledger. This closes the highest residual control-plane risk and makes `playback_evidence` implementable without confusing accepted refresh, observed item presence, provider task completion, or actual playback.

This is the smallest safe Execution 0055 slice. It does not add writable media-server configuration, multiple profiles, retention, deletion, repair, forced overwrite, or automatic export-to-scan behavior.

## Baseline and threat model

At `d0a8cc2`, the FastAPI application has 51 routes and no authentication middleware. Business APIs, QR images, archive bytes, operation SSE, support bundles, deep readiness, generated OpenAPI/docs, `/legacy`, and the SPA fallback are reachable by any client that can reach the port. Loopback-only defaults and `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED` reduce exposure but are not access control.

Phase A assumes one trusted operator, one foreground API process, no distributed HA, and no trusted forwarding-header support. The attacker may reach the listening socket, forge Host/Origin/headers/cookies/request bodies, replay captured non-secret API responses, race duplicate requests, and supply arbitrary UUIDs or digests. The attacker does not already control the process account, configured secret provider, database file, export tree, or TLS termination. XSS, compromised operator browsers, multi-user authorization, SSO/MFA, reverse-proxy identity, and hostile same-permission local processes remain outside this slice.

## Acceptance criteria

1. `media-sync serve` resolves a typed operator credential reference before binding. Missing, malformed, empty, oversized, control-bearing, or unresolvable credentials fail startup with a fixed code and without echoing the reference or value. There is no production anonymous-mode switch.
2. A separate typed bearer-token reference is optional for non-browser automation. When configured, it must resolve before binding, meet the same bounded-secret rules, and differ from the browser credential. Tokens are accepted only in the `Authorization: Bearer` header, never in URL, query, form, cookie, WebSocket, EventSource, or log context.
3. Non-loopback deployments require an explicit bounded allowlist of canonical operator origins. Loopback may derive its exact HTTP origin from the configured host and port. Every request validates the raw Host against that allowlist; forwarded host/proto headers grant no authority. Non-loopback browser origins require HTTPS.
4. The anonymous route allowlist is exact: `GET`/`HEAD /api/v1/health`, `GET`/`HEAD /api/v1/ready`, `POST /api/v1/operator-auth/login`, `GET /api/v1/operator-auth/session`, `GET`/`HEAD /`, `/favicon.svg`, `/_app/version.json`, and existing regular files below `/_app/immutable/`. Nothing else is public by prefix or fallback.
5. All other routes are authenticated before handler, database, filesystem, reconciliation, or streaming work begins. This includes OpenAPI/docs/redoc/oauth redirect, deep readiness, support bundle, settings, QR PNG, archive GET/HEAD/Range, operation SSE, all business reads and writes, `/legacy`, and authenticated SPA deep links. Unknown future routes inherit denial by default.
6. Browser login accepts one strict JSON credential field, requires an allowed Host and exact Origin, applies a bounded process-global failure limiter, and compares the resolved secret in constant time. Responses and structured audit logs use fixed codes and never retain the submitted credential, cookie, CSRF value, Origin, Host, IP, or User-Agent.
7. Successful login rotates the sole process-local browser session and invalidates the prior one. The cookie is opaque, random, `HttpOnly`, `SameSite=Strict`, Path `/`, has no Domain, has an eight-hour-or-shorter bounded TTL, and is `Secure` for HTTPS deployments. Restart, logout, expiry, or credential rotation invalidates it.
8. An authenticated session bootstrap returns a bounded CSRF value for same-origin memory only. Every cookie-authenticated unsafe request requires the exact allowed Origin plus the CSRF header. Missing, malformed, stale, forged, cross-origin, or logged-out session material fails closed. Bearer requests are non-ambient and do not use CSRF, but still require the Host gate.
9. Authentication failures return fixed 401/403/429 responses with `Cache-Control: no-store`; HEAD responses have no body. Security headers cover middleware rejections. CORS remains disabled, and no secret is placed in HTML, generated JavaScript, local/session storage, service-worker state, URL, or response diagnostics.
10. A matched author item lookup emits a domain-separated opaque `observation_fingerprint` bound to the author, current profile, complete publication, selector, and exact item fingerprints. Not-found, incomplete, ambiguous, or failed lookup emits no attestation authority.
11. `POST /api/v1/media-server/playback-evidence` accepts only a canonical author UUID and that opaque fingerprint, and only from an authenticated browser session with valid CSRF. Bearer authentication is rejected for this human-attestation mutation. The request accepts no provider, profile, Library, path, item ID, Etag, publication ID, timestamp, or free text.
12. Before insertion, the server performs complete target resolve/manifest inspection, one bounded unique item lookup, and a second complete target resolve. Both targets and the recomputed observation fingerprint must match. Any publication/profile/selector/item drift, forged digest, incomplete work, or remote ambiguity writes nothing.
13. Revision `0008_playback_evidence` adds one append-only table with safe UUIDs, four context digests, the observation fingerprint, server-observed and operator-confirmed timestamps, and RESTRICT foreign keys to Author and publication Job. It stores no raw JSON, state/update column, remote item ID, path, provider value, Etag, credential, session, CSRF, IP, Host, Origin, or User-Agent.
14. The observation fingerprint is the natural unique identity. Serial or concurrent duplicates return the original row and timestamp as a replay; SQLite and PostgreSQL produce at most one row. A conflicting row under the same fingerprint fails closed. The endpoint does not accept the generic `Idempotency-Key` contract.
15. Evidence is never updated or deleted in this phase. A changed current identity leaves historical evidence intact but stale. Qualification schema v3 marks `playback_evidence` as `IMPLEMENTED`; it grants human `PASS` only for evidence matching the current profile/publication/selector/item authority, otherwise remains `NOT_RUN` and reports bounded stale evidence separately.
16. `provider_task_completion` remains `NOT_IMPLEMENTED / provider_api_unsupported`; `automatic_post_export_scan` remains `NOT_IMPLEMENTED`. Accepted refresh, observed item presence, bearer automation, local/mock tests, and an old stale attestation never imply provider completion or playback PASS.
17. The Web console gains a login shell, unified 401/session-expiry handling, in-memory CSRF propagation, safe SSE/media/QR cookie compatibility, and an explicit confirmation dialog enabled only from a current matched lookup. Its wording states that the operator is attesting to actual playback; the application is not remotely measuring playback.
18. Tests enumerate every application route and prove the anonymous allowlist rather than sampling endpoints. They cover auth/session/CSRF/Host/Origin/rate-limit/redaction, archive HEAD/Range, SSE pre-handler rejection, QR, docs, legacy, migration, repository races, TOCTOU, qualification truth, Web behavior, packaging, and rollback.

## Rollback and evidence truth

Browser sessions are deliberately process-local and disappear on restart; they are not backup data. Playback evidence is durable audit data. Online downgrade from revision 0008 succeeds only when the evidence table is empty; any row blocks downgrade with a fixed code. Offline downgrade is rejected. An old binary must not serve a revision-0008 database and must never be used to regain anonymous access; rollback requires a compatible authentication layer or network isolation and must preserve all evidence rows.

Local and mocked verification can establish implementation behavior only. Until an authorized operator uses a real Emby/Jellyfin server, actually plays an item, and submits the explicit confirmation, the repository's live playback status remains `NOT_RUN`.

## Explicit exclusions

- Browser-writable media-server settings or secrets, multiple profiles, credential rotation UI, and reverse-proxy trust.
- Subscription/account deletion, retention, cascade cleanup, orphan repair, forced overwrite, and any evidence DELETE/PATCH/PUT.
- Automatic export-to-scan, provider-specific background-task completion, playback telemetry, transcoding, and player embedding.
- Multiple users, roles/RBAC, SSO, OAuth/OIDC, MFA, password reset, recovery codes, and durable browser sessions.
- Real seven-platform, CDN, Linux deployment, or Emby/Jellyfin qualification execution; those remain under Execution 0047.
