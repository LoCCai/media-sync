**English** | [中文](plan.zh.md)

# Execution 0011 plan

- Status: Offline implementation, automated verification, final read-only secret audit and local implementation commit `8bb16f6` complete; live qualification remains `NOT_RUN`
- Plan date: 2026-08-31
- Predecessor: Execution 0010 commit `f2e5899`

## Delivery sequence

1. **Freeze state contracts**
   - Add typed, closed login requests/results and fixed error codes.
   - Extend Account/LoginSession repositories with conditional start, waiting, success, expiry, failure and cancellation transitions.
   - Admit eligible QR states plus exact `saved_session/expired` reauthentication; prove every other account/method/adapter scope has zero session/browser side effects.

2. **Build an isolated login-only integration
   - Reuse pinned checkout/Python verification, derived per-account paths, the account lock and bounded process-tree supervision.
   - Add a private closed parent/child protocol that reports authenticated, expired, failed or cancelled independently of process exit code.
   - Force headed QR login and persistent browser state while configuring a login-only upstream mode that cannot start creator/content work.
   - Catch upstream `SystemExit` explicitly and reject missing, duplicate, oversized or malformed result frames.

3. **Compose the application and CLI
   - Add `media-sync account login --account-id ... --enable-mediacrawler --accept-mediacrawler-license` as a blocking host-assisted command.
   - Add redaction-safe session/status inspection under the account command group.
   - Keep QR challenge material inside the visible upstream browser; do not extract or serialize it.
   - On success, atomically finalize the session and switch Account login method to `saved_session`; leave scheduler Job resume explicit.
   - For expired saved-session reauthentication, atomically enter `qr/authenticating`; restore `saved_session/authenticated` only on success and retain a retryable QR state on non-success.

4. **Make scheduled saved sessions fail closed
   - Remove the current saved-session-to-QR fallback from the bridge.
   - Validate profile presence before creator traffic; distinguish unavailable saved-session state from ordinary bridge configuration errors, and conservatively map a blocked QR fallback to auth-required state without claiming an exact remote cause.
   - Prove background scheduler execution never opens a headed interactive challenge.

5. **Verify and close out
   - Add repository, login protocol, process supervision, seven-identifier contract, scheduler handoff, CLI and secret-sink tests.
   - Cover deadline and Ctrl+C terminalization, expired saved-session reauthentication and ordinary-configuration versus auth-expired classification.
   - Run focused tests, full pytest, Ruff, format, mypy, docs/upstream checks, build and `git diff --check`.
   - Update all four execution records with exact commands/results and keep every live-account row `NOT_RUN`.
   - Create a bilingual local implementation commit after the complete gate. Do not push until the user gives a new explicit instruction.

## Administrative closeout

- Bilingual local implementation commit `8bb16f6` is recorded; no remote push is claimed.
- Keep all seven live QR and saved-session reuse rows `NOT_RUN` until an operator authorizes and performs the real scan.
- Carry hard-parent-death LoginSession recovery/parent-liveness into the next execution; do not infer it from normal timeout, cancellation or Ctrl+C coverage.

## Risks and rollback points

- The upstream login implementations may terminate with `SystemExit(0)` on failure; only the closed child result is authoritative.
- A false saved-session `pong()` may reflect expiry or an upstream network ambiguity. `auth_expired` is a conservative operator action, not an exact remote-cause diagnosis; ordinary local bridge misconfiguration must remain `configuration_invalid`.
- Normal parent paths join the process tree and terminalize durable state, but SIGKILL cannot run cleanup. Automatic stale LoginSession recovery requires a future parent-liveness protocol.
- A browser login is necessarily interactive and may wait on QR/CAPTCHA. A hard timeout, cancellation join and explicit operator invocation bound that risk; no automated CAPTCHA work is planned.
- The initial MVP is local-host single-account coordination, not cross-host HA. If existing identities cannot fence stale completion, stop and add a migration rather than weakening the contract.
- A login-only upstream mode must be proven against the pinned SHA for all seven identifiers. If any platform performs content work, that platform fails closed until a narrower wrapper exists.
- Rollback is deletion of the new login command/integration and restoration of saved-session rejection; existing Cookie scheduling, stored accounts and execution 0010 pipeline remain untouched.
