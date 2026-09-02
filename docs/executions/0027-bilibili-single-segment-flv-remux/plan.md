**English** | [中文](plan.zh.md)

# Execution 0027 plan

- Status: Executed and verified
- Plan date: 2026-09-02
- Predecessor: `245e8e377761ee8343b33f581dfcd27295eac532`
- Database migration: None planned
- Plan commit: `ec7095a9cc5e85fda1aee66f256eb16345c1294a`
- Implementation commit: `7f99aa480328a25b7e9c2acc8a9c2234128e7b74`

## Baseline and audit

Execution 0026 is clean and reconciled at `245e8e3`. The strict v6 detail path accepts exactly one progressive `durl`, carries its primary/backups transiently and publishes the downloaded bytes directly after structural probing. `FFprobeMediaProbe` does not currently allowlist FLV, `ResolvedMediaTarget` has no format-aware progressive derivative, and `FFmpegStreamCopyMuxer` can mux DASH video plus optional external audio but cannot preserve optional audio from one mixed input. The CLI and pipeline already require launchable ffmpeg for Bilibili adapter-refresh VIDEO work, so no new operator capability switch is required.

The pinned MediaCrawler downloader chooses the largest `durl` entry and writes it as `.mp4` without format repair. The pinned bili-sync-up analyzer recognizes top-level formats containing `flv`, still selects only `durl[0]`, and uses ffmpeg remux for mixed FLV. Both checkouts are read-only design evidence; neither supports the multi-segment contract targeted later. Baseline gates are Execution 0026 focused `490 passed in 73.31s`, complete `1814 passed, 1 skipped in 342.33s`, closeout single-/multipart/DASH compositions `1.45s`/`1.70s`/`1.87s`, 120 Markdown files, two locked clean checkouts, 308 tracked files and zero untracked/runtime/upstream/dist tracked files.

## Delivery sequence

1. Add a repr-safe ephemeral FLV target wrapping one Bilibili-profile `ResolvedLocator`; extend the closed runtime union, refresh validation and exports without changing persistent locator v1.
2. Upgrade detail protocol to v7, classify only a closed top-level FLV format, and carry an exact private format marker through single-page and multipart payloads with collision detection and recursive stripping.
3. Extend normalizers and lazy refresh so legacy primary-only/primary-plus-backups progressive payloads remain ordinary while a valid FLV marker reconstructs the typed ephemeral target; schema drift fails closed.
4. Allowlist structurally probed FLV video, add fixed-argument single-input remux preserving video plus optional audio, and enforce input/output file identities, byte caps, timeout and bounded child output.
5. Add a generation-scoped FLV source store and typed downloader branch that reuses ordered candidate failover, strict resume and one all-auth refresh, probes the source, remuxes once, probes/publishes only the final and preserves safe recovery/cleanup behavior.
6. Add unit/contract coverage for format classification, private bridges, repr/non-retention, FLV probe/remux argv, candidate/auth behavior, failure retention, prepared-final recovery and backward compatibility.
7. Add a production ffmpeg/ffprobe SQLite → failed primary → backup FLV → remuxed MP4 → SHA-256 archive → Emby composition with zero-work replay; retain no signed URL, raw FLV publication or private marker.
8. Run focused and complete suites plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audits; update the four execution documents and root truth, then create bilingual implementation/closeout commits, push and reconcile GitHub.

## Planned commit sequence

1. Documentation baseline
2. Implementation
3. Documentation closeout

`.upstream` remains excluded, unmodified and clean.
