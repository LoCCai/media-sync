**English** | [中文](upstream-replication-review.zh.md)

# Upstream replication completion review (archive, execution 0042)

The original plan: replicate MediaCrawler's platform crawling and bili-sync-up's archiving/Emby/web workflow as one self-hosted service, combining both behind media-sync's own license-safe boundaries. This document archives, capability by capability, what is delivered (with the execution record that proves it), what is explicitly deferred, and what stays `NOT_RUN` until the operator-assisted qualification (execution 0047). Status boundary: execution 0041 on `main`.

## 1. Versus MediaCrawler (crawling side)

| Capability | Status | Evidence |
| --- | --- | --- |
| Seven-platform account model (`xhs`/`dy`/`ks`/`bili`/`wb`/`tieba`/`zhihu`) | Delivered | Execution 0003 schema; 0004 bridge |
| QR / Cookie / saved-session login with fenced state machine | Delivered (offline scope) | Executions 0011, 0012; live rows `NOT_RUN` → 0047 |
| Creator-subscription crawling (creator mode) with license-gated external process | Delivered (offline scope) | Executions 0004, 0007, 0008 |
| Creator authority resolution (secret-ref, bounded lookup) | Delivered (offline scope) | Executions 0017, 0019, 0020 |
| Content discovery per platform | Delivered for 15+ frozen shapes across all seven platforms | Executions 0013–0024, 0031–0039 |
| Incremental state (cursor + watermark + known IDs) | Delivered — exceeds upstream (upstream has none) | Architecture §5; execution 0003 |
| Process isolation, secret references, redaction | Delivered — exceeds upstream (upstream passes cookies on argv) | Execution 0004; ADR-0001 |
| Comments collection | Explicit non-goal (SAFE-002 default-off) | Requirements §0.x non-goals |
| Keyword/search crawling | Explicit non-goal (subscription-only product) | Requirements §0.x non-goals |
| Phone-number login | Not exposed (upstream enum broader than reality) | Execution 0012 truth boundary |
| Live login/crawl qualification | `NOT_RUN` — operator, execution 0047 | Roadmap Phase 5 |

## 2. Versus bili-sync-up (archiving / Emby / web side)

| Capability | Status | Evidence |
| --- | --- | --- |
| Persistent resumable downloads (`.part`, Range resume, restart fencing) | Delivered — exceeds upstream (atomic, checksummed) | Executions 0005, 0025–0026 |
| Bilibili DASH selection + stream-copy mux | Delivered | Execution 0024 |
| Multi-segment `durl` concat / multi-part FLV | Delivered | Executions 0029, 0030 |
| CDN backup failover (ordered, bounded) | Delivered for DASH + progressive + FLV | Executions 0025, 0026, 0027 |
| Deterministic SHA-256 archive | Delivered | Execution 0005 |
| Emby/Jellyfin NFO library (tvshow/season/episode, posters, galleries) | Delivered (layout v1) | Executions 0005, 0016 |
| Danmaku (ASS) / subtitle sidecars | Deferred → execution 0043 | Roadmap Phase 3 deferred rows |
| Scheduled automatic sync → download → export | Delivered (durable scheduler + resident supervisor) | Executions 0006, 0010, 0012 |
| Web administration | Partial: local REST API + Chinese console delivered | Execution 0040; hardening → 0044 |
| Task-queue visibility in the UI | Partial (jobs + operations endpoints) → 0044 | Execution 0040 |
| Credential/config management UI | Not built (secret refs stay CLI/secret-store managed) | Deliberate boundary |
| Bangumi/anime, multi-user, public deployment | Explicit non-goals | Requirements §0.x non-goals |

## 3. Cross-cutting delivery beyond both upstreams

- Documentation audit trail: 47 executions with four-file bilingual records, truth rules enforced (`NOT_RUN` never masquerades as pass).
- Local REST API + embedded web console with QR relay (execution 0040); Docker packaging with pinned upstream, mirrors and Xvfb (execution 0041) — operator verification happens on Linux, not here.
- Bounded quality gates: strict mypy, Ruff/format, compileall, docs-link checks; complete offline suite last recorded at 2032 passed + 1 Windows-inapplicable skip (execution 0039 baseline) — newer tests (0039–0040) run on the deployment host.

## 4. Remaining sequence to the final gate

| Execution | Scope | Verification model |
| --- | --- | --- |
| 0043 | Bilibili danmaku/subtitle sidecars (offline) | Static + offline suites (Linux host), live rows `NOT_RUN` |
| 0044 | Console/REST operations hardening | Static + offline suites (Linux host), live rows `NOT_RUN` |
| 0045 | Operations backup/restore + upgrade documentation | Documentation gates only |
| 0046 | Security & privacy review + release checklist | Documentation gates only |
| 0047 | Seven-platform live qualification (final gate) | Operator-assisted on Linux; every row honestly recorded |

Live rows never pass by documentation. Execution 0047 is the last milestone and completes the original combined plan only when the operator records real outcomes per platform.
