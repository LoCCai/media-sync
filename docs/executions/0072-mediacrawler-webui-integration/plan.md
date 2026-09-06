**English** | [中文](plan.zh.md)

# Plan

## 1. Freeze the pivot and ownership boundary

- Record execution 0071 as paused rather than complete. Preserve its evidence and unresolved findings, but stop widening custom child-output capture during execution 0072.
- Inventory the pinned MediaCrawler WebUI application, crawler API, WebSocket paths, singleton process manager, login modes, crawler modes, data views and media stores at the commit in `upstreams.lock.json`.
- Freeze the responsibility split: MediaCrawler owns WebUI/control/login/crawl/download; media-sync owns the authenticated shell, Subscription scheduling, task monitoring, completed-artifact ingestion and Emby/Jellyfin folders/NFO.
- Do not edit the locked checkout or duplicate its UI, process manager, login handlers, platform crawlers or media downloader in media-sync.

## 2. Establish one fixed upstream runtime

- Add typed configuration for the verified checkout and one dedicated virtual-environment Python. Validate absolute paths, checkout identity, lock commit, license acknowledgement and required entry points before exposing the integration.
- Add a deployment-level acknowledgement that defaults to false and accepts only the exact `true`/`false` tokens. Without explicit acknowledgement, do not import or construct the upstream application: every authenticated `/crawler` HTTP path, including `/crawler/api/crawler/start`, returns the same no-store `503 license_acknowledgement_required`. The resident supervisor keeps its independent explicit CLI gate.
- Launch the upstream API and crawler children through a media-sync-owned adapter that always selects the fixed interpreter and checkout working directory. Replace the upstream manager's ambient `uv run` assumption at the integration seam without modifying upstream files.
- Give startup, shutdown and child termination bounded behavior. A missing/mismatched checkout, interpreter or built WebUI fails with a fixed unavailable state and never falls back to another installation.
- Because a mounted FastAPI application's lifespan is not propagated by Starlette, expose one media-sync-owned asynchronous shutdown callback on the mounted application and await it from the root lifespan before disposing shared runtime state.
- Keep the upstream service private to the media-sync process/network boundary; `/crawler` is the supported entry, not a second unauthenticated listener.

## 3. Mount the authenticated `/crawler` surface

- Route the pinned WebUI, required API endpoints, static assets and WebSocket traffic through `/crawler`. Account for the upstream application's root-relative `/api`, `/assets`, `/logos` and `/static` assumptions using an external mount/proxy/base-path adapter rather than a source fork.
- Apply the existing media-sync operator authentication and request protections to the initial page and every HTTP/WebSocket control endpoint. Reject unauthenticated access before forwarding any crawler content or command.
- Preserve upstream start/stop/status and UI behavior behind the prefix. Media-sync may translate health/unavailable states but does not invent a second crawler state machine.
- Do not copy upstream free-form logs, command strings, Cookies or browser state into durable media-sync task/log records as part of this route slice.

## 4. Confine outputs and enable upstream media

- Allocate one managed output root for the integration and derive per-task locations beneath it. Reject traversal, symlink escape, checkout-relative output and arbitrary paths received from browser requests.
- Use a media-sync-owned bootstrap/adapter to pass the exact output location supported by upstream `SAVE_DATA_PATH` while leaving the pinned source tree clean.
- Explicitly set the pinned, misspelled `ENABLE_GET_MEIDAS=True` switch for crawler children so MediaCrawler performs its existing image/video downloads. Test the applied child configuration; a UI checkbox or save-format choice alone is not evidence that media download is enabled.
- Keep task output, browser profile state and media-sync library output as distinct roots. A crawler completion does not authorize reading outside its assigned output directory.

## 5. Keep media-sync's integration work thin

- Retain durable Subscription scheduling in media-sync and map each dispatched run to one monitored upstream task/output root. Serialize or reject starts according to the upstream manager's actual single-process capacity rather than pretending it supports parallel work.
- Observe upstream start, running, stop and terminal states with bounded polling/reconciliation. Monitoring records closed local state; it does not persist arbitrary upstream log text as authority.
- After a successful terminal state, ingest only recognized completed artifacts from the assigned root through bounded, defensive parsers. Failed or partial runs remain distinguishable and are not published as complete media.
- Feed accepted artifacts into the existing deterministic Emby/Jellyfin folder and NFO boundary. Filesystem/NFO publication must remain useful without an active media-server connection; do not make server credentials or a successful scan a prerequisite.

## 6. Deliver the first slice before later integration

- First implement only: authenticated `/crawler` routing, upstream prefix/static/WebSocket reachability, fixed virtual-environment/checkout selection, managed output-root injection, `ENABLE_GET_MEIDAS=True`, the minimal QR relay, bounded lifecycle, and focused configuration/route/relay tests.
- Use fake ASGI/upstream processes and temporary roots to prove authentication, forwarding, command/runtime selection, confinement and media-switch application without opening a browser or contacting a platform/CDN.
- Add source/contract assertions that the checkout remains unchanged and the adapter does not choose ambient `uv`/Python. Verify unavailable runtime and child-start failure produce fixed safe outcomes.
- Do not mark Subscription-to-ingestion-to-NFO end to end complete until later slices implement and test those seams.

## 7. Deliver the minimal QR relay and qualify honestly

- Document and test the current limitation: QR selection reaches upstream login code whose native display path calls `PIL.Image.show()`; it does not make QR bytes available to the browser UI.
- At the media-sync-owned bootstrap seam, intercept only upstream `show_qrcode`; keep the upstream login state machine unchanged. Validate and bound one QR image, then atomically write it to an attempt-scoped temporary location outside the checkout.
- Add an authenticated task/attempt-bound endpoint that returns only the current QR image with `Cache-Control: no-store`, rejects absent/stale/mismatched attempts, and deletes the exact temporary file on replacement, completion, expiry, cancellation and shutdown.
- Add the smallest integration view to the mounted upstream React UI so the initiating operator can see the relayed image. Do not add a parallel login form or expose a public/static QR URL.
- Test the hook, bounds, authentication, no-store response, attempt isolation, UI state and cleanup with synthetic PNG bytes. These tests prove the relay implementation, not a real platform scan.
- Run focused Python/Web route and configuration tests, formatting/type/lint checks and `git diff --check`; record exact commands only after they run.
- Keep live QR, Cookie, seven-platform crawl/download, CDN bytes and Emby/Jellyfin server scan/playback as `NOT_RUN` until separately authorized and observed. A passing mock WebUI test is implementation evidence only.
