**English** | [中文](plan.zh.md)

# Plan

## 1. Freeze the seam and preserve the working pipeline

- Confirm the two managed profile locations and reuse the existing path builders:
  - WebUI source: `<runtime-root>/webui-profiles/<platform>_user_data_dir`
  - Account destination: `<runtime-root>/accounts/<platform>/<account-id>/browser_data/<platform>_user_data_dir`
- Trace the existing Account repository invariants, saved-session probe, profile/account locks, Subscription delivery, scheduler handler, JSONL ingestion, asset download, immutable archive and library/NFO publication. Reuse those boundaries; do not add a second run or media state machine.
- Keep `/crawler/` interactive output separate from scheduled output in this execution. Scheduled runs continue through the established normalized pipeline so the same content identity, retry and publication contracts remain authoritative.
- Record the native-download limitation accurately: current evidence covers only portions of Xiaohongshu, Douyin and Bilibili, not seven complete platform/media matrices. Do not remove the existing download fallback or cause the same scheduled asset to be downloaded by both paths.

## 2. Define a narrow session-adoption application boundary

- Add one typed application request containing only Account identity and expected Account auth revision. Resolve the platform from the Account and derive all profile paths from trusted settings and database state; reject path, platform, Cookie, credential and arbitrary metadata fields at the API boundary.
- Require an existing eligible MediaCrawler Account and resolve the exact same-platform WebUI profile from it. Reject deleted, stale, busy or malformed Accounts with fixed conflict codes.
- Expose adoption as an operator-authenticated, CSRF-protected mutation carrying the Account's expected authentication revision. Return a bounded state and safe next action; never return profile entries, Cookie values, command lines or raw child output.
- Treat initial adoption and later refresh as the same explicit, revision-fenced snapshot action. Never merge live Chromium trees or share a runtime profile. A successful refresh atomically replaces only that Account's previous snapshot; failure restores it.

## 3. Make profile transfer exclusive, confined and recoverable

- Add a media-sync-owned coordinator that first proves the embedded WebUI crawler/login child is stopped and holds the WebUI profile gate while taking and validating the snapshot. Acquire the destination `MediaCrawlerAccountLock` before the short replacement/publication section. Reject busy state rather than waiting without a bound.
- Re-read the Account after locks are held. Fence the operation with its expected auth revision and platform so concurrent edits, deletion, login, creator lookup or scheduler dispatch cannot be overwritten by a late result.
- Validate the source using no-follow filesystem inspection. It must be the exact expected, non-empty platform directory beneath `webui-profiles`; reject path escape and prevent symlinks/reparse points or unsupported special entries from being copied.
- Copy regular files into an attempt-scoped Account-shaped staging location, never following links, while the source is quiescent. Validate this independent snapshot, then promote it to the exact destination with an atomic same-volume directory exchange so the scheduler never observes a partial profile.
- Maintain an explicit rollback journal for target replacement. Before Account publication, every failure keeps the WebUI source intact, removes only attempt-owned staging data and restores the prior Account profile when safe. Cleanup failure receives its own fixed classification and never turns an unverified Account into authenticated state.

## 4. Validate the adopted session before publication

- Invoke the existing pinned MediaCrawler saved-session probe against the staged Account-shaped snapshot, fixed checkout and dedicated interpreter. Force non-interactive/headless saved-session behavior and retain the existing fence that forbids QR fallback.
- Apply the existing deadlines, controlled child process tree, safe output parsing and secret redaction. Accept only the exact authenticated terminal result for the requested platform; expired, login-required, timed-out, cancelled, ambiguous and malformed outcomes fail closed.
- After a successful probe, re-check operation ownership, Account revision/platform and destination identity in the publication transaction. Reuse repository invariants to set `login_method=saved_session`, `auth_status=authenticated`, advance the auth revision and clear incompatible credential/profile-path fields.
- Return a bounded outcome only after Account-profile replacement and database publication agree. If database publication conflicts, restore the prior Account profile and do not surface success. Make restart reconciliation conservative: uncertain installation is not an authenticated Account and requires an explicit retry/recovery path.

## 5. Change the Accounts UI to the native-login flow

- Replace the normal QR/Cookie login calls to action with a concise three-step flow: open `/crawler/`, complete native login for the Account's platform, return and adopt the saved session.
- Open the same authenticated `/crawler/` route; do not expose an upstream port or create a second login form. Preserve exact deployment prefix/origin behavior delivered by 0072.
- Add an Account-scoped “Adopt saved session” action that shows the exact platform and Account, carries the expected auth revision, and reports stable outcomes: no saved profile, crawler busy, Account busy, validation expired/failed, conflict, cleanup failure or success.
- On success, refresh the existing Account read model so the user sees `saved_session` / `authenticated` and can continue to creator lookup or Subscription creation. On failure, show a safe actionable message; do not render raw logs or secrets.
- Remove or demote custom QR/Cookie controls from the primary Accounts experience. Keep only internal compatibility seams required by the probe/scheduler; API removal or database migration is not required by this execution.

## 6. Prove connection to the existing Subscription chain

- Add an integration test that seeds an eligible Account, adopts a synthetic profile through a fake authenticated saved-session result, creates a Subscription, and proves scheduler dispatch resolves the exact adopted account-scoped profile.
- Exercise the existing handler through normalized ingestion and a bounded media fixture into archive and Emby/Jellyfin-compatible folder/NFO publication. Assert no media-server profile is configured and publication still succeeds.
- Verify the adoption work introduces no alternate content IDs, output roots, asset downloader, archive writer, export requirement or provider connection. Interactive `/crawler/` output remains outside automatic scheduled ingestion in 0073.
- Preserve current history acknowledgement, pagination bounds, cadence, retry/backoff and account-expiry behavior. A real historical crawl, incremental follow-up and risk-control qualification remain deployment evidence, not consequences inferred from an offline fixture.

## 7. Test failure and concurrency boundaries

- Unit-test path derivation, API schema rejection, operator auth/CSRF, source absence/empty state, unsafe entries, bounded transfer and safe response projection.
- Integration-test WebUI-busy and Account-busy rejection, stale auth revision, pre-cancellation, expired/failed/malformed probe results, database conflict, prior-profile rollback and successful publication.
- Prove successful adoption leaves the source intact and installs one independent Account-owned snapshot; prove every pre-publication failure leaves the Account unauthenticated and never lets scheduler observe a partial destination.
- Regress existing QR/Cookie compatibility services only to ensure the hidden internal seams still work where required. Do not count synthetic success as real platform authentication.

## 8. Verify, document and release honestly

- Run focused Python unit/contract/integration suites for adoption, API, Account repository, MediaCrawler saved-session behavior, scheduler handler, ingestion, pipeline, archive and NFO publication.
- Run the full Python suite and Web tests plus Ruff, formatting, mypy, frontend formatting/check/build, documentation checks, upstream-lock/source-integrity checks, packaging and source/package parity. Record exact commands and final counts only after execution.
- Add bilingual `progress.md` / `progress.zh.md` and `verification.md` / `verification.zh.md` with implementation revisions, corrected failures, skipped environment rows and deployment status. Use bilingual Git commit messages and push only after all intended files are reviewed.
- On the deployed host, first verify `/crawler/` access and a single authorized platform login/adoption while the scheduler cannot race the profile transfer. Then use one bounded Subscription canary to prove account profile reuse, ingestion, media bytes, compatible directory/NFO and later incremental behavior.
- Keep each unexecuted live platform login/crawl/CDN row and Emby/Jellyfin scan/playback row as `NOT_RUN`. A media-server connection remains optional; filesystem publication is the required result.

## Stop conditions

- Stop rather than publish if the WebUI profile cannot be exclusively quiesced, the profile is unsafe or already owned, validation would permit interactive QR fallback, the Account fence changes, rollback cannot establish one clear owner, or the existing scheduler would observe a partial profile.
- Do not expand this execution into a new log center, arbitrary WebUI-output importer, native-download rewrite, seven-platform repair campaign or media-server integration. Capture such findings as follow-up work with evidence.
