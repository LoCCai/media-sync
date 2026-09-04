[English](progress.md) | **中文**

# 执行 0054 阶段 B 进展

- 状态：规划基线已记录；尚未开始实现
- 日期：2026-09-05
- 基线：`4945df1`
- 数据库 revision：计划不新增

## 基线

阶段 B 从已发布的执行 0054-A 收尾 `4945df1` 开始。在创建本规划包之前，工作树没有 tracked change，只有既有未跟踪 `.mimosa/` 目录。该目录不属于项目范围，继续排除。

基线已实现受管树检查器、不可变服务器 profile、加固连接器、只确认接受的定向刷新、两个媒体服务器 Operation kind、qualification schema v1，以及 Library/Settings/Jobs 集成。在此边界，scan completion polling 与 provider/path item lookup 仍明确为 `NOT_IMPLEMENTED`。

## 已冻结设计

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

## 工作状态

本规划切片已完成：

1. 只读复核当前 connector、Operation、payload、publication、API、Web、migration 与 qualification 边界。
2. 对比四个受支持 Emby/Jellyfin 版本的路由级契约。
3. 冻结错误 taxonomy、成功证据、兼容策略、安全预算、API/Web 契约、restart policy 与验收矩阵。
4. 创建本双语 `phase-b/` goal、plan、progress 与 verification 包。

没有修改生产源码、测试、migration、部署配置或父级 0054 文档。本计划所述 running accepted/observed checkpoint 需要未来扩展 repository/coordinator，不得表述成当前已有能力；它将复用 `result_summary` 与 `operation_phase_changed`。不声称任何实现测试结果。

## 资格状态

基线时：

- `connection_probe`、`library_discovery` 与 `targeted_scan_acceptance` 已实现，但真人状态为 `NOT_RUN`。
- `item_lookup` 与 `post_refresh_item_observation` 尚未实现；没有真人状态。
- `provider_task_completion`、`playback_evidence` 与 `automatic_post_export_scan` 保持 `NOT_IMPLEMENTED`。

实现完成后，只有前两个阶段 B 能力转为实现状态 `IMPLEMENTED`；在授权真实服务器上执行前，其真人状态仍为 `NOT_RUN`。

## 工作区纪律

本规划任务只变更 `docs/executions/0054-media-library-server-integration/phase-b/` 下八个 Markdown 文件。它不检查、不添加、不修改、不删除、不暂存、不提交、不推送 `.mimosa/`。runtime data、secret、database、archive、export/job tree、build output、cache 与 report 继续排除。

实现后，如果仍有 active author-observation Operation，就不得回滚到旧 binary。操作员必须等待这些行全部进入终态，或部署具备兼容 reconcile 的 binary；绝不能为了让回滚看似兼容而删除审计行或 accepted/observed 证据。

## 下一检查点

只有评审接受这些契约后才开始下一实现检查点。交付先从 publication target resolver 与只读 lookup 开始；只有 selector、完整性、预算和日志边界具备 focused test 后，才进入 mutation orchestration。之后每次进展更新都必须记录精确命令与结果，不得把 mocked evidence 升级为真人 qualification。
