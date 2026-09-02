**English** | [中文](goal.zh.md)

# Execution 0015 goal

- Status: Offline frozen slice complete; every live qualification row remains `NOT_RUN`
- Started: 2026-08-31 07:24 +08:00
- Completed: 2026-08-31
- Predecessor: Execution 0014 closeout commit `6098923`
- Plan commit: `76b1973`
- Implementation commit: `95d314d`

## Outcome

Close one ordinary Douyin single-video path with platform-specific offline evidence. Given one trusted Subscription and one normalized record with a numeric `aweme_id`, an empty `note_download_url`, exactly one valid `video_download_url`, no music Asset and an optional cover, prove pure-ID detail, exact Account/Subscription-bound refresh, deterministic download and mandatory probing, immutable archive publication and Emby/Jellyfin primary `.mp4` plus poster/metadata output.

This execution qualifies the already composed single-video primitives and fixes only defects exposed by its contracts. It does not claim galleries, associated music as an external audio track, bounded creator pagination, real CDN compatibility or a special Douyin request profile.

## Design basis

- The pinned Douyin helper accepts a pure numeric ID; detail mode writes it to `DY_SPECIFIED_ID_LIST`, fetches one aweme and persists `aweme_id`, `video_download_url`, `cover_url`, `music_download_url` and comma-joined `note_download_url`.
- media-sync already maps a non-gallery record to video/audio/cover Assets, stores stable `mediacrawler` refresh locators and exact AssetRefreshSource provenance, and selects detail candidates by content ID, remote ID, kind, position and query-free source hint. The default HTTP profile, mandatory probe, SHA-256 archive and Emby primary-media layout are platform-neutral.
- The product gap closed by this execution was that, unlike Kuaishou, Douyin media fields were not structurally query-free before normalized raw was retained. Unknown query-key values, URL userinfo, fragments or drifted nested objects could therefore outlive the transient boundary. `note_download_url` now follows the normalizer's comma-list semantics rather than treating the whole joined string as one URL.

## Acceptance

1. **Closed ordinary-video shape** — a numeric `aweme_id`, empty image-list field and exactly one valid video URL emit one position-zero video Asset; an optional valid cover emits one position-zero cover. Music is empty in the accepted fixture. Remote IDs, positions, MIME/source hints and stable locators are exact.
2. **Durable media-URL boundary** — `video_download_url`, `cover_url`, `music_download_url` and every comma-separated `note_download_url` item retain only canonical origin/path in durable raw. A comma-joined note scalar becomes an ordered flat sequence; rejected opaque children become `null` slots rather than preserving nested data. Userinfo, all query values and fragments are removed. Accepted in-memory discovery/detail Assets retain their complete transient URLs.
3. **Pinned pure-ID detail** — the real isolated fake checkout proves `platform=dy`, numeric `DY_SPECIFIED_ID_LIST`, detail/JSONL/media-off/concurrency switches, bounded child framing, repr safety, saved-profile shape and normal-success attempt cleanup.
4. **Exact provenance and refresh** — lazy runtime construction binds the exact eligible AssetRefreshSource, Account and Subscription. Only the exact content/remote ID/kind/position/query-free source hint candidate is accepted; missing, drifted, duplicate or wrong-Subscription cases fail before media transfer.
5. **Default HTTP and playable publication** — video and cover resolve with `MediaRequestProfile.DEFAULT`; the media HTTP requests send no Cookie, Authorization, Referer, Origin or caller-controlled header. Deterministic MP4/PNG bytes pass mock public-DNS pinning and bounds, video receives controlled mandatory probing, both Assets finalize under SHA-256 archive paths, and the local Emby layout contains primary `.mp4`, optional poster, NFO and allowlisted source metadata.
6. **Replay and closed sinks** — query-only forward URL rotation preserves identity, generation and verified bytes. In the composed E2E, replay is `already_verified`/`already_exported` with no second fake detail runner, HTTP, DNS or probe. Dynamic sentinels are absent from ORM, disposed SQLite/sidecars, runtime/work/archive/library, representations and Git-visible retained files.
7. **Truthful qualification** — the focused gate passes 231 tests, and the final complete suite passes 1209 tests with one Windows-inapplicable skip. No coverage run is claimed. Real login/session, creator scan, detail/CDN, platform bytes and Emby/Jellyfin server rows remain `NOT_RUN`.

## Known identity and cleanup limitations

The durable identity is `<aweme_id>:<kind>:0` plus a query-free source hint. Same-ID/same-origin/path byte replacement with only query rotation cannot invalidate already-verified bytes automatically; CDN host/path movement may reset generation or fail exact refresh. Detail output also inherits trusted Subscription ownership rather than independently proving the aweme still belongs to that author.

Normal-success detail cleanup is in scope. Injected filesystem cleanup failure still lacks the scheduled runner's full quarantine/incident/account-block protocol and is not claimed as zero retention.

## Explicit exclusions

- Douyin galleries/images, associated music/audio semantics, multiple video or cover URLs, slideshows, subtitles, comments, live/paid/restricted/deleted content and trustworthy creator profiles.
- Bounded creator pagination; the pinned creator client walks until `has_more != 1`, so current use still requires `allow_full_history` and outer watchdogs.
- Any unproven platform-specific CDN header and every live qualification row.
