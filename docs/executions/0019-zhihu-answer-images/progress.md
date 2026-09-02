**English** | [中文](progress.zh.md)

# Execution 0019 progress

- Status: Frozen offline Zhihu answer-image slice and documentation closeout complete
- Last updated: 2026-09-02
- Predecessor: `4fb639a`
- Plan commit: `dc1714c`
- Implementation commit: `2edb9d763b4948c56cc182bcc5012914bcb644d1`

## Completed

- [x] Audited and source-bound the pinned MediaCrawler Zhihu answer request, real extractor/update/JSONL loss boundary, answers-only creator dispatch and missing native cap at SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`; no upstream file was edited.
- [x] Implemented the frozen `data-original` → `data-actualsrc` → `src` one-image parser and strict canonical answer/`zhimg.com` URL gates. Duplicate/competing lazy or `srcset` attributes, multiple images, media-container drift, empty delimiters and unsupported URLs fail closed.
- [x] Fixed the review-discovered P1 by binding capture to the exact returned object and using `ContextVar` only inside nested storage. The gather-child → parent-store regression and real locked Pydantic carry/consume/non-serialization contract pass.
- [x] Bounded scheduled creator execution by Subscription `max_items`. The end-to-end child proof turns 23 into two API requests and two callback invocations with page sizes `20 + 3`, exactly 23 callback-processed rows and one between-page pacing sleep; there is no third request or post-cap sleep. Short non-terminal, repeated, malformed and extractor-drift pages fail closed. Zhihu no longer requires full-history acknowledgement.
- [x] Normalized ARTICLE plus one position-zero `<content_id>:image:0` IMAGE, removed private/transient authority from durable state, and implemented exact canonical-answer detail refresh with credential-free `MediaRequestProfile.DEFAULT`.
- [x] Added automatic bounded static structural qualification for Zhihu IMAGE downloads. Qualified JPEG/PNG/WebP pass; GIF/APNG/animated WebP/AVIF fail; normal, recovery and takeover preparation preserve the flag. This is structural qualification, not complete pixel decoding.
- [x] Passed the SQLite → fake detail → mock public DNS/HTTP → production byte gate → SHA-256 archive → Emby poster/backdrop/gallery/body/NFO/source composition, zero-work query replay and retained SQLite/runtime/archive/export/WAL/SHM audit.
- [x] Passed the final 505-test focused gate, complete suite (`1543 passed, 1 skipped`), Ruff, format, strict mypy, compileall, upstream locks, build, docs, diff/retained-artifact audit and a fresh independent 461-test review with no P0/P1/P2.
- [x] Created and pushed bilingual implementation commit `2edb9d763b4948c56cc182bcc5012914bcb644d1`; local `main`, `origin/main` and GitHub were reconciled.

## Documentation closeout

- [x] The commit containing this record is the bilingual documentation closeout. Its self-referential SHA is intentionally not embedded; post-push local/tracking/GitHub reconciliation is reported in the task handoff.

## Deferred product scope

Multiple-answer images/gallery, Zhihu articles, zvideo playback/covers, real redacted fixtures and live login/creator/detail/CDN/Emby qualification remain deferred or `NOT_RUN`. Tieba downloadable media and complete seven-platform coverage remain active work.
