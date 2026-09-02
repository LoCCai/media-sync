**English** | [中文](progress.zh.md)

# Execution 0032 progress

- Status: Frozen offline bounded Douyin note-gallery scope implemented and gated; live rows remain `NOT_RUN`
- Date: 2026-09-02
- Plan commit: `286dac9` (documentation baseline)

## Delivered

1. A strict `_dy_note_images` parser freezes the pinned comma-joined `note_download_url` shape: string or JSON-frozen sequence input, per-item string/no-embedded-comma/valid-URL checks, closed duplicate handling and the 1–64 bound; drift raises `RecordNormalizationError` instead of silently dropping items, while empty or absent fields stay empty.
2. `_normalize_dy` now materializes `ContentKind.IMAGE` (one image) or `ContentKind.GALLERY` (2–64) with ordered `{aweme_id}:image:0..N-1` IMAGE assets; the video/music/cover fields keep the established tolerant parsing and the pinned crawler's image-over-video choice unchanged, so the 0015 single-video/audio/text shapes stay byte-compatible.
3. The existing per-asset adapter refresh is qualified for gallery positions: one exact numeric-ID detail run re-resolves each position's current signed URL in memory and path drift closes as `locator_refresh_asset_mismatch`.
4. Coverage: ingestion-contract materialization for 1/2/64 images, the 65-image bound and per-item drift; refresh coverage for both positions and path drift; one production SQLite → detail refresh → mock DNS/HTTP → static PNG sniff gate → SHA-256 archive → Emby poster/backdrop/gallery/NFO composition with zero-work replay.
5. Durable state keeps only query-free hints; the detail signature, its sentinel and both signed URLs appear nowhere in retained runtime/work/archive/export/library trees or SQLite artifacts.

## Verification snapshot

See [`verification.md`](verification.md) for the exact commands, exit codes and gate outputs.

## Not done

Video+image mixed Asset semantics, associated music for galleries, animated drift beyond the static gate, same-ID byte replacement, bounded creator pagination, dedicated CDN headers, cleanup-failure quarantine and every live qualification row remain deferred or `NOT_RUN`.
