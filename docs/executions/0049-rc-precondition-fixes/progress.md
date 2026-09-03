**English** | [中文](progress.zh.md)

# Execution 0049 progress

- Status: RC-precondition fixes implemented; runtime verification stays with phase B
- Date: 2026-09-03
- Plan commit: `dcba270` (documentation baseline)

## Delivered

1. Dockerfile: the pinned checkout now materializes at `/app/.upstream/MediaCrawler` (the exact lock-relative path) with `.git` intact; `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright` is set for both install and runtime; the runtime user owns the browser cache; the build manifest launches Chromium as `mediasync` and records the real version plus the resolved base image; the manifest app-venv freeze falls back to `uv pip freeze`.
2. Compose template: `BASE_IMAGE` passes through as a build arg (digest-pinnable), and the bind-mount note states it must apply to both services; the deployment docs add the digest-pinned RC build block and the in-container doctor preflight plus a real Chromium-launch check as phase-B gates.
3. API: blocked/failed downloads finish their operation with `error_code` (state `failed`); the console button relabels to 下载/校验; every background thread and the login-status path use the settings captured by `create_api_app()`.
4. Tests: the download endpoint gains real-Asset lifecycle coverage — blocked→`failed` with `locator_refresh_unsupported`, hand-verified-without-archive→`failed` with `asset_download_state_invalid` (the honest inconsistency signal), and a completing executor driving running→`succeeded` with app-captured settings.
5. Docs: both journal readmes de-duplicated (each 156 lines, one H1, one switcher); the single index now carries the 0043 deferral, the 0044 absorption, the 0047 canary-first restructure and the 0049 row; 0043's plan syncs to deferred; 0044 closes as absorbed with pointer-only progress/verification records; the architecture note states the delivered ffmpeg stream-copy reality and the current toolchain; the third-party notice describes the operator-built image accurately; the status pages record the sanitized junit artifact and mark Windows-native runs Experimental pending classification.
6. The documentation checker now rejects duplicate H1/H2 headings, stray or multiple language switchers and English/Chinese heading-structure divergence (code blocks excluded), and would have caught the readme duplication.
7. The parent process carries the fixed completion-receipt reason codes into redacted diagnostics (`completion_failed (unsafe_path)` style), so test diagnostics can distinguish why a completion failed without any path data.

## Verification snapshot

See [`verification.md`](verification.md) for the exact commands, exit codes and gate outputs.

## Not done

Docker build/run, the in-container doctor preflight and the Chromium-as-`mediasync` launch stay `NOT_RUN` on this station (no Docker) and are the first phase-B steps; every live qualification row stays with 0047.
