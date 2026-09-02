**English** | [中文](progress.zh.md)

# Execution 0018 progress

- Status: Offline implementation and documentation closeout complete
- Last updated: 2026-09-01
- Plan commit: `c9d3586` (pushed to `origin/main`
- Implementation commit: `356e254` (pushed to `origin/main`

## Implemented

- [x] Source-bound contract executes the locked XHS store functions and proves `origin_video_key`, `originVideoKey`, H.264 `master_url`, comma-scalar `video_url` and scalar artwork output.
- [x] Strict initial XHS media-locator validation for HTTP/HTTPS `xhscdn.com` roots/subdomains, normalized case/IDNA/trailing dot, default ports and non-root paths; userinfo, whitespace/control bytes, fragments, malformed labels and foreign/custom-port destinations fail closed.
- [x] Automatic creator fallback now accepts one ordinary raw `type="video"` row with exactly one scalar VIDEO candidate and zero or one scalar IMAGE candidate, mapped one-to-one to VIDEO or narrow MIXED content.
- [x] Multiple, duplicate, empty, whitespace, malformed+valid and container-drift candidates fail before normalized Asset selection; the historical explicit exact-note video path remains compatible and outside the new automatic claim.
- [x] A real isolated fake checkout proves bounded creator configuration, exact URL selection, `MediaRequestProfile.DEFAULT`, cleanup and repr-safe authority handling.
- [x] Full SQLite provenance → creator lookup → mock DNS/HTTP → archive → Emby composition publishes playable `.mp4`, optional poster, NFO and source output; query-only replay performs zero additional detail, DNS, HTTP, probe, archive or export work.
- [x] An embedded real H.264 MP4 passes production `FFprobeMediaProbe`; the deterministic composition retains a recording probe for exact call-count assertions.
- [x] Durable XHS raw and Asset hints remain query/userinfo/fragment-free, completed attempt roots are removed, and neither pinned `.upstream` checkout is modified or tracked.

## Verification completed

- Pre-edit baseline: `167 passed in 46.50s`; focused nine-file gate: `222 passed in 43.69s`.
- Locked upstream source contract: `4 passed`; real H.264/upstream/composition check: `6 passed in 8.84s`.
- Complete suite: `1353 passed, 1 skipped in 338.48s`; only skip is the Windows-inapplicable POSIX mode-bit test.
- Ruff check and format PASS (`241 files already formatted`); strict mypy passes `80 source files`; compileall, two upstream locks, wheel/sdist build, docs, diff and retained-artifact audits PASS.
- Independent final review found no P0–P2 findings. No coverage run is claimed.

## Remaining

- [ ] Main thread: create/push the bilingual closeout commit and reconcile local/tracking/GitHub SHAs; the post-edit documentation/diff checks are rerun immediately before commit.
- [ ] Real XHS QR/Cookie login, creator/feed/detail traffic, real CDN video/artwork bytes and Emby/Jellyfin server scan/playback remain `NOT_RUN`.
- [ ] Multi-video, multi-image, broader mixed-media, live-photo, animation, authority-expiry recovery, Tieba/Zhihu media shims and the remaining seven-platform shapes remain future work.

Execution 0018 is complete at its offline boundary; the broader user goal remains active.
