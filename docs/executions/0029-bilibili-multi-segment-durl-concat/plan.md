**English** | [中文](plan.zh.md)

# Execution 0029 plan

- Status: Executed and verified
- Plan date: 2026-09-02
- Predecessor: `2621f6a119aac60eaf89f0195d4fbe23bd5160f0`
- Database migration: None planned
- Plan commit: recorded in the closeout index; never embedded in this file
- Implementation commit: recorded in the closeout index; never embedded in this file

## Baseline and audit

Execution 0028 is clean and reconciled at `2621f6a`; its deferred Python re-verification (`uv run python scripts/check_docs.py`, 256 Markdown files) and the Ruff/upstream/Bilibili composition baseline all pass on this workstation before any 0029 change. The strict v7 detail path accepts exactly one progressive `durl`; `len(durl) != 1` closes as unsupported. `ResolvedMediaTarget` has no multi-segment variant, `_PartStore` roles cannot express per-segment state, and `FFmpegStreamCopyMuxer` can mux two inputs or remux one input but cannot concatenate an ordered segment tuple.

The pinned MediaCrawler downloader still selects one `durl` entry and writes it as `.mp4`; the pinned bili-sync-up analyzer selects `durl[0]` only. Both checkouts stay read-only design evidence. Baseline gates recorded before implementation: Bilibili composition `4 passed in 6.95s`, `ruff check` and `ruff format --check` clean, `check_docs.py` (256 files) and `check_upstreams.py` (2 locked checkouts) pass.

## Delivery sequence

1. Add a repr-safe ephemeral `ResolvedSegmentsLocator` holding 2–64 ordered, pairwise-distinct Bilibili-profile segment locators; extend the closed runtime union, exports and lazy-refresh validation without changing persistent locator v1.
2. Upgrade the detail protocol to v8: accept the bounded ordered `durl` tuple, validate each segment's primary/backups, keep DASH precedence, keep exactly-one-segment behavior identical, and close multi-segment FLV as unsupported.
3. Bridge the multi-segment target through one new private field shaped `{"cid", "segments": [{"url", "backup_urls"}...]}` with strict collision detection against every existing private field, recursive stripping before persistence, and reconstruction that fails closed on drift; require the payload CID to match the selected page.
4. Extend `_PartStore` with bounded per-segment roles, add the concat list file as confined attempt-local state, and extend cleanup to discard every segment store plus the list file.
5. Add the typed downloader branch: per-segment ordered download under one shared byte cap and deadline, per-segment exactly-MP4 structural probing, one all-auth refresh that must return the same segment count (drift fails closed), one fixed concat-demuxer `ffmpeg -c copy` invocation, exact-MP4 final gate, immutable archive publication, prepared-final recovery and safe failure retention.
6. Add unit/contract coverage for locator validation, protocol v8 parsing, bridge collisions/stripping, refresh reconstruction, concat argv/list escaping/identity/failure behavior, per-segment failover/auth/budget/probe semantics, failure retention, recovery, cleanup and backward compatibility.
7. Add a production ffmpeg/ffprobe SQLite → failed primary → backup → two-segment concat → SHA-256 archive → Emby composition with zero-work replay; retain no signed URL, raw segment or private marker.
8. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits; update the four execution documents and root truth, then create bilingual implementation/closeout commits.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
