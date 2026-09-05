**English** | [中文](security-review.zh.md)

# Security and privacy review (execution 0046)

Scope: the claim-by-claim self-review introduced at the 0046 boundary, calibrated through execution 0054 phase B, the execution 0055 backend-authentication commit `f19bfaa`, the playback-evidence persistence commit `1d5b448`, and the current browser-only confirmation checkpoint. This is a self-review, not an external audit. The backend boundary, matched-only observation identity, append-only persistence and TOCTOU-safe confirmation service/API are implemented and offline-verified; safe current/stale projection, qualification schema v3 and the Web login/CSRF/confirmation client are not.

## 1. Credentials and secrets

| Claim | Enforcement |
| --- | --- |
| Raw cookies/passwords are never persisted in the database, config, logs, argv or Git | Requirements AUTH-004; accounts store opaque `credential_ref` values only; QR/OTP material stays inside the login child process |
| The administration credential is resolved before `serve` binds and is never persisted | A required typed operator reference resolves through `env:` / confined `file:` / `keyring:`; the value is reduced to a process-memory digest. The optional automation Bearer uses a distinct reference and value. Fixed startup/login/audit codes disclose neither |
| Browser authority is process-local and non-exportable | One rotating opaque HttpOnly, `SameSite=Strict` session cookie and one memory-only CSRF value expire on timeout, logout, restart, or credential replacement; neither belongs to a backup or support bundle |
| Crawler/account secrets resolve only at their process boundary; the media-server API key resolves only at the final connector boundary | `security/secrets.py` provides `env:` / `keyring:` / confined relative `file:` schemes; execution 0054 keeps the complete media-server reference and value out of API responses, Operation payloads and SQLite |
| A playback-observation identity discloses no raw server selector | Only a complete unique `matched` lookup derives it, by hashing the bounded remote item ID inside profile/publication/selector context and then binding that digest to the canonical author. `not_found` carries neither item nor observation fingerprint; raw item IDs and paths never enter the ledger |
| Playback-evidence persistence preserves the first persisted row | Revision `0008` constrains canonical UUIDs, lowercase SHA-256 digests, timestamp order, unique observation identity and `RESTRICT` author/publication-Job parents. The repository has create-or-exact-replay only; a conflicting identity fails closed, a non-empty table prevents downgrade, and the service emits its fixed success audit only after the application-owned transaction commits. Default `serve` logging gives the `media_sync` namespace its own configured stderr handler, so fixed INFO audits remain visible without mutating or removing Uvicorn's default entries |
| Signed CDN URLs are runtime-only | Detail-protocol children carry them in bounded frames/memory; recursive strip before persistence (executions 0009, 0013+); retained-tree scans assert zero-match |
| Creator authority references are secret-typed | `SecretValue` provenance for `creator_input.secret_ref`; ambiguous query/fragment URLs fail closed |
| Media-server configuration cannot be supplied by an API request | One immutable environment-owned profile is validated at startup; the API returns only a hand-built summary without the API key, complete reference, Library ID, server path or network ranges |

## 2. Process boundary

| Claim | Enforcement |
| --- | --- |
| Upstream crawler never imported into the service | ADR-0001: external pinned checkout as a child process; module-identity checks (`_module_belongs_to_checkout`) reject foreign modules |
| Cookie enters only a private env channel | Bridge injects via environment read by a small runner, removed before import; the public argv carries only entry point + confined spec path |
| Login/crawl children are reaped deterministically | Parent START/CANCEL/EOF framing, post-result guardian, Windows job objects / POSIX process groups (execution 0012) |

## 3. Network and filesystem policy

| Claim | Enforcement |
| --- | --- |
| Downloads reach only public, verified addresses | Every hop resolves to public DNS answers; pinned connections; manual redirects that drop Range validators across origins |
| Media-server calls reach only the configured origin and explicit network policy | Every lookup page and POST revalidates all DNS answers against operator-allowlisted IP/CIDR, pins the connection while preserving Host/TLS SNI, disables environment proxies, rejects redirects and server-provided next links, and prevents requests from overriding the target |
| Download paths cannot escape configured roots | Path-confinement guards; symlink/lstat checks on every directory; archive blobs are immutable no-clobber links |
| Upstream binary downloads stay disabled | Bridge config forces `ENABLE_GET_MEIDAS/GET_MEDIAS = False` |

## 4. Service exposure

| Claim | Enforcement |
| --- | --- |
| `serve` fails before bind without valid operator authority | Missing, malformed, weak, unresolved or conflicting credential inputs collapse to fixed configuration errors before Uvicorn starts; no production anonymous-mode switch exists |
| Deny-by-default route boundary | Exact raw Host validation runs first. Only health/readiness, login/session bootstrap, the public root and existing immutable bootstrap assets are anonymous; business APIs, QR/archive bytes, SSE, deep readiness, support bundle, OpenAPI/docs, `/legacy` and authenticated SPA deep links require a valid session or the optional Bearer where permitted |
| Browser mutations require same-origin proof | Login requires an exact configured Origin. Every unsafe cookie-authenticated request additionally requires that Origin plus the session-bound CSRF header. CORS is disabled; forwarded Host/proto headers confer no authority |
| Playback confirmation is browser-only and revalidates current authority | The outer middleware rejects Bearer-only and any mixed Cookie/Authorization request for the endpoint before body or handler work. The handler then requires the browser auth marker, exact Origin and CSRF, rejects `Idempotency-Key`, and accepts only a duplicate-free JSON object of at most 1 KiB containing canonical author UUID plus lowercase observation fingerprint. The service uses one bounded deadline and authority lock for resolve A → one complete unique lookup → resolve B, compares both targets and the recomputed identity, releases the authority lock, and only then opens the short create-or-replay transaction. Every drift, mismatch or incomplete/ambiguous lookup writes nothing |
| Container loopback topology is explicit | The image binds `0.0.0.0` internally, while example Compose publishes `127.0.0.1:8632`, mounts the required credential from outside the repository, and allowlists exactly `http://127.0.0.1:8632`. Non-loopback browser origins require HTTPS |
| Web integration is not overstated | Console v2 and `/legacy` do not yet bootstrap the session or propagate CSRF. They are not currently operable administration clients even though the backend boundary is active |
| Structured logs and durable operation/evidence surfaces are redacted | Classified secret names are masked at sinks; raw adapter exceptions never surface to CLI/API output. Selector-bearing dependency wire messages are replaced with fixed text. Raw or percent-encoded media-server paths/provider values, remote item IDs, Etags and remote error bodies cannot enter logs, SQLite, Events, SSE, API results or support bundles; revision `0008` stores only context-bound digests and canonical local identities. Confirmation returns only schema version, evidence/author IDs, server timestamps and replay state—never the submitted fingerprint, publication Job or four internal digests |

## 5. Privacy

- The archive intentionally links content to authors the user subscribed to; collection is bounded by per-subscription `max_items`, request delays, and closed request profiles; comments and keyword crawling are explicit non-goals.
- Browser profiles are per-platform-per-account under a 0o700 runtime root; QR images relayed for the web console live in the same root and are deleted with the login attempt (execution 0040).

## 6. Residual risks (honest list)

1. The Web clients are temporarily behind the backend contract: they cannot log in, retain CSRF in memory, or recover uniformly from session expiry. Web has synchronized only the matched lookup response type; it has no confirmation UI. This fails closed as 401/403 rather than reopening anonymous access, but blocks Web administration and live QR qualification until the remaining 0055 frontend work is verified.
2. This is single-operator authentication, not multi-user authorization. The optional Bearer is broad automation authority, and non-loopback deployment still requires reviewed HTTPS termination and exact Host preservation. Public-network deployment, RBAC, SSO/MFA and trusted reverse-proxy identity remain unsupported.
3. The browser-only confirmation service/API now provides authenticated write authority, but there is no bounded by-author current/stale projection, qualification schema v3 or Web confirmation UI. The schema-v2 qualification response therefore continues to report overall `playback_evidence` as `NOT_IMPLEMENTED` with null human status, and live playback remains `NOT_RUN`. Local/mock confirmations are not remote playback telemetry and cannot create a checked-in human PASS.
4. SQLite is the single supported production store; disk access equals full data access, including credential *references* (which still require the secret provider) and any future playback-association digests. PostgreSQL repository semantics have an isolated optional race harness, but its new cases have not run on this workstation and do not establish complete-schema or production PostgreSQL support.
5. Upstream platform behavior changes can alter what the pinned crawler does; the license gate is an acknowledgement, not a technical control on upstream behavior.
6. No external audit has been performed (`NOT_RUN`, operator option).
