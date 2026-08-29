# Architecture / 架构设计

- Status / 状态：Accepted baseline / 已接受基线
- Date / 日期：2026-08-30

## 1. Shape / 总体形态

The first release is a modular Python monolith. A single domain and SQLite database serve the CLI, REST API, scheduler and workers. Platform-specific behavior is behind adapters; media download and Emby rendering do not know upstream field names.

首版采用 Python 模块化单体。CLI、REST API、调度器和工作器共享同一领域层与 SQLite 数据库。平台特有行为全部位于适配器之后；媒体下载和 Emby 渲染不接触上游字段名。

```text
CLI / REST API / Scheduler
           |
     Application services
           |
  +--------+---------+----------------+
  |                  |                |
Subscription      Sync runs       Library export
  |                  |                |
SQLite <---- normalized domain ----> Filesystem
                     |
             PlatformAdapter
              /            \
   Fake/fixture adapter   MediaCrawler process bridge
                                  |
                     separately pinned checkout
```

## 2. Technology baseline / 技术基线

- Python `>=3.11,<3.14`, `uv`, `src/` package layout.
- Typer for CLI; FastAPI for local REST; Pydantic for boundary validation.
- SQLAlchemy 2.x plus Alembic, SQLite WAL by default; repository interfaces keep PostgreSQL possible later.
- `httpx` streaming downloads, standard-library XML generation, optional FFmpeg subprocess for muxing/slideshows.
- `pytest`, Ruff and mypy; deterministic fixtures and golden directory trees.

The local machine already has Python 3.11.8, uv 0.9.18 and FFmpeg. Python 3.11 is retained because it is both available and compatible with the pinned MediaCrawler requirement.

本机已有 Python 3.11.8、uv 0.9.18 与 FFmpeg。选择 Python 3.11 是因为本地可直接验证，且满足锁定版 MediaCrawler 的要求。

## 3. Modules / 模块边界

| Module / 模块 | Responsibility / 职责 | Must not / 禁止 |
| --- | --- | --- |
| `domain` | Enums, entities, value objects and state transitions / 枚举、实体、值对象、状态转换 | Import FastAPI, SQLAlchemy or upstream modules / 导入框架或上游模块 |
| `application` | Use cases, ports and transaction orchestration / 用例、端口、事务编排 | Parse platform-specific dictionaries / 解析平台原始字典 |
| `infrastructure.db` | Models, migrations, repositories and job claiming / 模型、迁移、仓库、任务领取 | Run crawlers or download media / 执行爬虫或下载 |
| `adapters` | Capability discovery, authentication/session and normalized discovery / 能力发现、登录会话、归一化发现 | Write the Emby library / 写 Emby 媒体库 |
| `integrations.mediacrawler` | External process, safe environment, output ingestion and compatibility shims / 外部进程、安全环境、输出导入、兼容修正 | Vendor or modify upstream source / 内嵌或修改上游源码 |
| `media` | Safe download, checksum, probe, optional FFmpeg transformations / 安全下载、校验、探测、FFmpeg 转换 | Depend on crawler implementation / 依赖爬虫实现 |
| `exporters.emby` | Deterministic paths, NFO and artwork sidecars / 确定性路径、NFO、图片边车 | Fetch platform APIs / 请求平台 API |
| `interfaces` | CLI, REST schemas and dependency wiring / CLI、REST 契约、依赖装配 | Contain business rules / 包含业务规则 |

## 4. Normalized model / 归一化模型

```text
Account 1 --- * Subscription * --- 1 Author
                                  |
                                  * Content 1 --- * Asset
Account/Subscription 1 --- * SyncRun --- * RunEvent
Content 1 --- * ExportRecord
```

- `Account`: platform, adapter, login method, credential reference, isolated profile path and auth status.
- `Author`: `(platform, remote_id)`, display/handle/profile/avatar and raw envelope.
- `Subscription`: account/author link, enabled flag, interval, item cap, cursor and scheduling timestamps.
- `Content`: `(platform, remote_id)`, kind, title, body, URL, published time, metrics and raw envelope.
- `Asset`: ordered image/video/audio/subtitle/cover reference, download state, local path, MIME, bytes and checksum.
- `SyncRun`: durable state, attempt, lease, redacted manifest, counters, timestamps and classified error.
- `ExportRecord`: exporter/version, source fingerprint, output path and rendered fingerprint.

All identifiers exposed outside the database are UUIDs. Timestamps are stored as UTC ISO-8601 values; original timezone/epoch fields remain in the raw envelope.

## 5. State machines / 状态机

```text
SyncRun: queued -> claimed -> awaiting_auth -> running -> ingesting -> succeeded
                         |          |            |            |
                         +----------+------------+----------> failed_retryable
                                                            -> failed_terminal
                                                            -> cancelled

Asset: discovered -> queued -> downloading -> downloaded -> verified -> exported
                         |           |              |
                         +-----------+------------> failed_retryable / failed_terminal
```

Claims use a lease timestamp and worker ID. A crashed worker makes the run claimable only after lease expiry. State changes and counters are transactional; file writes use `.part` files followed by same-filesystem atomic replacement.

任务领取使用租约时间与 worker ID。工作器崩溃后，只有租约过期的任务才能被重新领取。状态与计数在事务内变更；文件先写入 `.part`，再在同一文件系统原子替换。

## 6. Platform adapter contract / 平台适配协议

Every adapter reports a `CapabilitySet` and implements a narrow asynchronous port:

```python
class PlatformAdapter(Protocol):
    def capabilities(self) -> CapabilitySet: ...
    async def ensure_session(self, account: Account, interaction: InteractionPort) -> AuthResult: ...
    async def resolve_author(self, account: Account, reference: str) -> AuthorSnapshot: ...
    async def iter_author_content(
        self, account: Account, author: Author, cursor: Cursor | None, limit: int
    ) -> AsyncIterator[ContentSnapshot]: ...
```

Capabilities include login methods, creator reference forms, content kinds, native media availability and interactive requirements. Unsupported methods fail before a job is queued.

能力集合包含登录方式、作者引用形式、内容种类、原生媒体可用性和真人交互要求。不支持的方法必须在任务入队前失败。

## 7. MediaCrawler bridge / MediaCrawler 桥接

The bridge is optional and explicitly license-gated. It launches the pinned checkout as a child process in an isolated job directory, with one crawler at a time per account. Safe non-secret arguments include platform, `creator`, creator reference, JSONL output path, item cap, comment flags and headless setting.

Cookie values are injected through a private environment variable read by a small independent runner, then removed from its environment before upstream execution. This avoids the upstream WebUI pattern that adds cookies to both the command line and its logged command (`api/services/crawler_manager.py:113-128, 205-239`). The runner also supplies isolated account profile paths, enables media when requested, and works around the missing Zhihu creator CLI assignment without editing upstream files.

桥接器是可选且需要明确接受许可证的组件。Cookie 通过私有环境变量交给独立运行器，读取后立即从环境移除；不会沿用上游 WebUI 把 Cookie 放入命令行并记录完整命令的方式。运行器还负责账户级浏览器目录、媒体开关和知乎创作者参数兼容，全程不修改上游文件。

Output is read only from the run's new JSONL files. Because MediaCrawler names files by day and appends (`tools/async_file_writer.py:37-60`), each run receives a unique `SAVE_DATA_PATH`; no shared daily file is tailed. Raw lines are wrapped with adapter name, adapter version, upstream SHA and ingestion time.

## 8. Emby layout / Emby 目录映射

```text
library/
  xhs/
    Creator Name [creator-id]/
      tvshow.nfo
      poster.jpg
      Season 2026/
        S2026E08300001 - Post title.mp4
        S2026E08300001 - Post title.nfo
        S2026E08300001 - Post title-poster.jpg
        S2026E08300001 - Post title.assets/
          001.jpg
          source.json
```

The episode key derives from UTC publish date plus a deterministic collision ordinal assigned by `(published_at, remote_id)`. A stable remote ID is written as `<uniqueid type="media-sync-xhs" default="true">…</uniqueid>`. Creator metadata uses `tvshow.nfo`; playable posts use `episodedetails`. Gallery/text assets remain preserved even when slideshow rendering is disabled.

集编号由 UTC 发布日期和按 `(published_at, remote_id)` 确定的冲突序号组成。稳定远端 ID 写入带平台命名空间的 `<uniqueid>`。作者使用 `tvshow.nfo`，可播放内容使用 `episodedetails`；即使关闭幻灯片渲染，图文原始资产也完整保留。

## 9. Security boundaries / 安全边界

- Bind REST to loopback by default; authentication is required before non-loopback binding.
- Credential values live in OS keyring where available, with environment/file providers for headless use; database rows store provider/key only.
- Redaction happens at log construction and again at sink boundaries.
- Downloader resolves and validates every redirect, rejects loopback/private/link-local targets by default, and confines paths to configured roots.
- User-supplied creator names never become raw paths; sanitized display names are suffixed with stable IDs.

## 10. Deployment and evolution / 部署与演进

Start as one process and one SQLite writer. Scheduler and workers communicate through durable database jobs, so they can later split into separate processes without changing use cases. Native platform adapters may progressively replace the restricted bridge; raw envelopes allow re-normalization after either upstream or schema upgrades.

首版使用单进程与单 SQLite 写者。调度器和工作器通过数据库持久任务通信，因此以后可以拆进程而不改用例。原生平台适配器可逐步替换受限桥接；原始信封允许在上游或模型升级后重新归一化。
