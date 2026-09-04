[English](goal.md) | **中文**

# 执行 0054 阶段 B 目标

- 状态：规划基线已冻结；尚未开始实现
- 日期：2026-09-05
- 基线：`4945df1`（执行 0054-A 收尾）
- 数据库 revision：计划不新增
- 范围：有界 provider/path 查找与如实的刷新后受管项目观察

## 结果

在不声称 Emby/Jellyfin 未提供能力的前提下，完成 0054-A 之后最小且安全的一步。既有空对象 `{}` 的定向刷新请求继续可用且只证明接受。操作员还可以选择一个由本地授权、已发布的作者，检查精确受管 provider/path 项目是否存在，只请求一次带后置观察的刷新，并观察持久化核验活动。产品必须把刷新接受、受管项目观察和可播放性作为三个独立事实呈现。

## 真实性边界

受支持的 Emby/Jellyfin HTTP API 不会从 `POST /Items/{id}/Refresh` 返回持久任务身份。全局 Scheduled Task 状态无法与该次 POST 关联；Jellyfin WebSocket 的刷新进度也不是持久、唯一关联的任务契约。因此阶段 B 不实现、也不声称 provider task completion。

实现能力命名为 `post_refresh_item_observation`。严格成功证据为：

1. dispatch 前，一次完整且有界的查找没有观察到精确项目。
2. 唯一一次 refresh POST 返回可信 2xx。
3. 后续一次完整查找观察到恰好一个同时精确匹配 provider key/value 与 server path 的项目。
4. 间隔一个正时间后，第二次观察仍找到同一唯一项目。

这只证明已接受刷新之后发生了 absent-to-unique-match 后置条件；不证明所有 provider 队列已排空、元数据已最终稳定、媒体可播放，或所有远端变化都由该刷新引起。

baseline 已存在的项目不具备严格成功资格。author observation 模式在 POST 前以 `media_server_scan_observation_precondition_failed` 终止；只想执行 acceptance-only 手动刷新的操作员可以改用保留的 `{}` 请求。Etag 变化、Scheduled Task 状态变化、服务器空闲、`DateModified`、`DateLastRefreshed`、`DateLastSaved` 与 `RefreshState` 都不是完成证据。

## 验收条件

1. 保留以 `{}` 调用 `POST /api/v1/media-server/scan` 的 0054-A acceptance-only 契约。同一路由额外精确接受 `{"author_id":"<uuid>"}` 进入 observation 模式。显式 null 与未知字段无效。两种形状都不能提供 origin、URL、路径、Library ID、provider selector、远端 item ID、API key、网络规则、超时、分页大小或轮询策略。
2. 后端从当前唯一成功的 publication head 与严格 manifest 派生 selector：provider key 为 `media-sync-{platform}-creator`，provider value 为作者已存 remote ID，server path 为配置的 Library path 与确定性作者目录拼接。dispatch 前必须再次核验同一 publication。
3. 新增有界同步只读接口 `GET /api/v1/media-server/items/by-author/{author_id}`。完整遍历后的零匹配正常返回 `not_found`；完整且唯一的双重匹配返回 `matched`。响应只包含安全 digest、计数、完整性范围和时间。
4. Emby lookup 使用其有文档的 `GET /Items` Path 与 AnyProviderIdEquals 过滤器，并固定 ParentId、Recursive、Fields、关闭图片/用户数据及 `Limit=2`。返回的每一行仍须在本地同时精确核验 provider value 与派生路径。
5. Jellyfin lookup 在配置的 Library 下使用有文档的 `GET /Items` 分页，固定 ParentId、Recursive、Fields、关闭图片/用户数据并要求总数。不得发送未支持的 Path 或 AnyProviderIdEquals 过滤器。SearchTerm 永远不能成为缺失判断的权威。
6. 在遍历证明唯一之前，lookup 不能报告 `matched`。多个不同 item identity 精确匹配时返回 `media_server_item_lookup_ambiguous`；页数、item、字节、JSON、deadline 预算耗尽或响应不一致时返回 `media_server_item_lookup_incomplete`，绝不降级为 `not_found`。
7. refresh 路由必须按 provider 分流。Emby 可以收到有文档的 `Recursive=true`；Jellyfin 不得收到这个未声明参数。不得回退全库刷新，不得从 Scheduled Tasks 或 WebSocket 推断完成，也不得重试 POST。
8. 复用现有 `media-server-scan` Operation kind 与 profile-exclusive domain。legacy `{}` 请求继续 targetless。observation Operation 使用 `target_type=author` 与 `target_id=<author UUID>`；既有 target 关系自动关联 author，publication Job 以 `related` subject 在 worker 启动前原子关联。新 request fingerprint 绑定 mode、profile、author target 与 publication identity，且不改变 legacy fingerprint。
9. 持久 phase 为 `preparing`、`baselining`、`dispatching`、`accepted`、`polling`、`observed`。新增受 lease/revision fence 保护的 running checkpoint，把 `accepted` 或 `observed` 证据写入既有 `result_summary`，并复用 `operation_phase_changed`；不新增 Event kind 或 schema migration。progress 是无 total 的核验次数，永远不是远端扫描百分比。
10. author baseline 已 matched，或已知发生在 transport dispatch 前的取消/失败，都不得发送 POST。matched baseline 以 `media_server_scan_observation_precondition_failed` 结束，并引导 acceptance-only 操作员使用 legacy 请求。transport entry 后、可信 2xx 前的一切歧义均为终态、不可重试的 `media_server_scan_acceptance_unknown`。可信 2xx 后发生超时、取消、重启、lookup 失败、漂移或观察预算耗尽时，终态为不可重试的 `media_server_scan_completion_unknown`，并保留 accepted checkpoint。只有取消尚未在权威锁内先胜出时，observed checkpoint 才能提交；observed 一旦提交，迟到取消不得覆盖它，coordinator 兜底也不得用空 summary 覆盖 accepted 证据。
11. API、SQLite、Events、SSE、Web、日志和 support bundle 不得暴露原始 server path、provider value、远端 item ID、Etag、响应正文、远端错误文本、凭据或完整 secret reference。边界外只允许 domain-separated digest 与固定错误码。
12. 单元、集成、API、Web、安全、migration 兼容、SQLite 竞态和真实 PostgreSQL 竞态测试覆盖冻结契约。mock 结果只构成实现证据；真实服务器资格仍为 `NOT_RUN`。

## Provider 契约

兼容下限为 Emby 4.8.10 与 4.9.5，以及 Jellyfin 10.10.7 与 10.11.11。

- Emby `GET /Items` 声明支持 Path 与 AnyProviderIdEquals；refresh 接口声明递归刷新并返回空 200。直接 GET 单项需要用户作用域路由，因此阶段 B 使用列表路由。
- Jellyfin `GET /Items` 声明 ParentId、Recursive、Fields、IDs 和分页，但没有 Path 或 AnyProviderIdEquals。item refresh 接口把工作入队并返回 204，不返回 task ID；其公开路由不包含 `Recursive`。
- 共同 DTO 只能依赖 `Id`、`Path`、`ProviderIds` 与可选 `Etag`。Etag 仅用于诊断，既不是成功的必要条件，也不是充分条件。

规范依据为 [Emby 4.8.10 OpenAPI](https://github.com/MediaBrowser/Emby.SDK/blob/4.8.10.0/Resources/OpenApi/openapi_v3.json)、[Emby item query](https://dev.emby.media/reference/RestAPI/ItemsService/getItems.html)、[Emby item refresh](https://dev.emby.media/reference/RestAPI/ItemRefreshService/postItemsByIdRefresh.html)、[Jellyfin 10.10.7 OpenAPI](https://api.jellyfin.org/openapi/stable/jellyfin-openapi-10.10.7.json)、[Jellyfin 10.11.11 OpenAPI](https://api.jellyfin.org/openapi/stable/jellyfin-openapi-10.11.11.json) 与 [Jellyfin 10.10.7 ItemRefreshController](https://github.com/jellyfin/jellyfin/blob/v10.10.7/Jellyfin.Api/Controllers/ItemRefreshController.cs)。

## 安全与预算边界

每一页 lookup 和 POST 都必须独立重复 0054-A 的全部 DNS answer allowlist、连接 IP pinning、保留原 Host/TLS SNI、禁用环境代理、拒绝重定向、固定 origin/route allowlist、最终边界 secret 解析、`X-Emby-Token` 凭据出口、header/body/JSON 上限与绝对 deadline。忽略服务端 next link；分页索引只能由本地计算。

初始固定上限为：Jellyfin 每页 128 行；每次 lookup pass 最多 32 页、4,096 个唯一 item、8 MiB；一次 scan observation 总计最多 128 页、检查 16,384 行、32 MiB；总观察窗口最多 120 秒，poll 间隔至少两秒。既有单响应上限继续为 64 个 header、单 header 行 8 KiB、header 总计 64 KiB、body 256 KiB、JSON 深度 8、JSON item 2,048、单字符串 4,096 字符。服务器侧部署配置可以降低这些值，但 API 请求不能提高或替换它们。

带 query 的 wire event 不得保留完整 URL 或 query string。路径与 provider value 可能被百分号编码，子串替换不足以完成脱敏。连接器应在请求期间把依赖库 wire message 整体替换为固定事件，只发出应用自有固定码和 domain-separated digest。

profile-exclusive 数据库 key 只串行化持久 probe、legacy scan 与 author-observation scan Operation。同步 lookup 接口是独立的只读 snapshot；connector 的进程内 gate 会限制同进程访问，但不声称跨进程互斥，也不声称它与 scan Operation 具有关联关系。

## 资格边界

阶段 B 将 taxonomy 调整为：

- `item_lookup`：实现门禁通过后为 `IMPLEMENTED`。
- `post_refresh_item_observation`：实现门禁通过后为 `IMPLEMENTED`。
- `provider_task_completion`：`NOT_IMPLEMENTED`，原因为 `provider_api_unsupported`。
- `playback_evidence` 与 `automatic_post_export_scan`：`NOT_IMPLEMENTED`。

本工作区没有真实 Emby/Jellyfin 凭据。已实现 lookup 与 observation 的真人状态仍为 `NOT_RUN`；未实现能力的真人状态为 null。mock server 永远不能赋予真人 PASS。

## 范围外

播放、需认证的证据写入、自动 export-to-scan 串联、浏览器可写媒体服务器 profile、多 profile、访问控制、保留策略、破坏性清理、孤儿修复、强制覆盖和 provider-specific 后台任务插件都不在阶段 B 范围。跨 provider 的精确 scan-task completion 需要未来 provider-specific、可关联的任务契约，本阶段不得用近似信号冒充。
