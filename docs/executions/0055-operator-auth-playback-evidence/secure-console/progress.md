**English** | [中文](progress.zh.md)

# Safe console progress

- Date: 2026-09-05
- Status: Implementation and local combined verification complete; external qualification remains open

## Delivered

Previous checkpoint `2e1949f` is published on `origin/main`. This eight-file bilingual baseline was committed first as `714c849`; all parent/child frozen goal/plan files remain unchanged.

1. `serve --check-config` reuses real settings/secret/origin/bind-syntax checks with fixed safe output and no application/database/directory/socket/migration work. Container serve preflights before Xvfb and `db init`, including Click's `-- serve`; explicit help/check-only does not initialize state.
2. The operator login/session/logout shell serializes Cookie-mutating requests. Login requires subsequent session/CSRF retrieval. Credential/CSRF stay in memory; the private component tree follows session epochs, expiry and logout. Unconfirmed logout stays locked; late responses cannot revive a newer view.
3. Business and QR requests use same-origin Cookie, unsafe-request CSRF, cancellation and 204 handling, without automatic mutation replay. SSE closes then checks session before fallback. Current-epoch HTTP 401 locks immediately even with a corrupt or stalled body.
4. Exactly eight known HTML GET/HEAD deep links receive middleware-only anonymous 303 login redirects. Host rejection remains first; APIs/unknown/encoded aliases stay rejected, arbitrary queries are dropped and the anonymous resource allowlist is unchanged.
5. Protected legacy UI is now an inert bilingual migration notice; missing v2 builds show build/CLI guidance. Authenticated onboarding offers memory-only “browse for now” without accepting the MediaCrawler license.
6. Actual browser testing found and fixed Jobs stream-label reactivity and initial assets/contents loading after delayed authenticated mounting. Navigation queries are deduplicated and teardown cancels requests.

## Verification and corrections

[Verification](verification.md) records exact commands, attempts and limits. Full Python: 3155 passed / 22 skipped / one existing warning. Final Web: 114 tests, type check 0/0, format/build passed. A subsequent fixture-only correction passed four tests separately; it is not a new full-suite total.

Disposable browser checks covered deep-link login, a CSRF-protected account creation, refresh, asset/content loading, exact synthetic login image, image decoding, video loading/decoding, SSE connection, natural expiry, confirmed logout and another tab returning to login. A fresh origin proved browse-only deferral was not persisted.

Independent review fixed the container option-terminator preflight bypass, ambient database URL leakage in the fixture and malformed/stalled 401 handling. The archive fixture initially violated the existing read-only-file rule; fixing the fixture restored previews without weakening production security.

## Remaining and publication

No real platform credentials, license acceptance, platform/CDN request or media-server request was used. This completes the safe-console/local-startup increment, not 0055 or the product goal. Docker/Compose final-image UID and secret mounts, fresh/upgrade/restart/restore, real PostgreSQL, Bilibili/XHS canaries and Emby/Jellyfin playback remain unqualified.

Follow the [delivery priorities](../delivery-priorities.md): Linux deployment evidence, then authorized Bilibili video and XHS image/text canaries. Playback confirmation UI and evidence expansion stay behind these gates.

The implementation commit containing this record is the publication reference. Explicitly stage reviewed source/tests/Web/docs, push with the planning commit and reconcile the remote; exclude fixtures, build output, runtime data and secrets.
