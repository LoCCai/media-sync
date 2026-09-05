**English** | [中文](progress.zh.md)

# Login browser runtime progress

- Date: 2026-09-05
- Status: Implemented and locally verified; publication closeout in progress; live qualification pending

The previous turn made progress: authenticated UI evidence, independent environment-filter reproduction and source/channel mismatches were recorded in commit `db6c3c7`. Current worktree was clean at resumption. The new increment repairs those shared paths; no deployed platform success is inferred.

## Implemented

1. A shared secret-denying browser environment retains the installed cache path for login, creator and detail execution. It does not forward arbitrary proxy/Python/debug/operator settings or parent private input.
2. An in-memory bundled-Chromium policy wraps the pinned factory and standard launch methods in all three entry points, including numeric Bilibili aid detail. It removes the conflicting channel and selects the installed executable, preserving upstream options, profile and lifecycle ownership. The upstream checkout and lock remain unchanged.
3. Account login preflight now exercises a blank headed persistent browser with the same environment and bundled executable. A disposable profile, start gate, Windows Job/POSIX process-group containment, timeout and tree cleanup protect ordinary outcomes. Only a bounded numeric version may leave the subprocess; raw errors do not.
4. Xvfb must pass a bounded real connection/liveness check after operator configuration validation and before migrations. The image adds `x11-utils`; missing tools, process death and timeout produce fixed errors and nonzero exits.
5. `scripts/check_login_browser.py` provides a credential-free runtime-UID smoke command. Deployment, status and journal docs now point to the repair without changing private Compose settings.
6. Existing synthetic fixtures now supply the factory/launcher structure that the production policy requires. New tests execute verified pinned factory/main/launcher bodies and real entry wiring; platform network work remains stubbed.

## Verified so far

- 134 focused checks cover the policy, seven-platform wiring, environment, preflight and smoke command.
- 205 existing login/detail/saved-session/scheduler regressions and 152 bridge/CLI regressions passed (one Windows-inapplicable skip in the latter).
- 77 startup/configuration regressions passed under Git Bash stubs, including an actual coreutils hung-probe termination.
- A real blank Windows headed Chromium launch returned version `151.0.7922.34` and exited successfully, using an ignored isolated Playwright 1.62.0 probe runtime.
- Full Python and final package/publication results are recorded in [verification](verification.md), not inferred from these focused counts.
- The complete collected suite passed 3264 tests, with 22 expected skips and one existing warning in 679.04s; the additional 29 wiring tests passed separately as part of the 134-test final union. Do not relabel that as a single 3293-test full run.

## Still pending

- Rebuild and verify the exact Linux image under the server's mapped UID, preserving credentials, Origin and the named volume; verify startup/restart/restore and the headed smoke.
- With the operator, observe one real QR image, scan and successful account authentication, then verify saved-session reuse, author subscription, capture, download and Emby/Jellyfin output. Extend to all seven platforms; no successful live row has been recorded by this repair.
- Runtime failures beyond preflight still collapse into a general failed state; add safe actionable categories and durable account-page explanation if the rebuilt deployment reaches later failure stages. Do not expose raw upstream logs.
- Generic headless readiness retains its prior lifecycle implementation. Hard POSIX parent death is not covered by this preflight's ordinary timeout/finally cleanup guarantee. P1 evidence UI and other documented product backlog remain open.
