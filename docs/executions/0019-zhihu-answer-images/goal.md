**English** | [中文](goal.zh.md)

# Execution 0019 goal

- Status: Frozen offline slice delivered; live qualification `NOT_RUN`; broader seven-platform goal active
- Date: 2026-09-02
- Predecessor: `4fb639a`
- Plan commit: `dc1714c`
- Implementation commit: `2edb9d763b4948c56cc182bcc5012914bcb644d1`

## Objective

Add the first downloadable Zhihu media slice without editing the locked MediaCrawler checkout: subscribe to a creator with a successful Subscription-`max_items` bound, capture exactly one static-image candidate from an ordinary answer, normalize it as an ARTICLE-owned IMAGE, refresh it from durable non-secret authority, download it through the production safety boundary, and publish deterministic Emby/Jellyfin-compatible output.

## Frozen acceptance boundary

1. The locked upstream answer request includes raw `content` HTML, but the extractor/update/JSONL path discards downloadable attributes. A source-bound contract executes that real loss boundary at MediaCrawler SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`; `.upstream` remains unmodified and untracked.
2. Only an ordinary creator answer with exactly one managed image is claimed. Attribute priority is `data-original` → `data-actualsrc` → `src`; duplicate/competing lazy or `srcset` candidates, multiple images, player/video/container drift, malformed IDs and unsupported URLs fail closed. Canonical answer URLs reject query/fragment delimiters; image URLs require bounded HTTPS `zhimg.com` authority, a static extension and no empty query or fragment delimiter.
3. The verified-checkout shim binds capture to the exact returned Pydantic object and uses `ContextVar` only inside nested storage, so extraction in `asyncio.gather` children survives parent-task storage without leaking into peers. Scheduled creator execution passes `max_items=23` as two API requests and two callback invocations with page sizes `20 + 3`, exactly 23 callback-processed rows and one between-page pacing sleep; there is no third request or post-cap sleep. Short non-terminal and repeated pages fail closed. Zhihu is therefore removed from `FULL_HISTORY_PLATFORMS`.
4. Normalization retains `ContentKind.ARTICLE` and creates exactly one position-zero IMAGE with remote ID `<content_id>:image:0`. The private capture field and transient query authority are removed from normalized raw data, SQLite and retained artifacts.
5. Lazy refresh derives the only allowed detail authority from the persisted canonical answer URL, independently revalidates refresh/parent/child boundaries, requires one exact ARTICLE/IMAGE/source-hint match, and returns `MediaRequestProfile.DEFAULT` without account Cookie, Authorization, Referer or Origin.
6. Zhihu IMAGE downloads automatically require bounded static structural qualification. Structurally qualified JPEG, PNG and WebP fixtures pass; GIF, APNG, animated WebP and AVIF fixtures fail. This is a bounded container/structure gate, not a complete pixel decoder. Normal, recovery and takeover preparation preserve the requirement.
7. The isolated composition traverses exact SQLite provenance, fake detail, mock public DNS/HTTP, production byte qualification, SHA-256 archive and Emby poster/backdrop/gallery/body/NFO/source publication. Query-only replay adds zero work, and retained SQLite/runtime/archive/export/WAL/SHM artifacts contain neither private capture data nor transient query values.
8. The expanded focused gate, complete suite, Ruff, format, strict mypy, compileall, upstream locks, build, documentation, retained-artifact audit and independent review must pass before closeout. Live Zhihu login/creator/detail/CDN and real Emby/Jellyfin qualification remain explicitly `NOT_RUN`.

## Deferred scope

Multiple-answer images/gallery, Zhihu articles, zvideo playback/covers, real redacted fixtures and live qualification remain deferred or `NOT_RUN`. Tieba still has no qualified downloadable media slice, so the larger seven-platform goal remains active.
