**English** | [中文](plan.zh.md)

# Execution 0049 plan

- Status: Executed and verified
- Plan date: 2026-09-03
- Predecessor: `0eb3f895b02137cbfe231c705ba34aa1ce86a9f4`
- Database migration: None planned
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Baseline and audit

The RC-precondition review accepted 0048's direction but rejected `0eb3f89` as a Linux RC baseline. Two statically confirmable Docker blockers (checkout at `/opt/mediacrawler` while the lock resolves `.upstream/MediaCrawler` relative to `/app`, plus `.git` deleted; Playwright installed as root into a per-user cache the runtime user cannot read), two operations semantics issues (downloads that fail or stay blocked still finish as `succeeded`; "redownload" label overstates the verified-asset no-op), missing positive-lifecycle API tests, a fully duplicated project-log readme pair carrying a stale index, and several status/architecture/notice residuals.

Baseline gates recorded before implementation: the pulled tree passes `ruff check .`, the documentation link checker (416 files) and the upstream lock checker on this workstation; the new 0039/0040 unit files pass (14 tests).

## Delivery sequence

1. Dockerfile: clone the pinned checkout to `/app/.upstream/MediaCrawler` keeping `.git`; set `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright` for both install and runtime; chown the browser cache to the runtime user; record the actually-launched Chromium version in the build manifest; keep the doctor preflight as the phase-B gate.
2. Compose/deployment: document digest-pinned base-image builds, pass `BASE_IMAGE` through as a build arg, and note that bind mounts must be applied to both services.
3. API: finish failed/blocked download operations with `error_code`; relabel the endpoint/console wording to download/verify; make every background thread and the login-status path use the app-captured settings.
4. Tests: add real-Asset lifecycle coverage (succeeded, blocked→failed, verified no-op) and keep the existing gates green.
5. Parent diagnostics: carry the fixed completion-receipt reason codes into the redacted message; capture the authoring-station failure list as a sanitized junit-derived artifact.
6. Docs: de-duplicate the two readme files, sync the 0043/0044/0047 index rows and 0043/0044 plan states, close 0044 as absorbed, correct the architecture/third-party-notice/status wording, and strengthen the documentation checker (duplicate H1/H2, stray switchers, bilingual heading parity).
7. Run the focused and complete offline suites plus the full static gate family; write the four execution documents; create bilingual implementation/closeout commits, push and reconcile.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

The upstream tree stays excluded, unmodified and clean.
