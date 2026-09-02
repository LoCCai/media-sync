**English** | [中文](upstream-analysis.zh.md)

# Upstream source analysis

This report records design evidence from the exact commits in [`upstreams.lock.json`](../../upstreams.lock.json). Paths are relative to each ignored local checkout and can be reproduced using [`docs/upstreams.md`](../upstreams.md).

## 1. MediaCrawler findings

### License and shape

The custom license limits use, copying, modification and merging to non-commercial learning, forbids large-scale crawling and commercial use, and does not clearly grant redistribution/sublicensing (`LICENSE:12-18,42-48`). The code is a Python 3.11+ crawler whose factory selects seven platform classes (`main.py:50-67`; `pyproject.toml:1-7`).

### Coupling and process behavior

- The CLI mutates global configuration (`cmd_arg/arg.py:344-402`).
- Platform clients depend on Playwright pages, cookies and relative project files.
- The WebUI is only an in-memory, single-child wrapper around `main.py` (`api/services/crawler_manager.py:30-41,93-151,205-239`).
- It passes Cookie secrets in command-line arguments and logs the full command (`api/services/crawler_manager.py:113-118,234-235`).
- It listens without authentication on `0.0.0.0:8080` (`api/main.py:40-66,204-205`).
- Browser state defaults to one profile per platform rather than per account (`config/base_config.py:52-59,95-96`; representative path use `media_platform/xhs/core.py:423-438`).

These constraints justify a single isolated subprocess per account job, a private secret channel, redacted event capture and an independent database. Direct imports into the main server would let global configuration and browser lifecycle leak across jobs.

### Data limitations

MediaCrawler uses platform-specific tables (`database/models.py:33-303`), deliberately removes most creator profiles and original user IDs (`database/models.py:19-25`), and replaces them with truncated unsalted hashes/masked names (`tools/user_hash.py:11-36`). Most `save_creator()` paths are no-ops. It has no subscription, run, cursor or download-job model.

File output supports CSV/JSON/JSONL/database variants, but JSONL is appended to a date-derived filename and JSON rewrites the whole list (`tools/async_file_writer.py:37-80`). SQL update paths use select-then-write rather than a single atomic upsert (`database/db_session.py:31-84`).

### Testing

The tree contains roughly 21 `test_*.py` files and about 115 test/test-class declarations, but the only GitHub workflow builds documentation and does not run Python tests (`.github/workflows/deploy.yml:26-64`). There is no seven-platform login/creator/media end-to-end suite, and no Emby coverage.

## 2. bili-sync-up findings

The repository is MIT-licensed (`License:1-21`). It is a Rust application rather than a reusable library; the main crate declares a binary target (`crates/bili_sync/Cargo.toml`, `crates/bili_sync/src/main.rs`). Reuse should therefore focus on MIT-compatible design patterns or clearly attributed extracted modules, not a permanent child-process dependency.

### Relevant patterns

- Rich NFO variants model Movie, TVShow, creator/Upper, Episode and Season (`crates/bili_sync/src/utils/nfo.rs:14-147`).
- XML generation is indented, UTF-8, field-configurable and filters invalid XML characters (`crates/bili_sync/src/utils/nfo.rs:149-238`).
- Workflow creates creator, series, season and episode sidecars (`crates/bili_sync/src/workflow.rs:10413-10663`).
- Repeated scanning and credential refresh are long-running tasks (`crates/bili_sync/src/main.rs:28-165`; `crates/bili_sync/src/task/video_downloader.rs:278-287,1374-1417`).
- Retry delay and risk-control handling are classified rather than treated as generic failures (`crates/bili_sync/src/error.rs:194-335`; `crates/bili_sync/src/task/video_downloader.rs:126-201`).
- Downloads and workflow state are persisted and independently resumable rather than represented by one boolean.

These patterns drive our independent NFO writer, classified state machines, restart-safe scheduling and separate content/asset/export records. We intentionally do not carry over Bilibili-only assumptions such as BVID-centric identity or one global scan interval.

## 3. Reuse decision

| Area | MediaCrawler | bili-sync-up | media-sync approach |
| --- | --- | --- | --- |
| Platform browser/signature behavior | Optional external bridge under its license | Bilibili only | Adapter port, progressive clean-room/native implementations |
| Creator subscription | Missing | Bilibili source-specific | Independent normalized model |
| Incremental state | Missing | Mature patterns | Known IDs, watermark, cursor and durable run state |
| Download | Partial and memory-buffered | Resumable workflow concepts | Streaming `.part`, checksums, probe and retry |
| Emby / Jellyfin | Missing | Rich NFO and naming | Independent platform-neutral exporter |
| Web/API security | Unauthenticated broad bind | Local self-hosted UI | Loopback default, auth before remote bind |

## 4. Main risks

1. **License** — An external process is an engineering boundary, not a license escape. Commercial distribution needs written authorization or independent adapters.
2. **Platform volatility** — Browser selectors, signatures and unofficial APIs change without notice; adapter capabilities must be versioned and observable.
3. **Account/risk control** — Interactive verification and temporary blocks cannot be eliminated; runs require explicit `awaiting_auth` and risk-control states.
4. **False incrementality** — Ignoring old emitted records does not bound upstream requests; the bridge requires watchdogs and explicit full-history acknowledgement.
5. **Media ambiguity** — Expiring URLs, DASH/multi-part video and image/text posts need refresh, mux and slideshow policies outside crawler metadata.
6. **Privacy** — A subscription archive intentionally links content to an author; collection must remain limited to user-selected public creators and access-controlled local storage.
