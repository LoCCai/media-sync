**English** | [中文](goal.zh.md)

# Execution 0011 goal

- Status: Complete for the offline implementation and automated verification scope in local commit `8bb16f6`; every live row is `NOT_RUN`
- Started: 2026-08-31 02:17 +08:00
- Predecessor: Execution 0010 commit `f2e5899`

## Outcome

Deliver an explicit host-assisted MediaCrawler QR-login command for one exact initial QR account or one expired saved-session account. The command must open a headed, account-isolated upstream browser only after the operator enables MediaCrawler and acknowledges its license for that invocation. It records redaction-safe `LoginSession` and Account authentication states, performs no creator/content crawl, and atomically hands a successful attempt over to `saved_session` for later scheduler runs.

## Current evidence boundary

The implementation is recorded in bilingual local commit `8bb16f6`. Focused offline evidence covers the repository state machine (`32 passed`), application orchestration (`33 passed`), repository/application/login-model composition (`83 passed`), login-only integration (`42 passed`), saved-session audit (`25 passed`), CLI surface (`77 passed`) and the integrated login/saved-session/scheduler/download slice (`274 passed`). The complete suite passes `1080` tests with one Windows-inapplicable POSIX mode-bit test skipped; no coverage run is claimed. No browser, real platform account, creator endpoint, CDN or media server was used by these checks.

## Acceptance

1. **Default-off exact scope** — no child is started unless both MediaCrawler gates are present. The account must exist, use the MediaCrawler adapter and be either an eligible QR account or exactly `saved_session/expired`. Cookie, phone, authenticated/non-expired saved-session and foreign-adapter accounts are rejected before a browser or session mutation.
2. **Login-only headed child** — the pinned checkout and Python runtime are verified, the browser profile and account lock are derived from platform plus account UUID, and the upstream child is forced headed with saved login state. Its contract performs zero creator/search/detail/comment/media/store/ingestion work for all seven platform identifiers.
3. **Durable observable state** — `LoginSession` follows `pending → waiting_user → succeeded|expired|failed|cancelled`; initial QR states and exact `saved_session/expired` reauthentication atomically enter `qr/authenticating`. Success becomes `saved_session/authenticated`; expiry/cancellation/failure terminalizes the session and leaves a retryable QR account state. Fixed-state CLI output exposes IDs, statuses and timestamps only.
4. **Fenced handoff** — one local account login process tree is active while the runner holds the per-account lock, and database completion accepts only the still-current session through repository CAS. Success preserves only the derived stable profile, changes QR to `saved_session` atomically, and lets an existing `qr_required` scheduler Job continue through the existing explicit resume control without another QR challenge. Deadline and Ctrl+C paths terminalize the still-owned session rather than leaving a normal-path zombie. The execution 0012 audit corrected the earlier wording: the runner joins the tree and then releases the lock before the application writes this database completion; execution 0011 did not implement stale recovery in that interval.
5. **Saved-session fail-closed** — a missing derived profile or an authentication probe that reaches the blocked QR fallback maps conservatively to fixed `auth_expired`/`waiting_auth`; ordinary bridge configuration faults remain `configuration_invalid`. Upstream `pong() == false` may include network ambiguity, so no exact remote cause is claimed. A background scheduler run never silently opens an interactive browser.
6. **Explicit child truth** — the login child emits a closed result protocol. Upstream `SystemExit`, including exit code zero on a login failure, cannot be mistaken for success.
7. **Cancellation and secrecy** — under a live parent, timeout/cancellation/Ctrl+C terminates and joins the child process tree before releasing the account lock and records a recoverable fixed state. QR bytes/tokens, Cookies, raw child stdout/stderr and local profile paths never enter SQLite, CLI output, logs, docs or Git. Hard parent termination such as SIGKILL is not claimed recoverable in this execution.
8. **Truthful qualification** — offline fake-child coverage may qualify the local protocol for all seven identifiers, but every real-account QR row remains `NOT_RUN` until the user performs an authorized scan. Phone login, CAPTCHA bypass, REST, daemon, Docker, hard-parent-death login recovery, content sync and platform media expansion are outside this execution.

## Schema decision

Start by reusing the existing `accounts` and `login_sessions` columns. Local single-account exclusion is owned by the existing per-account filesystem lock, while repository transitions use conditional current-state updates. Add a migration only if implementation proves that the required fencing cannot be expressed safely with these existing identities.
