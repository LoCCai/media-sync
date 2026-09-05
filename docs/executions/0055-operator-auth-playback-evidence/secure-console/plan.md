**English** | [中文](plan.zh.md)

# Safe console and startup plan

- Date: 2026-09-05
- Baseline: `2e1949f`
- Status: Frozen before implementation

## Implementation sequence

1. Commit this bilingual eight-file baseline before implementation. Preserve all parent and prior child frozen files.
2. Add `serve --check-config`, reusing the real bounded secret/origin validation and host/port overrides. Success emits only fixed safe configuration status; missing/unreadable/invalid secrets, invalid settings/origins fail without app, database, directories or socket work. Do not echo values or references.
3. For container `serve`, preflight before Xvfb and `db init`; explicit check-only/help must not migrate. Keep existing non-serve CLI workflows compatible. Align deployment guidance with effective runtime-user ownership, rootless mappings and backups; no world-readable mode or recursive chown.
4. Add serialized/single-flight auth bootstrap/login/session/logout handling. Login 200 is not enough: it has no CSRF, so require successful session retrieval before granting access. Auth requests can set/delete cookies and therefore cannot overlap unsafely. Keep credential/CSRF in memory only; no URL/localStorage/sessionStorage/service-worker retention.
5. Gate the entire private component tree and onboarding behind authenticated state. Add login, retry/configuration errors and logout. Clear private state and cancel pending requests on expiry/reset. Late business responses use a captured session epoch and cannot invalidate a newer login. Do not automatically replay writes, including CSRF failures; failed logout is explicitly unconfirmed.
6. Normalize client headers, enforce same-origin requests and inject the current CSRF only on unsafe requests. Handle 204 responses. Bring QR fetches into the session boundary, revoke Blob URLs, and prevent late creation after unmount. SSE errors close the stream and perform one session check before fallback/reconnect; direct media remains Cookie-based.
7. Preserve the exact anonymous resource allowlist. Add middleware-only 303 redirects for unauthenticated HTML GET/HEAD navigation to the exact known SPA routes (`/accounts`, `/subscriptions`, `/contents`, `/assets`, `/library`, `/jobs`, `/settings`, `/diagnostics`) to root login with a fixed allowlisted return path. Drop arbitrary query data; Host checks still run first, APIs/unknown paths keep fixed rejection, and no downstream handler runs on redirect. The frontend accepts only that same fixed return-path set.
8. Replace legacy/fallback interactive HTML with a protected migration/build notice and correct the obsolete “no authentication” onboarding copy. Do not expose legacy or remove backend protection.
9. Add focused state-machine/client and backend regressions, then serial Web format/test/check/build and a real local backend + built-browser smoke with disposable synthetic account/operation/media fixtures only. Record what each fixture proves; it cannot grant live platform/playback qualification.
10. Run proportionate Python full/static/docs/upstream/package gates; independently review auth races and pre-migration ordering. Final Docker/runtime-UID tests are NOT_RUN unless a Docker host is actually available. Explicitly stage reviewed paths, bilingual commit, push and verify remote divergence and cleanliness.

## Verification boundaries

Exercise anonymous gating, login then session order, auth serialization, unsafe CSRF and safe headers, logout/expiry, late old responses, no write replay, 204, QR cancellation, SSE session loss, deep-link GET/HEAD and Host/API refusal. Prove configuration-only execution leaves fresh and existing database/state untouched, including unreadable credentials, and verify entrypoint ordering without claiming static inspection is a Linux execution.

Use existing local browser tooling for the combined workflow; screenshots/logs must not retain credentials, CSRF, Cookie, raw QR or private locators. No user platform credentials or live remote actions are required. Keep current image, real PostgreSQL, restart/restore and live canary rows honest.
