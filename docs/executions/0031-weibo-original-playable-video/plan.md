**English** | [中文](plan.zh.md)

# Execution 0031 plan

- Status: Executed and verified
- Plan date: 2026-09-02
- Predecessor: `e242b16097b2fb1f0f6ee1dc8e863ace1c68ab32`
- Database migration: None planned
- Plan commit: `1c79c6d94fbca2ac4c01ec1f9c2f6e17da7b6e7d`
- Implementation commit: `666438d793c18f97af5026e7506c8ee9745eba47`

## Baseline and audit

Execution 0030 is clean, pushed and reconciled at `e242b16`. The pinned Weibo store's `update_weibo_note` retains only text/metrics and discards `page_info`, so ordinary original video locators disappear at the store boundary exactly like `pics` did before 0016. The 0016 shim installs at that boundary in both the scheduled and detail children, `_normalize_wb` already fails closed on a retained `page_info`, WB numeric-note detail references are already validated end to end, and the generic adapter refresh already returns DEFAULT-profile locators from a fresh detail record while persistence keeps query-free hints. `FFprobeMediaProbe` already maps MP4 video, and the downloader/Emby paths are platform-neutral for VIDEO assets.

Baseline gates recorded before implementation: 0030 focused regression `460 passed in 91.95s`, complete `1916 passed, 1 skipped in 446.64s`, Ruff/format clean, strict mypy clean, docs (272 files) and upstreams (2 locked checkouts) passing.

## Delivery sequence

1. Add the closed Weibo video URL validator and one `_capture_video` pass over the exact-object store boundary; carry the result under one new private field with strict collision checks against the images field.
2. Extend `_normalize_wb` with the frozen VIDEO branch (exact `{"url"}` payload, numeric ID, no retweet, no image-field co-presence) and add the field to the recursive private-field strip set.
3. Add `AssetKind.VIDEO` to the WB refresh support set so the existing generic refresh path binds the exact asset, re-captures the current signed URL in memory and returns the DEFAULT-profile ephemeral locator.
4. Add unit/contract coverage for the validator, shim capture matrix (retweet/page-type/media-info shape/malformed URL/dual-field), normalizer fail-closed outcomes, real-child refresh compositions and durable non-retention.
5. Add one production ffprobe SQLite → detail refresh → mock DNS/HTTP → SHA-256 archive → Emby `.mp4`/NFO/source composition with zero-work replay.
6. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits; update the four execution documents and root truth, then create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
