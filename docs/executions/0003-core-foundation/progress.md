# Execution 0003 progress / 执行 0003 推进结果

- Status / 状态：Complete / 已完成
- Started / 开始时间：2026-08-30 03:50 +08:00
- Completed / 完成时间：2026-08-30 04:26 +08:00

## Delivered / 已交付

- Added an installable Python 3.11 package, locked `uv` environment, environment-based settings, and secret-free diagnostics.
- Defined immutable domain snapshots, the exact seven-platform vocabulary, adapter ports, classified errors, and validated auth/run/job/asset state machines.
- Added the deterministic Fake adapter with QR/Cookie/saved-session capability truth, repeated IDs, multi-page results, and same-timestamp fixtures.
- Added a bounded synchronization service that rejects unsupported platform/login combinations before a run is created, redacts raw failures, and preserves safe retry timing.
- Implemented ten SQLAlchemy tables and package-owned Alembic migrations for accounts, login sessions, authors, subscriptions, content, assets, sync runs/events, jobs, and export records.
- Enabled SQLite foreign keys, WAL, busy timeout, and explicit transaction begin semantics so nested savepoints still roll back with their outer transaction on Python 3.11.
- Implemented atomic SQLite upserts, monotonic publish-watermark boundary IDs, compare-and-swap run transitions, atomic event sequencing, and lease fencing tokens that reject expired or ABA-stale workers.
- Connected `SyncService` to SQLAlchemy without internal commits. Two fixture passes leave one author, four unique contents and four unique assets while preserving runs, events, counters, cursor state, publish watermark and boundary IDs.
- Added packaged migration tests that build and unpack the wheel, then initialize a database using only migration resources inside the wheel.
- Added secret-safe CLI commands for database initialization, account add/list, subscription add/list and deterministic sync run. Unsupported login methods and inline Cookie-like values are rejected before persistence.
- Added a read-only `db status` command that verifies connectivity, the current Alembic revision and all ten required tables without creating a missing database or exposing its URL.
- Marked secret-adjacent dataclass fields such as credential references, cursors, raw envelopes and signed asset URLs as excluded from `repr`.

- 已添加可安装的 Python 3.11 包、锁定的 `uv` 环境、环境变量配置和无密钥诊断。
- 已定义不可变领域快照、七平台精确枚举、适配端口、分类错误，以及经过验证的登录/运行/任务/资产状态机。
- 已添加确定性 Fake 适配器，真实声明二维码/Cookie/保存会话能力，并覆盖重复 ID、跨页及相同时间戳夹具。
- 已添加有界同步服务；平台或登录方式不支持时在创建运行前失败，原始异常被脱敏，同时保留安全的重试等待秒数。
- 已实现十张 SQLAlchemy 表和随安装包发布的 Alembic 迁移，覆盖账户、登录会话、作者、订阅、内容、资产、同步运行/事件、任务和导出记录。
- 已启用 SQLite 外键、WAL、忙等待和显式事务开始，确保 Python 3.11 下嵌套保存点仍能随外层事务回滚。
- 已实现 SQLite 原子 upsert、单调发布时间水位边界 ID、运行状态 CAS、原子事件序号，以及可拒绝过期/ABA 旧 worker 的租约 fencing token。
- 已把 `SyncService` 接入 SQLAlchemy 且仓储不自行提交；两轮夹具同步最终只有 1 位作者、4 条唯一内容和 4 个唯一资产，并保留运行、事件、计数、游标、水位及边界 ID。
- 已添加迁移打包测试：构建并解包 wheel，仅使用 wheel 内迁移资源初始化数据库。
- 已添加安全的数据库、账户、订阅和确定性同步 CLI；不支持的登录方式与疑似内联 Cookie 会在落库前被拒绝。
- 已添加只读 `db status`，检查连接、当前 Alembic revision 和全部十张必需表；数据库缺失时不会创建文件，也不会暴露 URL。
- 已将凭据引用、游标、原始信封和签名资产 URL 等相邻敏感字段排除在 dataclass `repr` 之外。

## Review fixes / 审查修复

- Fixed expired-lease completion and same-worker ABA completion by checking both expiry and a per-claim token.
- Fixed SQLite legacy savepoint behavior that could otherwise survive an outer rollback.
- Removed read-before-write paths that produced `SQLITE_BUSY_SNAPSHOT` in concurrent SQLite upserts and status updates.
- Made Alembic read the configured runtime URL and made `db init` migrate rather than calling `metadata.create_all`.
- Prevented database URLs, credential references and raw domain/adapter exception text from appearing in CLI output.

- 修复过期租约仍可完成、同 worker ABA 旧执行可借新租约完成的问题。
- 修复 SQLite 旧式保存点可能绕过外层回滚的问题。
- 移除会在并发 SQLite upsert/状态更新中触发 `SQLITE_BUSY_SNAPSHOT` 的先读后写路径。
- 让 Alembic 使用运行时配置库，并让 `db init` 执行迁移而非 `metadata.create_all`。
- 阻止数据库 URL、凭据引用以及原始领域/适配器异常文本出现在 CLI 输出中。

## Deferred by design / 按设计后续实现

- This execution uses only the network-free Fake adapter. MediaCrawler process integration, real secret resolution, binary downloads and Emby export belong to executions 0004-0005.
- The foundation persists continuation cursor, publish watermark and same-timestamp boundary IDs, but the Fake CLI deliberately does not claim bounded upstream incrementality. Consuming those checkpoints through overlap/known-ID stop rules belongs to the bridge milestone.
- Live login/content/media qualification remains `NOT_RUN`; no account, browser or platform endpoint was used.

- 本执行只使用无需网络的 Fake 适配器。MediaCrawler 进程桥接、真实密钥解析、二进制下载和 Emby 导出属于执行 0004-0005。
- 基线会持久化分页 cursor、发布时间水位和同时间戳边界 ID，但 Fake CLI 不宣称已经限制上游增量请求；通过重叠窗口/已知 ID 停止规则消费这些检查点属于桥接里程碑。
- 真人登录、内容与媒体验收仍为 `NOT_RUN`；本执行未使用账户、浏览器或平台端点。
