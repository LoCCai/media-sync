[English](verification.md) | **中文**

# 执行 0054 阶段 B 验证

- 状态：实现完成；本地冻结验证通过；真人资格保持 `NOT_RUN`
- 日期：2026-09-05
- 基线：`4945df1`
- 规划提交：`d7e14c9`
- 实现/验证提交：`b4af46d`、`ff5da07`、`88f5ed0`、`22bd9ef`、`48ecbe9`、`d8bbdf7`
- 数据库 revision：无新增；Alembic 保持 `0007`

## 验证政策

本文档区分规划证据、自动化实现证据与真人 qualification。本地和 mock 检查可以证明冻结实现契约，但不能证明真实服务器兼容性、provider task completion 或播放。

任何官方 API 响应都不得被解释得比其契约更强。refresh 200/204 只证明接受。完整精确 item lookup 只证明一次观察。mock provider test 只证明实现行为。只有经授权的真实服务器执行才能把真人状态从 `NOT_RUN` 改变。

## 规划基线证据（历史）

| 检查 | 命令或来源 | 状态 |
| --- | --- | --- |
| Git 基线 | `git rev-parse HEAD` | `PASS` — 规划修改前为 `4945df1969d4f4b8f2dd8c8da972b6183798f671` |
| 初始 tracked worktree | `git status --short` | `PASS` — 没有 tracked change；只有既有未跟踪 `.mimosa/` |
| 修改前 focused tests | `uv run --frozen pytest -q -p no:cacheprovider tests/unit/test_media_server_connector.py tests/unit/test_media_server_application.py tests/unit/test_api_media_server.py tests/unit/test_operation_payloads.py tests/integration/test_operation_repository.py tests/integration/test_operation_coordinator.py` | `PASS` — 218 passed、1 warning，耗时 10.06s；该 warning 是既有 Starlette/httpx deprecation |
| 官方路由复核 | goal 中链接的四份版本化 OpenAPI 与 Jellyfin 10.10.7 controller | `PASS` — 定向 refresh 无 task ID；已记录 provider 路由差异 |
| 文档结构 | `uv run --frozen python scripts/check_docs.py` | `PASS` — 490 个 Markdown 文件的文档链接均正常 |
| 文档集合 | 对 `phase-b/` 做精确文件名与数量审计 | `PASS` — 恰好为预期的 8 个 Markdown 文件 |
| Patch 空白 | 直接审计全部 8 个未跟踪文件的尾随空白与末尾换行，并运行 `git diff --check -- docs/executions/0054-media-library-server-integration/phase-b` | `PASS` — 无尾随空白、每个文件均以换行结尾，tracked diff 检查干净 |
| 范围审计 | `git status --short --untracked-files=all -- docs/executions/0054-media-library-server-integration/phase-b` 与排除 `.mimosa/` 的完整状态 | `PASS` — 仅出现预期的 8 个阶段 B 文件；父级 0054 文档与执行索引未修改 |

所有选择 deliverable 文件的命令和未来提交都排除既有 `.mimosa/`。

## 实现提交与最终门禁

| 边界 | 提交或命令 | 结果 |
| --- | --- | --- |
| 双语冻结规划 | `d7e14c9` | `PASS`——legacy `{}`、精确 lookup、刷新后 observation、无 provider task completion 与无新 migration 的边界独立提交 |
| 目标解析与精确 lookup | `b4af46d` | `PASS`——publication/manifest 权威、Emby 过滤查询、Jellyfin 有界完整分页、精确 provider/path 唯一性与安全 API 均落地 |
| 持久 checkpoint 与竞态 | `ff5da07` | `PASS`——accepted/observed checkpoint、取消/最终 CAS 与按 phase 重启恢复落地，复用 `result_summary` 和 `operation_phase_changed` |
| 作者观察编排与 API | `88f5ed0` | `PASS`——absent baseline、至多一次 POST、可信 acceptance、两次间隔 unique match，以及 completion unknown 保留 accepted 事实均落地 |
| Qualification v2 与 Library 授权 | `22bd9ef` | `PASS`——`item_lookup`、`post_refresh_item_observation` 的实现状态和 `refresh_and_verify` 服务端授权基础落地 |
| Web 收口 | `48ecbe9` | `PASS`——Library/Jobs 的两种动作、lookup、观察状态、安全文案、迟到响应隔离与无假百分比完成 |
| 真实 PostgreSQL 竞态加固 | `d8bbdf7` | `PASS`——普通取消与 coordinator shutdown 在取消写入前执行权威锁定读取；新增真实双连接竞态套件 |
| 首次并发 Web 尝试 | production build 与其他 Web 命令并发运行 | 已记录的 `FAIL`——只有 production build 因并发命令争用共享 `.svelte-kit` 中间产物而失败；这不是单元测试失败，且该诊断记录未被隐去 |
| Web 最终串行门禁 | 在 `web/` 目录依次运行 `pnpm test`、`pnpm format:check`、`pnpm check`、`pnpm build` | `PASS`——69 项测试通过；format 通过；check 为 0 errors、0 warnings；生产 build 通过 |
| Python 完整套件 | 设置 `MEDIA_SYNC_TEST_POSTGRESQL_URL` 指向隔离本地服务后运行 `uv run --frozen pytest -q -p no:cacheprovider` | `PASS`——`2763 passed, 3 skipped, 1 warning in 544.08s`；11 项 PostgreSQL 用例均实际运行而非 skip，没有媒体服务器 mock 被升级为真人证据 |
| 真实 PostgreSQL 竞态专项 | 启用隔离 PostgreSQL 服务后运行 `uv run --frozen pytest -q -p no:cacheprovider tests/integration/test_operation_postgresql_races.py` | `PASS`——11 passed；通过两个独立连接及 `pg_stat_activity.wait_event_type='Lock'` 证明 accepted/observed checkpoint、cancel/final 双顺序、shutdown、coordinator fallback、lease loss 与 duplicate final 确实发生行锁竞争 |
| PostgreSQL + SQLite Operation 联合 | 真实 PostgreSQL 竞态专项加 `tests/integration/test_operation_coordinator.py` 与 `tests/integration/test_operation_repository.py` | `PASS`——84 passed in 9.22s |
| 阶段 B 实现联合专项 | `uv run --frozen pytest -q -p no:cacheprovider tests/integration/test_media_server_publication.py tests/integration/test_operation_coordinator.py tests/integration/test_operation_repository.py tests/unit/test_api_media_server.py tests/unit/test_media_server_application.py tests/unit/test_media_server_connector.py tests/unit/test_media_server_observation.py tests/unit/test_media_server_publication.py tests/unit/test_operation_payloads.py` | `PASS`——350 passed |
| Qualification、Library 与 API 专项 | `uv run --frozen pytest -q -p no:cacheprovider tests/integration/test_library_application.py tests/unit/test_api_library_inspection.py tests/unit/test_api_media_server.py tests/unit/test_qualifications.py` | `PASS`——70 passed |
| Library application 专项 | `uv run --frozen pytest -q -p no:cacheprovider tests/integration/test_library_application.py` | `PASS`——12 passed |
| Python 质量与构建 | Ruff lint、Ruff format check、strict mypy、compileall、`uv build` | `PASS`——静态质量、编译及 wheel/sdist 构建均通过 |
| 锁定上游 | `uv run --frozen python scripts/check_upstreams.py` | `PASS`——两个锁定 upstream 检查通过 |
| 收尾仓库门禁 | `uv run --frozen python scripts/check_docs.py`；tracked generated/runtime denylist；拟提交 diff 的工作站路径、private-key 与赋值形式 secret 扫描；冻结 goal/plan diff；`git diff --check` | `PASS`——490 份 Markdown；787 个 tracked 文件且零禁入产物；敏感模式零命中；冻结的阶段 B goal/plan 未变化；空白干净 |

PostgreSQL 首次开发诊断共 10 项，其中 7 PASS、3 FAIL。失败排程暴露普通取消与 `shutdown()` 在等待竞争行锁前读取了旧 revision；两条路径现都在取消写入前通过 `require_for_update()` 获取权威行，扩展后的最终专项 11/11 PASS。该证据只针对 Operation metadata：fixture 仅在隔离 schema 中创建生产 Operation/Event/Subject/StreamState 四张表，不代表全应用 schema 迁移或生产 PostgreSQL 部署已完成；受支持的默认数据库仍为 SQLite。

## 契约证据映射

| 冻结要求 | 已实现证据 |
| --- | --- |
| 如实能力命名 | qualification 与 UI 断言 `post_refresh_item_observation`；`provider_task_completion` 保持不支持 |
| 向后兼容 scan | 精确测试确保 legacy 空对象 `{}` Operation 继续 targetless，并保留其 acceptance-only 结果与 golden `{profile_fingerprint}` request fingerprint |
| Observation identity | author 模式使用 `target_type=author`、`target_id=<author UUID>`、既有 author target relation，以及 worker 前原子关联的 publication Job `related` subject |
| 本地权威 | 当前完整 publication head/manifest 测试；无调用方远端 selector；POST 前重核验 |
| 精确 lookup | 完整 provider/path 双重匹配真值表与完整唯一性要求 |
| Emby/Jellyfin 差异 | 四版本请求 snapshot 与禁用参数/fallback 断言 |
| 有界工作 | 单响应、pass、Operation、页、item、字节、JSON、poll 与 deadline 耗尽测试 |
| Mutation 真实性 | matched baseline 不发送 POST；否则最多一次 POST，区分 acceptance unknown 与 completion unknown；accepted/observed checkpoint 使用既有 `result_summary` 与复用的 `operation_phase_changed`，不新增 Event kind |
| 取消与重启 | 明确覆盖 accepted/cancel、observed/cancel/final、coordinator fallback、transport-entry、phase-based reconcile 与 lease/final/checkpoint CAS 竞态 |
| 并发边界 | 数据库 profile exclusivity 只覆盖持久 probe 与 scan Operation；直接 GET 是独立有界 snapshot，只具备进程内 connector gate，不声称关联证据 |
| Migration 与回滚 | Alembic 保持 `0007` 且不新增数据库 vocabulary；旧 binary 不得接管 active author observation |
| 保密 | 日志、DB、Events、SSE、API、support bundle 与 Web 均无原始或编码 selector sentinel |
| 资格真实性 | automated、implementation 与 human 状态保持独立 |

## 已验证自动化矩阵

1. Emby 4.8.10 与 4.9.5 使用有过滤的 `GET /Items`，本地核验每个候选，发送有文档的递归 refresh，并接受有文档的 200。
2. Jellyfin 10.10.7 与 10.11.11 使用有界 Library 分页，不使用 Path/AnyProviderIdEquals；refresh 不发送 Recursive 参数；接受有文档的 204。
3. 代码不得调用 Emby direct item GET、`/ScheduledTasks`、WebSocket completion、全局 `/Library/Refresh`、服务端 next link 或第二次 mutation attempt。
4. 完整零匹配为 `not_found`；完整唯一精确 identity 为 `matched`；多个 identity 为 ambiguous；部分、漂移、重复、畸形或预算耗尽遍历为 incomplete。
5. 只有 absent baseline、accepted POST、两次间隔观察到同一唯一 item 才成功。既有 baseline 在 POST 前以 `media_server_scan_observation_precondition_failed` 结束；任何 Etag 变化都不能证明完成。
6. legacy 空对象 `{}` scan 继续 targetless 和 succeeded/accepted，并保留其精确结果与 golden `{profile_fingerprint}` request fingerprint。author 模式使用 `target_type=author` 与 author UUID、既有 target relation，并在 worker 启动前原子关联 publication Job `related` subject。
7. accepted 与 observed running checkpoint 写入既有 `result_summary`，且只发出既有 `operation_phase_changed`；不新增 Event kind。之后任何 completion-unknown 或 coordinator fallback 都保留 accepted 证据，绝不以 `{}` 替换其 summary。
8. 权威锁竞态矩阵证明：已知可信 2xx 后，cancel-first 对 accepted-checkpoint 与 accepted-first 对 cancel 两种顺序都保留接受事实；cancel-first 对 observed-checkpoint 会阻止 observed 并以 completion unknown 结束；observed-first 对 cancel 或 finalization 保留 observed success；coordinator exception/finalization 保留 accepted 证据且不可重试。entry 前取消发送零 POST；entry-first 的 timeout/reset/5xx/redirect/cleanup 歧义最多发送一次 POST，并以 acceptance unknown 结束。
9. 相同 idempotency key 与相同 identity replay 同一 Operation；mode/author/profile/publication 变化冲突。profile exclusivity 只串行化持久 probe、legacy scan 与 author-observation scan Operation。直接 GET 保持有界且独立，只使用 connector 进程内 gate，不具备数据库互斥，也不是与 scan 关联的证据。
10. 每页重复全部 DNS answer/CIDR 验证与 pinning。混合 answer、rebinding、Host/SNI 漂移、proxy、redirect、next link、非 header 凭据和 route/query override 尝试都 fail closed。
11. 即使远端响应和异常包含敏感值，任何持久或返回出口都不存在原始 path/provider/item/Etag/token 与百分号编码变体。
12. SQLite 验证 phase-aware restart：`preparing`/`baselining` 为 pre-dispatch interrupted，`dispatching` 为终态 acceptance unknown，`accepted`/`polling` 为保留 checkpoint 的终态 completion unknown，`observed` 只有 checkpoint 有效时才 succeeded，legacy targetless `{}` 行为保持不变。真实 PostgreSQL 服务另行验证 accepted/observed checkpoint、cancel/final、shutdown、coordinator fallback、lost-lease 与 duplicate-final 行锁竞态；每个失败方都被观察到等待数据库锁，且最终只保留一个如实的 terminal Event。
13. Migration-compatibility 测试保持 Alembic `0007`，并证明阶段 B 不新增数据库 kind、state、Event kind、subject type、role、表、列或 constraint value，同时使用已经有效的 author target、author/Job subject、`result_summary` 与 `operation_phase_changed`。
14. Web 单元测试覆盖两种 action、author gating、SSE reconnect、request generation、如实文案、无假百分比、无原始 selector 与 unknown-state 恢复指引；Svelte check 与生产 build 覆盖编译。本轮没有单独执行阶段 B 浏览器 smoke，因此不声明浏览器交互证据。
15. 部署回滚检查与文档禁止旧 binary 接管 active author-observation Operation；必须等待这些行进入终态，或部署具备兼容 reconcile 的 binary，且不得删除审计证据。

各 focused selection 彼此之间并与完整套件重叠，计数不得彼此相加，也不得加到 2763 项完整套件总数上。最终记录以完整 Python `2763 passed, 3 skipped, 1 warning in 544.08s` 和 Web 69 项测试为准；Ruff、format、strict typing、compileall、build/distribution 与 upstream 门禁也已通过。

## 真人资格

本工作区没有真实 Emby/Jellyfin origin、Library 或凭据。收尾时：

- `connection_probe`、`library_discovery`、`targeted_scan_acceptance`、`item_lookup` 与 `post_refresh_item_observation` 均为 `IMPLEMENTED`，但授权操作员真实执行前，真人状态全部保持 `NOT_RUN`；
- `provider_task_completion` 保持 `NOT_IMPLEMENTED`，原因为 `provider_api_unsupported`，不是 `NOT_RUN`；
- `playback_evidence` 与 `automatic_post_export_scan` 保持 `NOT_IMPLEMENTED`，真人状态为空；
- 69 项 Web 测试和全部 Python/mock 证据都不授予真实服务器 PASS。

## 退出门禁

阶段 B 已达到本地实现退出门：legacy `{}` scan 行为与旧 row 保持兼容，精确 lookup 和刷新后 observation 通过自动化验证，Alembic 保持 `0007`，Python/Web/质量/构建/upstream 最终门禁通过。首次并发执行中的 production build 失败已如实保留，顺序重跑成功。

本地退出门不改变真人资格：provider task completion 与 playback 没有被证明，自动导出后扫描也未实现。真实服务器运行属于外部 qualification，不能用 mock 伪造。
