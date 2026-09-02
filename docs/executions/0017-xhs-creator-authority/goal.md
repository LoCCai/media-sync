**English** | [中文](goal.zh.md)

# Execution 0017 goal

- Status: Offline execution complete; live qualification remains `NOT_RUN`
- Date: 2026-09-01
- Predecessor: Execution 0016 closeout commit `4774c34`
- Plan commit: `9d19e7e`
- Implementation commit: `2f8dbaa`
- Scope: XHS creator-authority lookup for ordinary static IMAGE/GALLERY

## Outcome

Execution 0017 closes the missing automatic refresh path for an exact XHS author Subscription. Without an explicit note override, the runtime resolves only that Subscription's opaque `creator_input.secret_ref`, privately validates the signed creator URL and performs a bounded creator lookup. An operator-supplied `xhs_detail_reference_ref` remains the higher-priority compatibility override and prevents creator-secret resolution.

The frozen offline-qualified shape is one unique ordinary `type="normal"` XHS record with one or more ordered static images. It produces IMAGE/GALLERY content and ordered IMAGE Assets, then traverses exact provenance, `MediaRequestProfile.DEFAULT`, controlled image validation, immutable SHA-256 archive publication and idempotent Emby/Jellyfin poster/backdrop/gallery/NFO/source output.

## Delivered acceptance boundary

1. Parent context, request and child schema v3 accept exactly one XHS authority path: an exact note-detail URL or exact creator URL, never both. Host/path/identity and decoded, unique, bounded `xsec_token`/`xsec_source` values are revalidated at every boundary.
2. Creator fallback comes only from the exact Asset observation's Account/Subscription provenance. `subscription.max_items` must fit watchdog `max_output_items`; the child clears every creator/detail list, configures one XHS path, uses concurrency one and disables comment/media side effects.
3. Creator results require exactly one matching raw `type="normal"` IMAGE/GALLERY target with only IMAGE Assets. Duplicate targets, video/mixed/nonordinary records and identity/source-hint drift fail closed. Explicit detail mode retains historical compatibility without broadening this claim.
4. Pipeline/CLI preflight runs before child Job or Asset mutation. Valid VERIFIED replay resolves no secret; missing/damaged VERIFIED archive repair preflights before quarantine/reset. Only the dedicated authority-required error maps to the XHS prompt; other fixed causes/retryability remain distinct, and non-XHS CLI option use is rejected.
5. Durable XHS raw removes the known top-level authority fields and query-strips the pinned `note_url`/`image_list`/`video_url` fields while preserving accepted scalar/empty/container shapes. No database migration was added and neither pinned `.upstream` checkout was modified.

## Explicit exclusions

- Real QR/Cookie login, creator/feed/detail traffic, real XHS CDN bytes and real Emby/Jellyfin server scans/playback remain `NOT_RUN`; offline mocks do not imply them.
- Automatic XHS video, live photo, animation, mixed media, authority-expiry recovery, pagination hardening and cross-Asset refresh caching remain deferred.
- Remaining platform/media shapes stay outside this execution. Execution 0017 is complete, while the broader user goal remains active.
