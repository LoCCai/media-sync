**English** | [中文](progress.zh.md)

# Progress: native MediaCrawler login now feeds the subscription pipeline

Status: the local implementation is complete in commit `165516a`. Deployment of that revision and live platform qualification remain pending.

## Outcome

The product boundary has been corrected and simplified:

```text
/crawler/ (native MediaCrawler QR/Cookie login and crawler controls)
    -> explicit saved-profile adoption
    -> account-scoped verified session snapshot
    -> existing Subscription scheduler
    -> job-scoped JSONL ingestion
    -> download/archive
    -> configured library root/<platform>/<creator>/ + NFO
```

media-sync no longer presents its custom QR, pasted-Cookie, login-preflight and login-diagnostic workbench as the normal Accounts workflow. The Accounts page now has three direct steps: open the native crawler console, complete login there, then adopt the saved session for a local Account of that platform.

## Implemented

1. **Native console is the login surface.** The pinned upstream MediaCrawler WebUI remains mounted at authenticated `/crawler/`, with its own platform, QR/Cookie, creator/detail/search, start/stop, live-log and data-preview controls. No second platform login UI was added.
2. **Explicit account session adoption.** `POST /api/v1/accounts/{account_id}/crawler-profile` accepts only `expected_auth_revision`. Account identity and platform come from the database; profile paths and Cookie material cannot be supplied by the browser.
3. **Verified profile snapshot.** While the embedded crawler is idle, media-sync copies regular profile files without following links into a temporary Account-shaped location. It runs the existing pinned non-interactive saved-session probe with QR fallback disabled. Only an authenticated result can continue.
4. **Atomic replacement and rollback.** After acquiring the real Account profile lock, the verified snapshot atomically replaces that Account's prior profile. A database revision conflict restores the prior profile. The WebUI source remains intact so the operator can renew login later and explicitly re-adopt it.
5. **Subscription recovery.** Successful adoption publishes `saved_session / authenticated`, increments `auth_revision`, clears incompatible credential/profile overrides, and resumes only this Account's `waiting_auth` sync jobs. `waiting_user` work is not resumed.
6. **Public error contract.** The API maps internal failures to a small stable set such as `crawler_busy`, `account_busy`, `crawler_profile_not_found`, `crawler_profile_auth_failed` and `account_revision_conflict`. The Web UI shows fixed Chinese actions and never reflects paths, Cookie values or raw exceptions.
7. **Scheduler proof.** A new integration test adopts a synthetic WebUI profile, creates a Bilibili Subscription and proves that scheduler dispatch uses the exact installed Account profile with `saved_session`, without resolving a Cookie secret, before successful normalized ingestion.
8. **Zhihu WebUI compatibility.** The pinned upstream CLI maps `--creator_id` for six platforms but omits `ZHIHU_CREATOR_URL_LIST`. The thin child compatibility seam now fills only that missing `zhihu + creator` assignment while preserving the upstream argv and leaving `.upstream` unchanged.

## Deliberately reused rather than rebuilt

- MediaCrawler owns interactive platform login and crawler interaction.
- The existing media-sync scheduler owns history/incremental Subscription runs and rate/backoff policy.
- Existing job-scoped receipts and ingestion remain authoritative; shared `/data/mediacrawler/webui-output` is still only an interactive-console output area and is not silently imported.
- Existing download, SHA-256 archive, output-directory and Emby/Jellyfin NFO code remains the single scheduled delivery path.
- Connecting to an Emby/Jellyfin server is optional. Compatible files and NFO are written to the configured directory even with no media-server provider.

## Historical 0072 deployment observation on 2026-09-06

Before `165516a` was deployed, the operator opened the existing 0072 deployment's `/crawler/` and observed `{"detail":"license_acknowledgement_required"}`. This is the expected closed gate when the API service itself lacks `MEDIA_SYNC_MEDIACRAWLER_LICENSE_ACKNOWLEDGED=true`; the supervisor command-line acknowledgement does not configure the API container. Add the variable under `services.media-sync.environment` and force-recreate that service. This observation does not identify or qualify a 0073 image, and a post-change page load has not yet been reported.

## Remaining live work

- Pull and build the final published revision on the Linux host.
- Confirm `/crawler/` loads after the API-container license acknowledgement.
- For each platform, perform native QR or Cookie login, stop/finish the crawler, adopt the matching Account session, and record the real result.
- Run one bounded Subscription canary through creator lookup, capture, media download and final directory/NFO inspection; then verify a later incremental cycle.
- Keep every unobserved platform/CDN/history-completeness row as `NOT_RUN`. Do not infer seven-platform success from offline tests.
