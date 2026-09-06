**English** | [中文](goal.zh.md)

# Goal: adopt native MediaCrawler sessions into the existing subscription pipeline

Execution 0073 closes the smallest remaining seam between the authenticated native MediaCrawler console delivered in execution 0072 and media-sync's existing account-scoped subscription pipeline. The locked upstream `/crawler/` console becomes the primary place for QR and Cookie login. After the operator completes login there, they explicitly adopt that platform's saved browser profile into one existing media-sync Account. A successful, non-interactive validation publishes the Account as `saved_session` / `authenticated`; the existing scheduler, JSONL ingestion, controlled download, archive, library-folder and NFO path then continues unchanged.

This execution does not build another login implementation, crawler, downloader or publication pipeline. It also does not claim that all seven platforms have passed human login or live crawling. The adoption boundary transfers authenticated browser state; it does not infer authentication from the presence of files, a WebUI success label or a previous platform result.

## Product flow

1. The operator creates or selects an existing media-sync Account for the exact platform.
2. The Accounts page sends login actions to the authenticated `/crawler/` console instead of presenting media-sync's custom QR/Cookie flow as the primary path.
3. The operator completes the locked upstream QR or Cookie login in `/crawler/`.
4. Back on the Account, the operator explicitly requests adoption of that platform's saved profile.
5. media-sync exclusively transfers the quiescent WebUI profile into the selected Account's managed profile location and validates it through the existing saved-session boundary with QR fallback disabled.
6. Only a successful validation atomically publishes `login_method=saved_session` and `auth_status=authenticated`. The Account can then be used by the existing Subscription scheduler.
7. A Subscription performs the established history-to-incremental workflow and writes its media library folders and NFO files without requiring an Emby or Jellyfin connection.

## Ownership and data boundary

| Concern | Owner after 0073 | Boundary |
| --- | --- | --- |
| Interactive QR/Cookie login and browser-visible crawler controls | Pinned MediaCrawler WebUI | Authenticated `/crawler/`; no second public listener |
| Saved profile adoption and Account authentication state | media-sync | Explicit, same-platform, operator-authenticated and CSRF-protected action |
| Scheduled creator crawl and normalization | Existing media-sync scheduler/MediaCrawler runner | Account-scoped profile; existing Subscription policy and acknowledgements remain authoritative |
| Media retrieval, archive and NFO publication | Existing media-sync pipeline | Continue the proven fallback coverage; do not add a competing path in this execution |
| Emby/Jellyfin server refresh | Optional integration | Never a prerequisite for compatible directories and NFO files |

The pinned upstream has native media-download support only for part of the required surface currently evidenced in this repository: portions of Xiaohongshu, Douyin and Bilibili. It is not yet complete across seven platforms or all mixed-media shapes. Therefore execution 0073 deliberately keeps scheduled delivery on the existing media-sync ingestion/download/archive/NFO pipeline. Interactive `/crawler/` output is not silently ingested or downloaded a second time. Replacing more fallback download coverage with completed upstream artifacts requires a separate, evidenced execution.

## Acceptance criteria

1. **The native console is the primary login entry** — the Accounts UI directs operators to `/crawler/` for QR or Cookie login and clearly returns them to an explicit adoption action. The old custom login controls are no longer presented as the normal path. Compatibility code may remain internally where the established saved-session probe or scheduler still depends on it, but it is not advertised as a parallel product flow.
2. **Adoption is explicit and same-platform** — a request identifies an existing Account plus a platform, uses operator authentication and CSRF protection, and requires the Account platform to match the selected WebUI profile. The server derives both source and destination paths; it accepts no filesystem path, Cookie, credential or browser-state payload from the client.
3. **One profile has one owner** — adoption is a move/claim, not a shared copy. One WebUI platform profile can be adopted by only one Account, and an Account cannot silently replace a non-empty managed profile. Re-adoption or replacement requires a separately explicit, conflict-safe design rather than implicit overwrite.
4. **Only quiescent state crosses the boundary** — reject adoption while the upstream crawler/login process or the selected Account's scheduler/profile lock is active. Hold the applicable WebUI runtime and Account locks through transfer, validation, publication or rollback so the Chromium profile is never read or moved concurrently.
5. **Filesystem handling is confined and reversible** — accept only the expected non-empty directory beneath `webui-profiles/<platform>_user_data_dir`; reject traversal, symlink/reparse escape and unsupported file types. Stage and move only beneath the configured MediaCrawler runtime root. A failed transfer or validation restores the source profile where safely possible, leaves the Account unchanged and emits a fixed safe failure classification.
6. **Files alone never grant authentication** — validate the adopted candidate using the fixed pinned checkout/interpreter and the existing non-interactive saved-session probe, with QR fallback fenced off. A missing, expired, ambiguous or malformed result is failure. Do not treat directory presence, upstream UI status or another platform's successful session as proof.
7. **Account publication is atomic and fenced** — after validation, re-check Account identity, platform, auth revision and lock ownership before committing `saved_session` / `authenticated`. Clear incompatible credential references according to the existing invariant, retain no client-supplied profile path, and record a bounded Operation/Event result without Cookie values, local profile contents or sensitive upstream output.
8. **Failure does not corrupt either side** — cancellation, timeout, process failure, stale Account revision, publication conflict and service shutdown leave a retryable, truthful state. A failed validation must not authenticate the Account; a late success must not cross a lost fence; no partial destination may be selected by the scheduler.
9. **The existing delivery chain is reused** — after adoption, the Account resolves to the same account-scoped profile path already consumed by creator lookup, scheduled crawl, detail refresh and media download. Do not introduce a second Subscription dispatcher, content identity scheme, downloader, archive layout or NFO writer.
10. **Filesystem output remains the product result** — a valid Subscription may crawl history, continue scheduled incremental checks, and publish deterministic compatible folders/NFO under the configured library root even when no Emby/Jellyfin provider is configured. Server refresh and playback verification remain optional follow-up evidence.
11. **Qualification remains honest** — deterministic tests must cover route/auth/CSRF checks, platform mismatch, empty/unsafe profiles, exclusivity, busy locks, successful validation/publication and every rollback boundary. These tests do not qualify real QR/Cookie login, platform requests, CDN bytes or seven-platform behavior. Live rows remain `NOT_RUN` until individually observed and recorded.

## Explicitly out of scope

- Reimplementing or repairing individual platform login flows outside the pinned MediaCrawler WebUI.
- Claiming seven-platform human login, creator crawl, native media completeness, anti-risk behavior, CDN retrieval or media-server playback without live evidence.
- Ingesting arbitrary interactive `/crawler/` output, importing upstream logs wholesale, or replacing the existing scheduled download/archive/NFO pipeline.
- Sharing one browser profile among Accounts, accepting arbitrary profile paths, or exposing Cookie/profile contents through the API, logs or support bundles.
- Redesigning Subscription history limits, cadence, backoff or risk-control policy beyond proving that an adopted Account enters the current scheduler path.

## Completion evidence

Execution 0073 is complete only when the bilingual progress and verification records show the exact implementation revision, focused adoption/UI tests, relevant scheduler and pipeline regressions, full repository gates, source/package parity, and any real deployment checks actually run. If no live deployment occurs, `/crawler/` QR/Cookie login and Account adoption remain locally implemented but live `NOT_RUN`; the documents must say so plainly.
