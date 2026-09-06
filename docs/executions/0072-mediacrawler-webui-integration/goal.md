**English** | [中文](goal.zh.md)

# Goal: authenticated integration of the pinned MediaCrawler WebUI

Execution 0072 changes the delivery order. It pauses execution 0071's expansion of custom runner-output diagnostics and instead integrates the already pinned MediaCrawler WebUI as the operator-facing crawler surface. This is a priority change, not completion of 0071: no missing diagnostic coverage, old discarded output or previously unverified platform behavior is reclassified as solved.

Reuse the locked upstream WebUI, crawler control, login, crawl and media-download flows directly. Do not reproduce those features in a second media-sync UI or maintain a fork of the locked checkout. In this integration, media-sync is deliberately thin: it supplies the authenticated shell, Subscription scheduling, task monitoring, controlled artifact ingestion, and deterministic Emby/Jellyfin folders and NFO files. MediaCrawler continues to own the interactive crawler operation and the network transfer of upstream media.

The first delivery slice is intentionally smaller than the complete integration. It establishes the authenticated `/crawler` route, a fixed verified MediaCrawler virtual environment, one confined output root, the upstream media-download switch, a minimal browser QR relay and focused offline tests. Later slices may connect scheduled runs, completion ingestion and library publication through those frozen seams without reopening the 0071 logging expansion.

## Delivery boundary

| Capability | First slice | Later evidence required |
| --- | --- | --- |
| Authenticated `/crawler` UI/API/WebSocket route | Implement and test offline | Live browser use remains unqualified |
| Fixed venv, pinned checkout, output root, `ENABLE_GET_MEIDAS` | Implement and test offline | Real child/platform behavior remains unqualified |
| Subscription dispatch, task reconciliation and completed-output ingestion | Freeze seams only | Implement and test in a later 0072 slice |
| Emby/Jellyfin folders and NFO | Preserve as media-sync responsibility | Prove from ingested artifacts later; no server required |
| Browser-visible QR relay | Implement and test with synthetic bytes in the first slice | Real scanning/login remains `NOT_RUN` |
| Real Cookie/QR login and seven-platform crawl/download | Not in the first slice | Separately authorize and record; current state is `NOT_RUN` |
| Emby/Jellyfin server scan/playback | Optional, not required | Run only when a service is available; current state is `NOT_RUN` |

## Acceptance criteria

1. **Status is truthful** — mark execution 0071 as paused in delivery ordering; do not describe its partial diagnostic work as complete, deployed or validated. Execution 0072 neither reconstructs discarded logs nor fixes a platform merely by changing the integration surface.
2. **The upstream remains pinned** — run the commit and license recorded in `upstreams.lock.json` without editing files inside the locked MediaCrawler checkout. Use one configured virtual-environment Python and the verified checkout as the runtime source; never fall back to ambient `python`, `uv`, `PATH` packages or an unverified clone.
3. **One authenticated crawler surface** — expose the upstream WebUI and its required HTTP/API/WebSocket control paths under media-sync's `/crawler` boundary. Every crawler page and control request passes media-sync operator authentication; an unauthenticated user cannot reach an alternate upstream port or bypass route. Prefix, static-asset and WebSocket behavior is tested without rebuilding the WebUI as a media-sync feature.
4. **Responsibilities stay narrow** — MediaCrawler owns interactive configuration, login, start/stop/status, crawling and upstream media download. Media-sync owns only authentication, durable Subscription scheduling, task observation, ingestion from the assigned output root, and Emby/Jellyfin-compatible folder/NFO publication. It does not add a parallel login form, crawler engine or second downloader in this execution.
5. **Output and media settings are controlled** — each launched crawler uses the configured managed output root rather than the checkout, current working directory or an operator-supplied arbitrary path. The integration explicitly enables the pinned upstream's media switch, spelled `ENABLE_GET_MEIDAS`, and supplies the output path through a media-sync-owned bootstrap or adapter without changing upstream source files.
6. **Artifacts cross one bounded seam** — media-sync reads only completed output beneath the assigned root, treats it as untrusted input, and associates ingestion with the scheduling/monitoring task that owns that root. Upstream logs, browser state and arbitrary files are not imported as durable media-sync records merely because the WebUI can display them.
7. **The first slice stays minimal** — its required implementation evidence covers `/crawler` authentication and route/prefix behavior, fixed interpreter and checkout selection, output-root confinement, `ENABLE_GET_MEIDAS=True`, the bounded QR relay, and unchanged failure behavior when the upstream runtime is absent. Tests are deterministic and do not contact a platform or CDN.
8. **The QR gap is closed narrowly** — the pinned native path ends in `PIL.Image.show()`. Without changing upstream login semantics, the first slice intercepts `show_qrcode`, writes one bounded image to an attempt-scoped controlled temporary file, serves it only from an authenticated `Cache-Control: no-store` endpoint, and renders it in the upstream React UI. Completion, expiry, cancellation and replacement remove the exact temporary image. Offline relay evidence does not qualify real browser scanning or login.
9. **A media server is optional** — generating and verifying Emby/Jellyfin-compatible folders and NFO files must not require an Emby or Jellyfin connection. Server configuration, scanning and playback may be exercised only when separately available and authorized.
10. **No live-platform qualification is implied** — offline route/runtime tests do not prove QR login, Cookie acceptance, real crawl/download behavior or seven-platform compatibility. Every real account, seven-platform, CDN and Emby/Jellyfin server row remains `NOT_RUN` until it is actually executed and recorded.

## Deferred but unchanged

- Connect durable Subscription dispatch, task reconciliation, completed-output ingestion and folder/NFO publication incrementally after the runtime seam is proven. The first route/configuration slice does not claim this end-to-end flow already works.
- Revisit execution 0071 only by an explicit later decision. Its remaining safe-diagnostic work is paused, not silently discarded or counted as acceptance for 0072.
- Live login, live crawling, real media downloads and real media-server scan/playback require separate authorization and evidence.
