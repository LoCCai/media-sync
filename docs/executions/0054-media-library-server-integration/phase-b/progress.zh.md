[English](progress.md) | **中文**

# 执行 0054 阶段 B 进展

- 状态：阶段 B 已实现并通过本地冻结验证；真人资格保持 `NOT_RUN`
- 日期：2026-09-05
- 基线：`4945df1`
- 规划提交：`d7e14c9`
- 实现/验证提交：`b4af46d`、`ff5da07`、`88f5ed0`、`22bd9ef`、`48ecbe9`、`d8bbdf7`
- 数据库 revision：未新增；Alembic 保持 `0007`

## 基线

阶段 B 从已发布的执行 0054-A 收尾 `4945df1` 开始。在创建本规划包之前，工作树没有 tracked change，只有既有未跟踪 `.mimosa/` 目录。该目录不属于项目范围，继续排除。

基线已实现受管树检查器、不可变服务器 profile、加固连接器、只确认接受的定向刷新、两个媒体服务器 Operation kind、qualification schema v1，以及 Library/Settings/Jobs 集成。在该历史边界，provider/path item lookup 与刷新后观察仍为 `NOT_IMPLEMENTED`；本阶段现已实现这两项能力，并把 qualification 升级为 schema v2。

## 已实现设计

阶段 B 复核了官方 Emby 4.8.10/4.9.5 与 Jellyfin 10.10.7/10.11.11 API 描述，以及 Jellyfin 的 queued item-refresh controller。定向 refresh 没有返回共同的持久 task identity。Scheduled Tasks、WebSocket 消息、服务器空闲状态、时间戳与 Etag 变化都不能把 provider task 关联到该次请求。

因此冻结的可实现声明是 `post_refresh_item_observation`：完整 absent baseline、一次 accepted refresh、连续两次观察到同一唯一 provider/path item。`provider_task_completion` 保持未实现，并明确记录 provider API 限制。

设计还冻结：

- provider-specific lookup 与 refresh query template；
- 完整本地 provider/path 相等与唯一性核验；
- incomplete 与 not-found 的真实性区分；
- 单响应、单 pass 与单 Operation 预算；
- 全 DNS answer policy、pinning、Host/SNI、禁 proxy/redirect/next-link 和仅 header 凭据流；
- query-log 整体固定化与原始 selector 禁止持久化；
- acceptance-unknown 与 completion-unknown 的独立状态；
- author baseline 已 matched 时 pre-dispatch 失败，并保留 legacy `{}` 供 acceptance-only refresh；
- targetless legacy `{}` Operation 与 `target_type=author` observation Operation 相区分，并在 worker 启动前把 publication Job 以 `related` subject 原子关联；
- phase-aware 取消、最终 CAS 与保守 restart；accepted 和 observed running checkpoint 写入既有 `result_summary`，并通过复用的 `operation_phase_changed` Event 投影；
- 数据库互斥只覆盖持久 probe 与 scan Operation；同步直接 lookup 是独立 snapshot，只受 connector 进程内 gate 限制；
- 不新增 Operation kind、Event kind 或数据库 migration，因为 revision `0007` 已提供所需 target、subject、result 与 Event vocabulary。

## 兼容性决策

既有 `POST /api/v1/media-server/scan` 请求 `{}` 保持 acceptance-only 与 targetless，并精确保留 0054-A 安全结果和 `{profile_fingerprint}` request-fingerprint 参数。同一路由增加严格 author object 作为 observation 模式。baseline 已 matched 时，该模式在 POST 前结束；acceptance-only refresh 继续由显式 legacy 请求提供。这不会静默改变旧客户端、idempotency replay、既有 Operation row 或顶部手动刷新动作。

author 模式复用同一 `media-server-scan` kind，使用 `target_type=author` 与 `target_id=<author UUID>`。既有 target relation 关联该 author，publication Job 在 worker 启动前以 `related` subject 关联。target 与 `{profile_fingerprint, mode=post_refresh_item_observation, publication_fingerprint}` 共同构成 request fingerprint，且不重定义历史 targetless row。同步 author lookup 不创建 Operation，不具备数据库 exclusive key 或跨进程关联，也不能自行成为与 scan 关联的证据。

无需 migration：当前 `0007` schema 已允许 author target、author/Job subject 与 target/related role、`result_summary` checkpoint 字段，以及 `operation_phase_changed` Event code。阶段 B 不新增数据库 kind、state、Event kind、subject type、role、表、列或 constraint value。

## 已交付

1. `d7e14c9` 单独提交双语阶段 B 冻结规划，保留 legacy `{}` acceptance-only 契约，并明确不以任何 provider 全局状态推断 task completion。
2. `b4af46d` 交付 publication target resolver、严格 manifest 权威、Emby 过滤查询与 Jellyfin 有界完整分页，以及同步作者 item lookup API。只有完整零匹配才返回 `not_found`，完整唯一 provider/path 双匹配才返回 `matched`。
3. `ff5da07` 在既有 `result_summary` 中加入受 lease/revision fencing 的 accepted/observed running checkpoint，并完成取消 CAS、最终收尾与按 phase 重启恢复；没有增加表、列、Event kind 或 Alembic revision。
4. `88f5ed0` 交付作者刷新后观察编排与 API：完整 absent baseline、至多一次 POST、可信 2xx 后保存 accepted、间隔观察同一唯一 item 两次后保存 observed。baseline 已存在时在 dispatch 前失败；accepted 后无法证明观察时保留 accepted 并以 completion unknown 收尾。
5. `22bd9ef` 把 qualification 升级为 schema v2，并为 Library `refresh_and_verify` 建立服务端授权基础。`item_lookup` 与 `post_refresh_item_observation` 成为 `IMPLEMENTED`，但没有获得真人 PASS。
6. `48ecbe9` 完成 Library 与 Jobs Web 表面：严格区分顶部 `{}` 刷新和作者 `{"author_id":"<uuid>"}` 刷新并验证；显示 accepted、observed、acceptance unknown 与 completion unknown；作者观察只显示核验次数，不伪造 provider 百分比、播放能力或远端任务完成。
7. `d8bbdf7` 增加可选启用的真实 PostgreSQL 双连接竞态套件，并在普通取消与 coordinator `shutdown()` 的取消写入前执行权威锁定读取。accepted/observed checkpoint、cancel/final 双顺序、shutdown、coordinator fallback、lease loss 与 duplicate final 现由 11 个非 skip PostgreSQL 用例覆盖，并通过 `pg_stat_activity.wait_event_type='Lock'` 证明竞争连接确实进入锁等待。
8. API、SQLite、Events、SSE、Web、日志与支持包继续只允许固定状态和摘要；原始服务器路径、provider 值、item ID、Etag、响应正文与远端错误文本不进入保留或返回出口。

## 资格状态

收尾时：

- `connection_probe`、`library_discovery`、`targeted_scan_acceptance`、`item_lookup` 与 `post_refresh_item_observation` 均为 `IMPLEMENTED`，但在授权真实服务器上执行前，真人状态全部保持 `NOT_RUN`。
- `provider_task_completion` 为 `NOT_IMPLEMENTED`，原因是 `provider_api_unsupported`；它不是 observation 的别名。
- `playback_evidence` 与 `automatic_post_export_scan` 保持 `NOT_IMPLEMENTED`，其真人状态为空。
- 本阶段所有 Emby/Jellyfin 响应均来自 mock/fake；没有真实服务器 PASS。

## 工作区纪律

阶段 B 各实现提交均排除既有 `.mimosa/`。runtime data、secret、database、archive、export/job tree、build output、cache 与 report 继续排除。收尾仓库门禁对 490 份 Markdown、两个锁定 upstream 及 787 个 tracked 文件通过：没有禁入的 generated/runtime output，拟提交 diff 没有工作站路径、private key 或赋值形式的 secret 命中，空白干净；冻结的阶段 B goal/plan 保持逐字节不变。阶段 B 共七个提交——一个规划提交与截至 `d8bbdf7` 的六个实现/验证提交——均已推送到 `origin/main`；包含本记录的文档收尾提交按约定不嵌入自身 SHA。

实现后，如果仍有 active author-observation Operation，就不得回滚到旧 binary。操作员必须等待这些行全部进入终态，或部署具备兼容 reconcile 的 binary；绝不能为了让回滚看似兼容而删除审计行或 accepted/observed 证据。

## 验证与收尾

- Web 最终门禁均在 `web/` 目录按顺序运行：`pnpm test`、`pnpm format:check`、`pnpm check`、`pnpm build`。69 项测试、format 与生产 build 均通过，Svelte/TypeScript check 为 0 errors、0 warnings。
- 更早的一次 production build 与其他 Web 命令并发运行，因争用共享 `.svelte-kit` 中间产物而单独失败；这不是测试自身失败。停止并发后，全部门禁按上述顺序重跑并通过。该 build 诊断失败被如实保留。
- 本阶段未单独执行 Phase-B 浏览器 smoke，因此不声明浏览器交互证据。
- 启用真实 PostgreSQL 后，Python 完整套件通过 `2763 passed, 3 skipped, 1 warning in 544.08s`；Ruff lint、219 个文件的 Ruff format check、103 个源码文件的 strict mypy、compileall、wheel/sdist build、lock consistency 与两个锁定 upstream 检查均通过。
- PostgreSQL 首次开发诊断共 10 项，其中 7 PASS、3 FAIL；失败揭示普通取消与 `shutdown()` 在等待竞争行锁前读取了旧 revision。两条路径都改为在取消写入前用 `require_for_update()` 重读权威行后，扩展后的最终矩阵 11/11 PASS。fixture 只在隔离 PostgreSQL schema 中创建生产 Operation/Event/Subject/StreamState 四张 metadata 表；它不证明全应用 schema 兼容或生产 PostgreSQL 部署，受支持的默认数据库仍是 SQLite。
- Alembic 仍为 `0007`。回滚旧 binary 前必须等待所有 author-observation Operation 进入终态，或使用具备兼容 reconcile 的 binary；不得删除审计行或 checkpoint 强行回滚。

阶段 B 的本地实现门已关闭。剩余工作仅包括获授权真实 Emby/Jellyfin 的外部 qualification，以及本阶段明确未实现的 provider task completion、播放证据和自动导出后扫描。
