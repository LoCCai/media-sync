**English** | [中文](plan.zh.md)

# Execution 0018 plan

- Status: Executed and closed offline
- Plan date: 2026-09-01
- Predecessor: Execution 0017 closeout commit `00add11`
- Plan commit: `c9d3586`
- Implementation commit: `356e254`
- Database migration: None

## Baseline

Before source edits, the seven-file gate passed `167 passed in 46.50s`: MediaCrawler detail-refresh contracts, Asset download orchestration, database ingestion, download runtime, pipeline runtime, the XHS creator-authority composition and refresh units. The branch was clean at `00add11`; local `main`, `origin/main` and GitHub were reconciled.

## Executed delivery sequence

1. **Freeze the upstream video shape**
   - Add one integration-owned XHS media-locator validator for ordinary HTTP/HTTPS `xhscdn.com` initial paths, excluding userinfo, mismatched/non-default ports, fragments and root paths while preserving transient signed queries. Normalize host case, IDNA and one trailing dot; allow explicit scheme-default ports.
   - Split the existing XHS creator target gate into static `type="normal"` IMAGE/GALLERY and playable `type="video"` VIDEO-or-MIXED branches. Before normalized Asset checks, strictly parse the locked upstream scalar raw fields: exactly one non-empty `video_url` and zero or one `image_list`, with no whitespace, empty segment, duplicate, invalid candidate or container drift. Then require a one-to-one mapping to exactly one position-zero VIDEO and at most one IMAGE.

2. **Preserve exact refresh behavior**
   - Reuse exact Account/Subscription provenance, creator-secret fallback, explicit note override, `max_items` watchdog projection and unique content/Asset selection. No new authority frame or migration is needed.
   - Validate the selected creator-fallback video URL again after normalization and before creating `ResolvedLocator`; return `MediaRequestProfile.DEFAULT`, matching the locked upstream's header-free media GET. Keep the historical explicit-note video path compatible and outside this new creator-video claim.
   - Retain field-specific XHS durable-raw cleanup for `note_url`, `image_list`, `video_url`, `xsec_token` and `xsec_source`; prove signed video queries do not persist.

3. **Prove process and refresh contracts**
   - Extend the real isolated fake-checkout creator contract with a video row and confirm bounded creator mode, exact URL selection, DEFAULT profile, cleanup and repr-safe authority handling.
   - Add unit matrices for video-only, optional-cover, malformed+valid and duplicate raw candidates, empty/whitespace segments, container drift, foreign/false-suffix/IPv6 hosts, case/trailing-dot/IDNA handling, default/custom ports, root path/fragment, duplicate matching rows and explicit note compatibility.

4. **Compose download, archive and Emby**
   - Add an offline end-to-end XHS creator-video test using exact SQLite provenance, a fake detail runner, mock DNS/HTTP, controlled MP4/PNG and a recording video probe; independently validate an embedded real H.264 MP4 through production `FFprobeMediaProbe`.
   - Assert immutable archive paths/checksums, Emby primary `.mp4`, optional poster/NFO/source output, generation stability and zero-work replay.

5. **Verify and close
   - Run focused pytest, Ruff check/format, strict mypy, complete pytest, compileall, upstream locks, build, documentation, retained-artifact and Git diff gates.
   - Update all four execution documents plus README, architecture, platform-capability and roadmap truth without promoting offline evidence to live qualification.
   - Create and push separate bilingual plan, implementation and closeout commits; reconcile local, tracking and GitHub SHAs after every push.

## Commit sequence

1. `c9d3586` — `docs: 启动小红书可播放视频闭环 / start XHS playable-video pipeline` — pushed
2. `356e254` — `feat: 闭环小红书可播放视频 / close XHS playable-video pipeline` — pushed
3. `docs: 收尾小红书可播放视频闭环 / close XHS playable-video pipeline` — ready to commit/push; its SHA cannot be self-referenced

`.upstream` remains excluded and both pinned checkouts remain clean.
