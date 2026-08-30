# Architecture / 架构设计

- Status / 状态：Accepted baseline / 已接受基线
- Date / 日期：2026-08-30

## 1. Shape / 总体形态

The first release is a modular Python monolith. One domain and SQLite database currently serve the CLI, bounded local scheduler and workers; a local REST API is planned but not implemented. Platform-specific behavior is behind adapters; media download and Emby rendering do not know upstream field names.

首版采用 Python 模块化单体。CLI、有界本地调度器与工作器目前共享同一领域层和 SQLite 数据库；本地 REST API 仍是计划能力，尚未实现。平台特有行为全部位于适配器之后；媒体下载和 Emby 渲染不接触上游字段名。

```text
CLI / Scheduler / [planned REST API]
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

- Python `>=3.11,<3.14`, `uv`, and a `src/` package layout. / Python `>=3.11,<3.14`、`uv` 与 `src/` 包布局。
- Typer provides the implemented CLI and Pydantic validates boundaries; FastAPI is reserved for a planned local REST surface. / Typer 提供已实现 CLI，Pydantic 校验边界；FastAPI 仅为后续本地 REST 接口预留。
- SQLAlchemy 2.x plus Alembic, with SQLite WAL by default; repository interfaces keep PostgreSQL possible later. / 使用 SQLAlchemy 2.x 与 Alembic，默认启用 SQLite WAL；仓储接口为后续 PostgreSQL 保留可能性。
- Implemented media tooling uses `httpcore`/`httpx` streaming downloads, mandatory bounded `ffprobe` validation for video/audio and standard-library XML generation. FFmpeg muxing/slideshow transformations are planned/deferred, not current capabilities. / 已实现媒体工具使用 `httpcore`/`httpx` 流式下载、音视频强制且有界的 `ffprobe` 验证及标准库 XML 生成；FFmpeg mux/幻灯片转换属于计划/延期能力，并非当前能力。
- `pytest`, Ruff and mypy, with deterministic fixtures and golden directory trees. / 使用 `pytest`、Ruff 与 mypy，并采用确定性夹具及 golden 目录树。

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
| `media` | Safe download, checksum and mandatory video/audio structural probe; FFmpeg transformations are planned/deferred / 安全下载、校验与强制音视频结构探测；FFmpeg 转换为计划/延期能力 | Depend on crawler implementation / 依赖爬虫实现 |
| `exporters.emby` | Deterministic paths, NFO and artwork sidecars / 确定性路径、NFO、图片边车 | Fetch platform APIs / 请求平台 API |
| `interfaces` | Implemented CLI and dependency wiring; REST schemas remain planned / 已实现 CLI 与依赖装配；REST 契约仍在计划中 | Contain business rules / 包含业务规则 |

## 4. Normalized model / 归一化模型

```text
Account 1 --- * Subscription * --- 1 Author
                                  |
                                  * Content 1 --- * Asset
Account/Subscription 1 --- * SyncRun --- * RunEvent
Subscription 1 --- * Job
Content 1 --- * ExportRecord
```

- `Account`: platform, adapter, login method, credential reference, isolated profile path and auth status. / 平台、适配器、登录方式、凭据引用、隔离 profile 路径与认证状态。
- `Author`: `(platform, remote_id)`, display/handle/profile/avatar and raw envelope. / `(platform, remote_id)`、显示名/handle/profile/avatar 与 raw envelope。
- `Subscription`: account/author link, enabled flag, interval, item cap, cursor and scheduling timestamps. / 账户/作者关联、启用标志、间隔、条数上限、cursor 与调度时间戳。
- `Content`: `(platform, remote_id)`, kind, title, body, URL, published time, metrics and raw envelope. / `(platform, remote_id)`、类型、标题、正文、URL、发布时间、指标与 raw envelope。
- `Asset`: ordered image/video/audio/subtitle/cover reference, download state, local path, MIME, bytes and checksum. / 有序图片/视频/音频/字幕/封面引用、下载状态、本地路径、MIME、字节数与校验和。
- `SyncRun`: durable synchronization state, redacted manifest, counters, timestamps and classified error; it does not own worker leases. / 持久同步状态、脱敏 manifest、计数器、时间戳与分类错误；它不拥有 worker 租约。
- `Job`: durable attempt, scheduling scope, lease owner/token/expiry, payload/result and classified error; all worker claims and fencing belong here. / 持久 attempt、调度 scope、租约 owner/token/expiry、payload/result 与分类错误；全部 worker 领取和 fencing 均归属于此。
- `ExportRecord`: exporter/version, source fingerprint, output path and rendered fingerprint. / 导出器/版本、来源指纹、输出路径与渲染指纹。

All identifiers exposed outside the database are UUIDs. Timestamps are stored as UTC ISO-8601 values; original timezone/epoch fields remain in the raw envelope.

## 5. State machines / 状态机

```text
SyncRun: queued -> claimed -> awaiting_auth -> running -> ingesting -> succeeded
                         |          |            |            |
                         +----------+------------+----------> failed_retryable
                                                            -> failed_terminal
                                                            -> cancelled

Asset: discovered -> queued -> downloading -> downloaded -> verified
                         |           |              |
                         +-----------+------------> failed_retryable / failed_terminal

ExportRecord: pending -> running -> succeeded
                         |
                         +-------> failed_retryable / failed_terminal
```

Job claims use a lease timestamp, worker ID and a fresh fencing token for every attempt. A crashed worker makes the Job reclaimable only after lease expiry; a stale worker cannot complete work by borrowing a later lease held by the same worker ID. For an asset download, the exact expired owner/token may renew if no reclaim has changed the token; renewal versus reclaim is a single-winner compare-and-swap. State changes use CAS updates, event sequences are allocated atomically, and counters are transactional. Download streams use generation-bound `.part` files; archive and Emby publication use their dedicated no-clobber protocols described below.

The Emby/Jellyfin exporter never advances an asset to `exported`. A verified archive blob may be consumed by multiple exporter versions and destinations, so per-export completion belongs to `ExportRecord`. The `AssetStatus.EXPORTED` vocabulary remains reserved for compatibility but is not used by layout v1.

Migration `0003_media_download_emby` adds generation identity that `0002_checkpoint` cannot represent. Its downgrade therefore clears `assets.download_job_id` before deleting every generation-bound `asset_download` Job. Succeeded `export.emby` Jobs and records remain as the durable publication chain. Non-succeeded Emby Jobs and records are deleted so their natural identities cannot poison a later re-upgrade, except that a Job with a structurally valid closed publication intent and the records explicitly named by that intent are retained for later exact byte-validated recovery.

Job 领取使用租约时间、worker ID 和每次尝试新生成的 fencing token。工作器崩溃后，只有租约过期的 Job 才能被回收；旧执行不能借用同一 worker ID 后续领取的新租约完成任务。对资产下载而言，精确且已到期的 owner/token 只有在 reclaim 尚未改变 token 时才可续期；renew 与 reclaim 是单胜者 CAS。状态变更使用 CAS，事件序号原子分配，计数在事务内更新。下载流使用绑定 generation 的 `.part`；归档和 Emby 发布分别使用下文的 no-clobber 协议。

迁移 `0003_media_download_emby` 引入了 `0002_checkpoint` 无法表达的 generation 身份。因此 downgrade 会先清空 `assets.download_job_id`，再删除所有与 generation 绑定的 `asset_download` Job。已成功的 `export.emby` Job 及 record 作为持久发布链保留。未成功的 Emby Job 及 record 会被删除，避免 natural identity 污染后续再升级；唯一例外是携带结构严格有效的封闭发布 intent 的 Job 及该 intent 明确点名的 records，它们会保留以便后续执行精确逐字节校验恢复。

### Durable subscription scheduler / 持久订阅调度器

Migration `0004_scheduler_control_plane` adds a monotonic subscription schedule revision, scheduler scope on Jobs, an active-cycle partial unique index, and persistent platform/account lanes. A bounded tick orders null-due and timestamp-due subscriptions deterministically and materializes `subscription:<id>:schedule:<revision>` exactly once. Terminal completion advances `next_run_at` by fixed delay from completion time, so downtime does not create a catch-up storm. Downgrade removes only scheduler Jobs/lanes before dropping their schema and preserves execution 0005 download/export identities, including asset download links that SQLite batch table replacement would otherwise clear.

迁移 `0004_scheduler_control_plane` 新增单调递增的订阅 schedule revision、Job 调度 scope、active 周期部分唯一索引，以及持久平台/账户 lane。有界 tick 会按 null-due 与时间到期确定性排序，并把 `subscription:<id>:schedule:<revision>` 精确物化一次。终态收尾从完成时间按 fixed delay 推进 `next_run_at`，因此停机不会形成追赶风暴。downgrade 只在移除调度列前删除 scheduler Job/lane，并保留执行 0005 的下载/导出身份，包括原本会被 SQLite batch 重建意外清空的资产下载关联。

Each `sync.subscription` Job freezes a closed retry-policy payload. Claiming first type-scopes reclaim/requeue mutation, then enforces global capacity plus both persistent lanes: concurrency, minimum start interval and closed/open/half-open circuit state with one exact probe. Equal-jitter exponential backoff is bounded, honors a valid `Retry-After` lower bound and terminalizes at the attempt limit. Authentication and human-interaction outcomes remain dormant in `waiting_auth`/`waiting_user` until an explicit resume. Pause, resume and run-now affect future materialization; cancel fences the exact active lease.

每个 `sync.subscription` Job 都冻结封闭 retry-policy payload。领取会先按 Job 类型限定 reclaim/requeue 变更，再同时执行全局容量与两条持久 lane：并发、最小启动间隔，以及带唯一精确探针的 closed/open/half-open circuit。有界 equal-jitter 指数退避会遵守合法 `Retry-After` 下界，并在达到 attempt 上限时终态化。认证与真人交互结果停留在休眠的 `waiting_auth`/`waiting_user`，只有显式 resume 才能恢复。pause、resume 与 run-now 控制后续物化；cancel 会 fence 当前精确租约。

The worker uses short claim/start/finalize transactions and an exact-token heartbeat while a handler awaits external work. Before every Fake-handler database mutation, a same-session ownership guard obtains SQLite's writer slot and verifies the still-running, unexpired owner/token; every adapter await begins after committing the current transaction. Cancel/reclaim and handler persistence therefore serialize without a time-of-check/time-of-use gap. Raw handler exceptions, malformed results, hostile adapter/domain error codes and foreign SyncRun IDs map to a closed scheduler code and never enter Job/lane/operator projections. The generic worker operates only on `sync.subscription`; `asset_download` and `export.emby` retain their exact execution 0005 owners.

worker 以短 claim/start/finalize 事务运行，并在 handler 等待外部工作时维持精确 token heartbeat。Fake handler 每次数据库变更前，都会在同一 session 中取得 SQLite writer slot，并校验仍为 running、未过期的 owner/token；每次 adapter await 前先提交当前事务。因此 cancel/reclaim 与 handler 持久化会串行决定胜者，不存在检查到使用之间的空隙。原始 handler 异常、畸形结果、恶意 adapter/domain 错误码及跨订阅 SyncRun ID 都会映射为封闭调度错误码，绝不进入 Job/lane/运维投影。通用 worker 只处理 `sync.subscription`；`asset_download` 与 `export.emby` 继续由执行 0005 的精确 owner 负责。

Execution 0006 ships only the deterministic Fake handler and qualifies scheduler launch throttling, not every upstream HTTP request. MediaCrawler scheduled execution, manifest v3 request-delay binding, long child-process heartbeat/cancellation, and an automatic sync → download → export DAG remain separate later work.

执行 0006 只随附确定性 Fake handler，并且只验收 scheduler 启动节流，不宣称覆盖每次上游 HTTP 请求。MediaCrawler 定时执行、manifest v3 请求延迟绑定、长子进程 heartbeat/cancel，以及自动 sync → download → export DAG 均属于后续独立工作。

The foundation Fake workflow uses one caller-owned transaction with per-item savepoints. A classified crawler failure may commit its failed run plus items that were already normalized successfully; a database failure or explicit transaction-owner rejection rolls the complete attempt back. MediaCrawler work holds no SQLite transaction across browser/network waits. A parent-authenticated completion receipt seals an immutable output snapshot; ingestion then commits bounded oldest-first batches and atomically publishes each batch's content, run counters and fenced checkpoint.

基础 Fake 工作流使用调用方拥有的外层事务，并为单条内容使用保存点。分类后的爬虫失败可以提交失败运行记录及此前已成功归一化的内容；数据库失败或事务拥有者显式拒绝时会回滚整次尝试。MediaCrawler 在浏览器/网络等待期间不持有 SQLite 事务；父进程认证的完成回执会密封不可变输出快照，随后导入按旧到新的有界批次提交，并原子发布该批内容、run 计数与带 fencing 的 checkpoint。

An adapter continuation cursor is not by itself an incremental high-water mark. Subscriptions therefore keep a publish timestamp plus every known remote ID at that timestamp, while backfill continuation is tracked separately. The bridge/native adapter must begin from the newest page, scan an overlap window, accept previously unseen IDs at the watermark boundary, and stop only under its qualified ordering contract.

适配器分页 cursor 本身不能充当可靠的增量高水位。因此订阅会同时保存发布时间及该时间点全部已知远端 ID，回填分页位置则单独跟踪。桥接/原生适配器必须从最新页开始、扫描重叠窗口、接收水位边界上的新 ID，并且只在其排序契约已验收时停止。

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

The bridge is optional and explicitly license-gated. It launches the pinned checkout as a child process with a unique output root and one crawler at a time per account. The public argument vector contains only the verified Python/runner entry point and a confined non-secret specification path; platform options are applied inside the independent runner.

Cookie values and secret-bearing creator-reference components are injected through private environment channels read by a small independent runner, then removed before any upstream import or descendant process starts. Resolved secret creator inputs retain typed `SecretValue` provenance; ambiguous plain query/fragment URLs fail closed. This avoids the upstream WebUI pattern that adds cookies to both the command line and its logged command (`api/services/crawler_manager.py:113-128, 205-239`). The runner also supplies isolated account profile paths and works around the missing Zhihu creator CLI assignment without editing upstream files. Upstream binary downloads stay disabled; media-sync owns resumable retrieval after normalized discovery.

桥接器是可选且需要明确接受许可证的组件。Cookie 通过私有环境变量交给独立运行器，读取后立即从环境移除；解析后的机密作者输入保留类型化 `SecretValue` 来源，含义不明的普通 query/fragment URL 默认拒绝。桥接不会沿用上游 WebUI 把 Cookie 放入命令行并记录完整命令的方式。运行器还负责账户级浏览器目录和知乎创作者参数兼容，全程不修改上游文件；上游二进制下载保持关闭，归一化发现后由 media-sync 负责可恢复获取。

Because MediaCrawler names files by day and appends (`tools/async_file_writer.py:37-60`), each run receives a unique `SAVE_DATA_PATH`; no shared daily file is tailed. After child exit and descendant cleanup, the parent rejects any exact known Cookie/signed-reference echo, then seals the exact directory/file set, sizes and SHA-256 values in a manifest-bound completion receipt. Ingestion validates path/link invariants and reads each file once into immutable bytes before normalization, eliminating inspect-then-reopen races. Raw lines are wrapped with adapter name, adapter version, upstream SHA and ingestion time.

MediaCrawler manifest schema v2 binds account, subscription, job, crawl-start checkpoint revision, intended forward/backfill mode, login method, maximum items and creator fingerprints. Recovery may replay an older sealed crawl against the current revision only to fill missing records; it cannot supply a continuation or regress the current cursor/watermark.

由于 MediaCrawler 按日期命名并追加文件，每个任务使用唯一 `SAVE_DATA_PATH`，不会跟踪共享的每日文件。子进程退出并清理后代后，父进程先拒绝任何已知 Cookie/签名引用的精确回显，再把精确目录/文件集合、大小和 SHA-256 密封到与 manifest 绑定的完成回执。导入验证路径/链接不变量，并在归一化前只读取一次为不可变字节，从而消除“检查后重新打开”竞态。

MediaCrawler manifest v2 绑定账户、订阅、任务、爬取起始 checkpoint revision、前向/回填模式、登录方式、数量上限及作者指纹。旧密封爬取只能针对当前 revision 补齐缺失记录，不能携带 continuation，也不能回退现有游标或水位。

## 8. Secure media retrieval / 安全媒体获取

Discovery and downloading own different columns. Discovery may refresh a query-free source hint and locator, but cannot overwrite verified MIME, byte length, SHA-256, archive path or lifecycle state. A replay with the same remote identity and semantic fingerprint keeps the current generation and verified bytes. A changed remote ID, origin/path or stable media hint performs a fenced generation reset and clears downloader-owned fields; rotating only signed query data does not.

资产发现与下载器分别拥有不同字段。发现阶段可更新去 query 的来源提示与 locator，但不能覆盖已验证 MIME、字节数、SHA-256、归档路径或生命周期。同一远端身份与语义指纹的重放保留 generation 和已验证文件；远端 ID、origin/path 或稳定媒体提示变化时，以 fenced CAS 增加 generation 并清空下载字段；仅签名 query 轮换不会重置。

Locator schema v1 is closed and canonical:

- `direct` stores only a query-free, fragment-free, credential-free HTTP(S) URL.
- `adapter_refresh` stores only an adapter name and stable non-secret asset key. Its resolver may return a non-serializable, in-memory signed URL; unsupported refresh fails with `locator_refresh_unsupported`.
- MediaCrawler discovery always persists `adapter_refresh`, while the deterministic Fake path may persist a qualified `direct` URL.

Secret classification normalizes snake_case, kebab-case and camelCase boundaries. Explicit composite names such as `api_key`, `access_key`, provider-prefixed variants, `private_key` and `signing_key` are redacted, while ordinary names such as `key`, `public_key` and `key_id` remain available. Credential-marker path segments and assignments—for example `/token/<value>/video.mp4` or `/download;session=<value>/video.mp4`—are detected through bounded percent decoding, including encoded and double-encoded separators. Generic URL sinks replace the credential-bearing path; `direct` parsing and asset source-hint derivation reject it, which forces stable `adapter_refresh` persistence. The `0003` legacy backfill mirrors this rule by setting an unsafe `source_url` to null and deriving the replacement locator only from a stable asset key; it does not retroactively rewrite unrelated legacy raw envelopes.

密钥分类会归一化 snake_case、kebab-case 与 camelCase 边界。`api_key`、`access_key`、带提供商前缀的变体、`private_key` 及 `signing_key` 等明确组合名称会被脱敏，`key`、`public_key`、`key_id` 等普通名称则保留。带凭据标记的路径段或赋值，例如 `/token/<value>/video.mp4` 或 `/download;session=<value>/video.mp4`，会通过有界百分号解码识别，包括已编码及双重编码的分隔符。通用 URL 落点会替换该凭据路径；`direct` 解析和资产 source-hint 派生会拒绝它，从而强制持久稳定的 `adapter_refresh`。`0003` legacy 回填复用同一规则：将不安全的 `source_url` 置空，且只用稳定 asset key 生成替换 locator；它不会追溯改写无关的 legacy raw envelope。

Each HTTP hop is resolved independently. All DNS answers must be public, the connection is pinned to one validated address while preserving the origin Host header and TLS SNI, redirects are manual, environment proxies are disabled, and cross-origin redirects cannot inherit Range validators. Resume metadata binds asset UUID, generation, canonical locator fingerprint, validator, expected total length and current bytes. Strict `200`/`206`/`416` handling, bounded restart/byte/time/header limits, magic/MIME validation, mandatory bounded `ffprobe` structural verification for video/audio, and a final SHA-256 gate precede publication.

每个 HTTP hop 都独立解析；全部 DNS 答案必须为公网地址，连接固定到已验证地址并保留源站 Host header 与 TLS SNI。重定向由应用手动处理，禁用环境代理，跨源重定向不得继承 Range validator。续传元数据绑定资产 UUID、generation、规范 locator 指纹、validator、预期总长度与当前字节数。发布前必须通过严格的 `200`/`206`/`416` 语义、有界重启/字节/时长/header 限制、magic/MIME 校验、音视频强制且有界的 `ffprobe` 结构验证，以及最终 SHA-256 门禁。

Verified files are immutable, single-link regular blobs at `archive/sha256/<first-two>/<sha256>.<verified-extension>`. Before any database mutation, the application acquires a same-`work_root` per-asset OS lock and holds it through finalization. A durable Job stores only a SHA-256 identity of the canonical work/archive roots; a different I/O scope and local lock contention are rejected before reclaim, attempt or asset mutation. The application opens one short transaction to claim and start the job/asset, performs DNS/network/filesystem work with no database transaction, then opens one short transaction to verify the asset and complete the still-owned job atomically.

The archive ownership guard renews the exact unreclaimed token and rechecks generation/job ownership after temporary copy, fsync and rehash and immediately before no-clobber link/rename; existing-blob reuse passes the same guard. Because filesystem commit and SQLite finalization cannot be one transaction, generation-bound `.part` metadata is retained until database success. An exact committed result can be recovered without network or a new attempt, including after the final attempt was terminalized solely by lease expiry. Best-effort cleanup happens after verification and cannot reverse success. Already-verified rows revalidate the canonical blob; corrupt bytes are quarantined and missing/invalid persisted archive state is CAS-reset. These guarantees assume the configured runtime roots and all ancestors are dedicated, operator-controlled directories. The 0.x path-based implementation rejects unsafe objects present at operation time and detected leaf replacement, but concurrent malicious same-permission parent-directory substitution is outside its threat model.

已验证文件是位于 `archive/sha256/<first-two>/<sha256>.<verified-extension>` 的不可变、单链接普通 blob。应用在任何数据库变更前获取同一 `work_root` 下的逐资产 OS 锁，并持有至收尾。持久 Job 只保存规范 work/archive 根的 SHA-256 身份；不同 I/O scope 与本地锁竞争会在 reclaim、attempt 或资产变更前拒绝。应用用一个短事务领取并启动 job/资产，DNS、网络和文件系统工作期间不持有数据库事务，再用一个短事务原子验证资产并完成仍由当前 worker 拥有的 job。

归档所有权 guard 在临时复制、fsync、重哈希之后及 no-clobber link/rename 前，续期精确且未被 reclaim 的 token，并复核 generation/job 所有权；复用既有 blob 也经过同一 guard。由于文件系统提交与 SQLite 收尾不能组成同一事务，绑定 generation 的 `.part` metadata 会保留到数据库成功之后。精确的已提交结果可在不访问网络、不增加 attempt 的情况下恢复，包括最后一次 attempt 仅因租约到期而 terminalize 的情况。best-effort 清理发生在验证之后，不能反转成功。already-verified 行会复核规范 blob；损坏字节被隔离，缺失/无效持久归档状态通过 CAS 重置。这些保证以配置的运行根目录及全部祖先都是专用、由操作员控制的目录为前提。0.x 的路径式实现会拒绝操作时已存在的不安全对象及可检测的叶节点替换；同权限恶意进程并发替换父目录不在当前威胁模型内。

## 9. Emby layout / Emby 目录映射

```text
library/
  xhs-creator-creator-id-<identity-hash>/
    .media-sync-managed-v1.json
    source.json
    tvshow.nfo
    Season 2026/
      S2026E<stable-number>-xhs-note-item-id-<identity-hash>.mp4
      S2026E<stable-number>-xhs-note-item-id-<identity-hash>.nfo
      S2026E<stable-number>-xhs-note-item-id-<identity-hash>-poster.jpg
      S2026E<stable-number>-xhs-note-item-id-<identity-hash>.assets/
        body.txt
        gallery-001-image-id-<identity-hash>.jpg
        source.json
```

Filesystem identities never depend on mutable display names or titles. The season is the UTC publication year, falling back to first-seen year. The episode number is a stable positive 32-bit hash of `(platform, remote_type, remote_id)`; a collision within one season fails deterministically instead of silently renumbering. Stable remote IDs are written as namespaced `<uniqueid>` values. Creator metadata uses `tvshow.nfo`; playable posts use `episodedetails`; gallery, text, attachments, subtitles, covers and avatars remain preserved while slideshow rendering remains unimplemented/deferred.

文件系统身份不依赖可变显示名或标题。Season 使用 UTC 发布时间年份，缺失时回退首次发现年份；episode number 由 `(platform, remote_type, remote_id)` 稳定散列为正 32 位整数，同一 season 内发生碰撞时确定性失败，不静默改号。稳定远端 ID 写入带平台命名空间的 `<uniqueid>`。作者使用 `tvshow.nfo`，可播放内容使用 `episodedetails`；幻灯片渲染仍未实现/已延期，图库、正文、附件、字幕、封面和头像仍会完整保留。

Rendering first creates a byte-complete job-ID staging tree. The database is the ownership authority: every succeeded `export.emby` Job result records the non-disclosing publication scope, output path, source fingerprint, tree SHA-256, manifest SHA-256, managed-file count and exact `predecessor_job_id`. These Jobs must form one unique chain; its head, not timestamps or a manifest discovered only from disk, is the trusted predecessor. Natural identity includes the desired source and exact predecessor, so `A → B → A` source cycles are valid while forks, graph cycles and broken ancestry fail closed. A different export root has a different hashed publication scope and therefore an independent chain.

Immediately before filesystem publication, the owned Job lease is renewed with an exact intent containing the rendered source/tree/manifest identities, managed-file count and affected ExportRecord identities. Publication holds an author-scoped process and OS lock, journals before mutation, and uses no-clobber per-file operations; it never leaves export hardlinks or symlinks. The current manifest identity and every predecessor-managed byte must match the database anchor. First publication rejects an unexpected managed manifest, and a self-consistent forged manifest cannot claim a user file. The only roll-forward exception is an exact desired tree already committed by the same intent before database finalization.

After installation, every desired managed file and the manifest are identity/hash revalidated before success while the author lock, journal and rollback evidence are still held. Interrupted-transaction roll-forward parses the installed desired manifest and applies the same complete-tree check before cleanup; mismatch retains the journal and a `RECOVERY_REQUIRED` marker. User-modified and unmanaged paths are preserved and reported as classified conflicts; ambiguous rollback retains transaction evidence rather than recursively deleting unknown paths. If filesystem publication succeeded but database finalization failed, a later call may validate the exact intent and atomically finish records plus Job after the live lease is no longer active. An empty snapshot has no ExportRecord but still creates a Job anchor and may remove only unchanged predecessor-managed content. Concurrent children of one predecessor leave one durable winner; the stale sibling fails retryably and later rebases on the new head.

渲染会先生成字节完整的 job-ID staging tree。所有权权威来自数据库：每个 succeeded `export.emby` Job result 保存不披露路径的 publication scope、output path、source fingerprint、tree SHA-256、manifest SHA-256、受管文件数量及精确 `predecessor_job_id`。这些 Job 必须组成唯一链；其 head，而非时间戳或仅从磁盘发现的 manifest，才是可信 predecessor。natural identity 包含 desired source 和精确 predecessor，因此允许 `A → B → A` 来源循环，同时拒绝分叉、Job 图成环和断裂祖先链。不同 export root 具有不同的 publication scope 哈希，因此形成独立链。

文件系统发布前，服务用精确 intent 续期所拥有的 Job 租约；intent 包含渲染后的 source/tree/manifest 身份、受管文件数量及相关 ExportRecord 身份。发布阶段持有作者级进程锁与 OS 锁，在任何变更前写 journal，并逐文件执行 no-clobber 操作；导出树不遗留硬链接或符号链接。当前 manifest 身份及每个 predecessor 受管字节都必须匹配数据库锚点。首次发布会拒绝意外 managed manifest，自洽伪造 manifest 不能认领用户文件。唯一 roll-forward 例外是同一 intent 已在数据库收尾前精确提交 desired tree。

安装后，每个 desired 受管文件及 manifest 都会在作者锁、journal 与回滚证据仍保留时完成身份/哈希复核，随后才能返回成功。中断事务的 roll-forward 会解析已安装的 desired manifest，并在清理前执行同样的完整树检查；不匹配时保留 journal 与 `RECOVERY_REQUIRED` 标记。用户修改及非受管路径会保留并返回分类冲突；无法无歧义回滚时保留事务证据，而不递归删除未知路径。若文件系统发布成功但数据库收尾失败，后续调用可在活跃租约结束后验证精确 intent，并原子完成 records 与 Job。空快照没有 ExportRecord，但仍创建 Job 锚点，且只能删除未改变的 predecessor 受管内容。同一 predecessor 的并发子发布只留下一个持久胜者；旧 sibling 以可重试错误失败，随后从新 head 重建。

`source.json` is an allowlist without raw envelopes, locators, request headers or source URLs. Benign redacted raw envelopes remain in SQLite for re-normalization by design, but they never enter the export tree. No legacy library migration is required because layout v1 is the first implemented exporter.

`source.json` 采用白名单，不含 raw envelope、locator、请求 header 或来源 URL。经过脱敏的非机密 raw envelope 按设计保存在 SQLite 供重新归一化，但绝不进入导出树。layout v1 是首个实际实现的导出器，因此无需迁移旧媒体库。

## 10. Security boundaries / 安全边界

- Planned REST deployment rule: bind to loopback by default and require authentication before any non-loopback binding. No REST server is implemented yet. / REST 部署计划规则：默认只绑定 loopback，任何非 loopback 绑定前必须启用认证；目前尚未实现 REST 服务。
- Credential values live in the OS keyring where available, with environment/file providers for headless use; database rows store provider/key only. / 凭据值优先保存在 OS keyring；无头环境可使用环境变量/文件 provider，数据库行只保存 provider/key。
- Redaction happens at log construction and again at sink boundaries. / 日志构造时先脱敏，并在 sink 边界再次脱敏。
- The downloader resolves and validates every redirect, rejects loopback/private/link-local targets by default, and confines paths to configured roots. / 下载器解析并验证每次重定向，默认拒绝 loopback/私网/link-local 目标，并把路径限制在配置根目录内。
- User-supplied creator names never become raw paths; sanitized display names are suffixed with stable IDs. / 用户提供的作者名绝不直接成为路径；清理后的显示名会附加稳定 ID。
- Download and export Job payloads persist non-disclosing scope hashes rather than raw filesystem roots. / 下载与导出 Job payload 保存不披露路径的 scope 哈希，而不是原始文件系统根目录。
- Credential-bearing values are removed or redacted before SQLite and operator sinks; redacted benign raw envelopes remain a database-only re-normalization source and never enter Emby output. / 携带凭据的值在进入 SQLite 与运维 sink 前被移除或脱敏；经过脱敏的非机密 raw envelope 只作为数据库重新归一化来源，绝不进入 Emby 输出。
- Runtime filesystem roots and their ancestors are trusted operator-controlled boundaries in 0.x; hostile same-permission parent-directory mutation is not a supported deployment model. / 0.x 将运行文件系统根目录及其祖先视为操作员控制的可信边界；不支持同权限恶意进程修改父目录的部署模型。

## 11. Deployment and evolution / 部署与演进

Execution 0006 adds a bounded local scheduler/worker CLI on top of the single-host SQLite control plane. Multiple local processes may compete through writer serialization, exact leases and persistent lanes, but no resident supervisor is shipped. REST operations, production supervision/packaging, distributed HA/PostgreSQL locking and public-network deployment remain later work. Native platform adapters may progressively replace the restricted bridge; redacted raw envelopes allow re-normalization after either upstream or schema upgrades.

执行 0006 在单机 SQLite 控制面上新增有界本地 scheduler/worker CLI。多个本地进程可通过 writer 串行化、精确租约和持久 lane 安全竞争，但尚未交付常驻 supervisor。REST 运维、生产守护/打包、分布式 HA/PostgreSQL 锁及公网部署仍属于后续工作。原生平台适配器可逐步替换受限桥接；经过脱敏的 raw envelope 允许在上游或模型升级后重新归一化。
