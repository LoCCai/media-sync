[English](goal.md) | **中文**

# 执行 0054 目标

- 状态：阶段 A 与阶段 B 均已交付并通过本地冻结验证；执行 0054 已完成，真人资格保持 `NOT_RUN`
- 开始时间：2026-09-05 02:45 +08:00
- 前驱：`22b5864`（执行 0053 收尾）
- 范围：安全已发布媒体库检查、单个环境变量托管的 Emby/Jellyfin 配置、持久连接/定向刷新、精确作者项目查找、刷新后项目观察及证据驱动的资格视图
- 阶段 B 提交：规划 `d7e14c9`；实现/验证 `b4af46d`、`ff5da07`、`88f5ed0`、`22bd9ef`、`48ecbe9`、`d8bbdf7`
- 数据库 revision：`0007_media_server_operations`；阶段 B 无新增 migration

## 结果

把既有确定性 Emby/Jellyfin 兼容导出变成操作者可核验的媒体产品。操作者可以在不知道宿主路径的前提下检查当前受管作者树及漂移，在浏览器之外配置恰一个媒体服务器，测试该配置、执行只确认接受的定向刷新、精确查找已发布作者项目，或发起刷新后观察，并查看持久证据，同时不会把本地或 mock 检查误当成真人资格、provider task completion 或播放证据。

## 验收

1. 保持既有 `GET /api/v1/library` 数组响应与筛选兼容。新增按作者 UUID 寻址的详情端点，其权威来源是数据库发布链加严格受管 manifest，绝不接受调用方文件路径。
2. 只返回有界逻辑相对节点和白名单发布事实：layout/source/tree/manifest 标识、发布 Job 标识、受管数量、相互独立的新鲜度与完整性状态、用户修改保护状态、cursor 事实及固定允许动作。当前源快照不可导出时，`blocked` 是正常新鲜度，不得误标成发布损坏。不得返回 export root、宿主路径、原始 Job payload、异常正文、locator、来源 URL 或文件字节。
3. 在只打开既存文件的作者锁下检查 manifest 与受管文件；manifest 畸形、链接、越界、大小写碰撞、文件缺失、大小/哈希漂移、替换竞态或发布链不一致全部关闭失败。单次请求最多校验 128 个文件、操作者配置的字节预算（默认 1 GiB）及截止时间（默认 10 秒），并受进程级 single-flight 限制。绑定 manifest 的 cursor 防止不同发布版本混页。响应必须报告精确 `page`、`complete` 或 `budget_exhausted` 范围，绝不能把部分检查升级成整树健康。检查必须只读，不修复、不删除，也不创建锁或目录。
4. 新增一个不可变、由环境变量托管的 `emby` 或 `jellyfin` 媒体服务器配置。API 只返回手工构建的安全摘要；API key 值和完整 secret reference 不得进入 API 响应、日志、Operation payload 或 SQLite。
5. 媒体服务器请求只能到达已配置的规范 origin 及操作者白名单 IP/CIDR。请求不能覆盖 URL、host、key、路径、library 或网络策略。每个 DNS 答案都必须被允许，解析与连接必须绑定，拒绝重定向，并限制时间、header、正文和条目数。私网/回环目标必须由部署配置显式授权。
6. 把连接探测和手动定向刷新持久化为封闭的 `media-server-probe` 与 `media-server-scan` Operation。两个端点都默认关闭并共用一个配置互斥键；UI action 标记不能替代服务端强制门。legacy 严格空对象 `{}` scan 保持 targetless，只在精确匹配 virtual folder 后调用固定 `POST /Items/{configured-library-id}/Refresh` 并证明可信 2xx acceptance；`404`、`405` 或 `501` 必须关闭失败，绝不回退全库 `/Library/Refresh`，也不重试 POST。
7. 只接受作者 UUID 的同步 lookup API 必须从当前唯一成功 publication head 与严格 manifest 派生 provider/path selector。Emby 使用有界过滤查询，Jellyfin 使用有界完整分页；两者都在本地要求 provider 与 path 精确双匹配并证明唯一性。只有完整零匹配是 `not_found`；多匹配、漂移、畸形或预算耗尽不得伪装成未找到。
8. 同一 scan 路由额外只接受严格 `{"author_id":"<uuid>"}`。作者模式必须先完成 absent baseline，随后至多发送一次刷新 POST；可信 2xx 后持久保存 accepted checkpoint，只有间隔后连续两次观察到同一唯一 item 才保存 observed 并成功。baseline 已存在时不发送 POST；dispatch 后无法确定 acceptance 为不可重试 `media_server_scan_acceptance_unknown`，accepted 后无法证明观察则为不可重试 `media_server_scan_completion_unknown`，且必须保留 accepted 事实。该结果是 `post_refresh_item_observation`，不是 provider task completion 或播放证据。
9. accepted/observed running checkpoint 复用既有 `result_summary` 与 `operation_phase_changed`，并受 lease/revision 与取消/final CAS 保护。按 phase 重启恢复不得覆盖 accepted/observed 事实；作者 scan 关联 author target 与 publication Job related subject。阶段 B 不增加 Operation/Event kind、表、列或 Alembic revision，现有 revision 保持 `0007`。
10. 升级 Library、Settings 与 Jobs 页面，展示真实受管树、安全连接姿态、精确 lookup、两种 scan 动作、持久状态及 qualification schema v2。作者观察显示核验次数但绝不伪造远端百分比；未知状态文案不得反射服务器值或暗示 provider task 完成、可播放或自动重试。
11. 增加单元、集成、API、Web、安全、迁移兼容与打包覆盖；既有 Emby 导出、内容/资产浏览器、Operation/Event、legacy `{}` fingerprint/result、migration 与 Web 契约继续兼容。本地导出成功、可信 acceptance、observed postcondition 和 mock 测试均不得推导出真人 PASS。

## 资格边界

本执行可以证明本地 manifest/树行为以及 fake 或 mock Emby/Jellyfin 协议行为。当前工作区没有配置真实服务器 URL、API key 或 library ID。`connection_probe`、`library_discovery`、`targeted_scan_acceptance`、`item_lookup` 与 `post_refresh_item_observation` 已实现，但在操作者于获授权部署中实际执行前，真人状态全部保持 `NOT_RUN`。`provider_task_completion` 因 `provider_api_unsupported` 为 `NOT_IMPLEMENTED`；`playback_evidence` 与 `automatic_post_export_scan` 同样为 `NOT_IMPLEMENTED`，不得写成 `NOT_RUN`。Linux 部署证据及七平台全部真人账户/CDN 行继续为 `NOT_RUN`。

## 延期范围

阶段 B 已交付精确 provider/path 项目查找及刷新后观察，但官方共同 API 不返回可关联的持久 task identity，因此 `provider_task_completion` 明确留在范围外，不得用 Scheduled Tasks、WebSocket、空闲状态、时间戳、Etag 或 observation 近似。播放证据写入需等待操作者鉴权并继续属于 0055；浏览器可写设置、多配置、破坏性清理、保留、孤儿修复、强制覆盖和访问控制也仍属于 0055；最终旧控制台移除仍属于 0056。导出后自动扫描保持 `NOT_IMPLEMENTED`，尚无冻结执行归属。
