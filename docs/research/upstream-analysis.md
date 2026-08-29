# Upstream source analysis / 上游源码分析

This report records design evidence from the exact commits in [`upstreams.lock.json`](../../upstreams.lock.json). Paths are relative to each ignored local checkout and can be reproduced using [`docs/upstreams.md`](../upstreams.md).

本报告记录 [`upstreams.lock.json`](../../upstreams.lock.json) 所锁定提交的设计证据。路径相对于本地忽略的上游检出，可按 [`docs/upstreams.md`](../upstreams.md) 复现。

## 1. MediaCrawler findings / MediaCrawler 结论

### License and shape / 许可证与形态

The custom license limits use, copying, modification and merging to non-commercial learning, forbids large-scale crawling and commercial use, and does not clearly grant redistribution/sublicensing (`LICENSE:12-18,42-48`). The code is a Python 3.11+ crawler whose factory selects seven platform classes (`main.py:50-67`; `pyproject.toml:1-7`).

定制许可证把使用、复制、修改和合并限制为非商业学习，禁止大规模抓取与商业使用，也没有清晰授予再分发/再许可权。因此新项目不得复制源代码，桥接也不会消除用户遵守该许可证的义务。

### Coupling and process behavior / 耦合与进程行为

- The CLI mutates global configuration (`cmd_arg/arg.py:344-402`).
- Platform clients depend on Playwright pages, cookies and relative project files.
- The WebUI is only an in-memory, single-child wrapper around `main.py` (`api/services/crawler_manager.py:30-41,93-151,205-239`).
- It passes Cookie secrets in command-line arguments and logs the full command (`api/services/crawler_manager.py:113-118,234-235`).
- It listens without authentication on `0.0.0.0:8080` (`api/main.py:40-66,204-205`).
- Browser state defaults to one profile per platform rather than per account (`config/base_config.py:52-59,95-96`; representative path use `media_platform/xhs/core.py:423-438`).

These constraints justify a single isolated subprocess per account job, a private secret channel, redacted event capture and an independent database. Direct imports into the main server would let global configuration and browser lifecycle leak across jobs.

这些约束说明：每个账户任务需要独立子进程、私有密钥通道、脱敏事件捕获和独立数据库；如果直接导入主服务，全局配置和浏览器生命周期会在任务间泄漏。

### Data limitations / 数据限制

MediaCrawler uses platform-specific tables (`database/models.py:33-303`), deliberately removes most creator profiles and original user IDs (`database/models.py:19-25`), and replaces them with truncated unsalted hashes/masked names (`tools/user_hash.py:11-36`). Most `save_creator()` paths are no-ops. It has no subscription, run, cursor or download-job model.

File output supports CSV/JSON/JSONL/database variants, but JSONL is appended to a date-derived filename and JSON rewrites the whole list (`tools/async_file_writer.py:37-80`). SQL update paths use select-then-write rather than a single atomic upsert (`database/db_session.py:31-84`).

因此上游数据库不能承担 `media-sync` 的订阅真相源；新项目必须独立保存用户主动订阅的远端 ID、作者标签、内容唯一键、运行水位与资产状态。

### Testing / 测试

The tree contains roughly 21 `test_*.py` files and about 115 test/test-class declarations, but the only GitHub workflow builds documentation and does not run Python tests (`.github/workflows/deploy.yml:26-64`). There is no seven-platform login/creator/media end-to-end suite, and no Emby coverage.

## 2. bili-sync-up findings / bili-sync-up 结论

The repository is MIT-licensed (`License:1-21`). It is a Rust application rather than a reusable library; the main crate declares a binary target (`crates/bili_sync/Cargo.toml`, `crates/bili_sync/src/main.rs`). Reuse should therefore focus on MIT-compatible design patterns or clearly attributed extracted modules, not a permanent child-process dependency.

该仓库使用 MIT 许可证，是 Rust 应用而非可直接调用的库。更适合借鉴或在保留声明后提炼模块，不适合成为长期子进程依赖。

### Relevant patterns / 相关模式

- Rich NFO variants model Movie, TVShow, creator/Upper, Episode and Season (`crates/bili_sync/src/utils/nfo.rs:14-147`).
- XML generation is indented, UTF-8, field-configurable and filters invalid XML characters (`crates/bili_sync/src/utils/nfo.rs:149-238`).
- Workflow creates creator, series, season and episode sidecars (`crates/bili_sync/src/workflow.rs:10413-10663`).
- Repeated scanning and credential refresh are long-running tasks (`crates/bili_sync/src/main.rs:28-165`; `crates/bili_sync/src/task/video_downloader.rs:278-287,1374-1417`).
- Retry delay and risk-control handling are classified rather than treated as generic failures (`crates/bili_sync/src/error.rs:194-335`; `crates/bili_sync/src/task/video_downloader.rs:126-201`).
- Downloads and workflow state are persisted and independently resumable rather than represented by one boolean.

These patterns drive our independent NFO writer, classified state machines, restart-safe scheduling and separate content/asset/export records. We intentionally do not carry over Bilibili-only assumptions such as BVID-centric identity or one global scan interval.

这些模式直接影响自有 NFO 写入器、分类状态机、可重启调度以及内容/资产/导出分表；不会继承 BVID 中心身份或单一全局扫描间隔等 B 站专属假设。

## 3. Reuse decision / 复用决策

| Area / 领域 | MediaCrawler | bili-sync-up | media-sync approach / 方案 |
| --- | --- | --- | --- |
| Platform browser/signature behavior / 平台浏览器与签名 | Optional external bridge under its license / 按其许可证可选外部桥接 | Bilibili only / 仅 B 站 | Adapter port, progressive clean-room/native implementations / 适配端口，逐步原生实现 |
| Creator subscription / 作者订阅 | Missing / 缺失 | Bilibili source-specific / B 站特定 | Independent normalized model / 独立统一模型 |
| Incremental state / 增量状态 | Missing / 缺失 | Mature patterns / 成熟模式 | Known IDs, watermark, cursor and durable run state / 已知 ID、水位、cursor、持久任务 |
| Download / 下载 | Partial and memory-buffered / 部分且整体读内存 | Resumable workflow concepts / 可恢复工作流思想 | Streaming `.part`, checksums, probe and retry / 流式暂存、校验、探测、重试 |
| Emby / Jellyfin | Missing / 缺失 | Rich NFO and naming / 丰富 NFO 与命名 | Independent platform-neutral exporter / 独立平台无关导出器 |
| Web/API security / Web/API 安全 | Unauthenticated broad bind / 无鉴权广泛监听 | Local self-hosted UI / 本地自托管 UI | Loopback default, auth before remote bind / 默认回环，远程绑定前鉴权 |

## 4. Main risks / 主要风险

1. **License** — An external process is an engineering boundary, not a license escape. Commercial distribution needs written authorization or independent adapters.
2. **Platform volatility** — Browser selectors, signatures and unofficial APIs change without notice; adapter capabilities must be versioned and observable.
3. **Account/risk control** — Interactive verification and temporary blocks cannot be eliminated; runs require explicit `awaiting_auth` and risk-control states.
4. **False incrementality** — Ignoring old emitted records does not bound upstream requests; the bridge requires watchdogs and explicit full-history acknowledgement.
5. **Media ambiguity** — Expiring URLs, DASH/multi-part video and image/text posts need refresh, mux and slideshow policies outside crawler metadata.
6. **Privacy** — A subscription archive intentionally links content to an author; collection must remain limited to user-selected public creators and access-controlled local storage.
