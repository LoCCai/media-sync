**English** | [中文](progress.zh.md)

# Execution 0011 progress

- Status: Complete for the offline implementation and automated verification scope in local commit `8bb16f6`; live qualification `NOT_RUN`
- Started: 2026-08-31 02:17 +08:00
- Predecessor: Execution 0010 commit `f2e5899`

## Implemented in the current worktree

### Durable state and application orchestration

- Added conditional Account authentication CAS and a redaction-safe `LoginSessionState` projection. The repository enforces `pending → waiting_user → terminal`, one active local session, deadline fences and stale/sibling rejection. Initial QR states and exact `saved_session/expired` reauthentication atomically enter `qr/authenticating`; success changes that state to `saved_session/authenticated`, while non-success leaves a retryable QR state.
- Reused the existing schema. Savepoints make duplicate, stale and sibling conflicts zero-half-write even if a caller catches the fixed conflict and continues its outer transaction.
- Added `MediaCrawlerQrLoginService` with strict pre-run eligibility: a MediaCrawler QR account in `unknown|required|expired|failed`, or exactly a `saved_session/expired` account, may reach the runner only when persisted credential/profile references are absent. Authenticated/non-expired saved sessions, Cookie/phone/foreign accounts and missing accounts create no session and do not invoke the integration.
- Added fixed redaction-safe application errors for not-found, ineligible, busy, invalid configuration, start failure, invalid result, conflict and unexpected failure. Runner-controlled exception text is never operator output; post-hook invalid/exceptional outcomes attempt a conservative `failed` closeout.

### Login-only process boundary and CLI

- Added a closed typed request/result protocol and an isolated process runner for `interactive_qr` and `saved_session_probe`. The runner verifies the pinned checkout and Python runtime, derives account-scoped paths, owns the per-account lock through process-tree join and accepts only one bounded exact child frame.
- Interactive mode forces a headed QR browser and saved login state while clearing creator/search/detail/comment/media/store work for all seven platform identifiers. QR bytes remain inside the visible browser, and upstream output is silenced rather than persisted.
- Saved-session probe mode is headless and rejects the upstream QR fallback before interaction. `SystemExit`, including code zero, malformed/duplicate/oversized results, timeout and cancellation cannot authenticate. Under a live parent, timeout/cancellation closes and joins the complete process tree before lock release; detail fallback also guarantees `async_cleanup`.
- Added explicit `media-sync account login` double gates and `account login-status`. Output contains only fixed IDs, statuses and timestamps; it omits credential references, profile paths, challenge material and child output.
- Background forward/detail paths now force saved sessions headless and block QR fallback. A missing derived profile uses the dedicated saved-session-unavailable boundary and maps to fixed `auth_expired`; ordinary `BridgeConfigurationError` remains `configuration_invalid`. A probe that reaches the blocked QR fallback also maps conservatively to `auth_expired`, but upstream `pong() == false` may contain network ambiguity, so this is not an exact remote-cause claim. Scheduler/download paths persist Account `expired` only for the fixed auth-expired outcome. No background path silently opens an interactive browser.

## Verified so far

- Repository state-machine focused gate: `32 passed in 6.55s`.
- Application orchestration focused gate: `33 passed in 6.64s`; repository/application/login-model composition: `83 passed in 13.13s`.
- Login-only runner/unit/contract gate: `42 passed in 23.57s`; its targeted Ruff, format, mypy, package-export import and whitespace checks pass.
- Saved-session forward/detail/scheduler audit: `25 passed in 0.97s`; its test Ruff/format and five-source mypy checks pass.
- CLI gate: `77 passed in 13.36s`.
- Integrated repository/application/login-only/CLI/saved-session/download/scheduler gate: `274 passed in 70.73s`.
- A later exact closure test proves that a successful QR login can resume the pre-existing `qr_required` Job under `saved_session` without creating a second Job or interactive fallback: `1 passed in 0.82s`.
- Deadline and Ctrl+C regressions terminalize the still-owned durable LoginSession instead of leaving a normal-path zombie; the final integrated gate includes them and passes `274` tests.
- Complete suite: `1080 passed, 1 skipped in 226.92s`; the sole skip is `tests/contract/test_mediacrawler_supervision.py:556`, whose POSIX mode-bit assertion is not the Windows ACL boundary. No coverage run was performed or claimed.
- Project-wide Ruff, format, mypy, documentation, pinned-upstream and sdist/wheel build gates all pass.
- These automated results complete the offline implementation scope; they are not evidence of live platform compatibility.

## Deviations and decisions

- Prioritize an explicit host-assisted `account login` control surface before a resident daemon or REST API because it unlocks the user-facing authentication path while keeping interactive authority visible.
- The login command handles only eligible initial QR states or exact `saved_session/expired` reauthentication. Start atomically becomes `qr/authenticating`; success returns to `saved_session/authenticated`, while failure/timeout/cancellation remains retryable QR state. Cookie, phone, active/non-expired saved-session, foreign-adapter, credential-bearing and persisted-profile-path accounts are rejected before integration.
- Do not serialize QR images or tokens. The user scans the upstream headed browser directly.
- No migration was required for the local-host model. Coordination relies on one derived runtime root plus its per-account filesystem lock and repository CAS; cross-host HA is not claimed.
- Treat a saved profile as derived runtime state rather than a database path or credential. Success changes the login method to `saved_session`; scheduled reuse derives the same account-scoped profile and fails closed if it is unavailable or reaches the blocked QR fallback. This conservative state does not distinguish expiry from every upstream network ambiguity.

## Remaining outside the completed offline scope

- Bilingual implementation commit `8bb16f6` created; remote push remains unclaimed.
- Real-account QR scans for all platforms remain `NOT_RUN`.
- Hard-parent-death LoginSession recovery and a parent-liveness protocol remain for the next execution; normal timeout/cancellation/Ctrl+C coverage does not prove SIGKILL recovery.
