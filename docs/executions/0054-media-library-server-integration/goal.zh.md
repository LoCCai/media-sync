[English](goal.md) | **中文**

# 执行 0054 目标

- 状态：阶段 A 已交付并完成冻结验证；执行 0054 继续为另行冻结的阶段 B 保持开启
- 开始时间：2026-09-05 02:45 +08:00
- 前驱：`22b5864`（执行 0053 收尾）
- 范围：0054 阶段 A——安全已发布媒体库检查、单个环境变量托管的 Emby/Jellyfin 配置、持久连接/定向刷新操作及证据驱动的资格视图
- 计划数据库 revision：`0007_media_server_operations`

## 结果

把既有确定性 Emby/Jellyfin 兼容导出变成操作者可核验的媒体产品。操作者可以在不知道宿主路径的前提下检查当前受管作者树及漂移，在浏览器之外配置恰一个媒体服务器，测试该配置、触发有界媒体库刷新，并查看已有持久证据，同时不会把本地或 mock 检查误当成真人资格。

## 验收

1. 保持既有 `GET /api/v1/library` 数组响应与筛选兼容。新增按作者 UUID 寻址的详情端点，其权威来源是数据库发布链加严格受管 manifest，绝不接受调用方文件路径。
2. 只返回有界逻辑相对节点和白名单发布事实：layout/source/tree/manifest 标识、发布 Job 标识、受管数量、相互独立的新鲜度与完整性状态、用户修改保护状态、cursor 事实及固定允许动作。当前源快照不可导出时，`blocked` 是正常新鲜度，不得误标成发布损坏。不得返回 export root、宿主路径、原始 Job payload、异常正文、locator、来源 URL 或文件字节。
3. 在只打开既存文件的作者锁下检查 manifest 与受管文件；manifest 畸形、链接、越界、大小写碰撞、文件缺失、大小/哈希漂移、替换竞态或发布链不一致全部关闭失败。单次请求最多校验 128 个文件、操作者配置的字节预算（默认 1 GiB）及截止时间（默认 10 秒），并受进程级 single-flight 限制。绑定 manifest 的 cursor 防止不同发布版本混页。响应必须报告精确 `page`、`complete` 或 `budget_exhausted` 范围，绝不能把部分检查升级成整树健康。检查必须只读，不修复、不删除，也不创建锁或目录。
4. 新增一个不可变、由环境变量托管的 `emby` 或 `jellyfin` 媒体服务器配置。API 只返回手工构建的安全摘要；API key 值和完整 secret reference 不得进入 API 响应、日志、Operation payload 或 SQLite。
5. 媒体服务器请求只能到达已配置的规范 origin 及操作者白名单 IP/CIDR。请求不能覆盖 URL、host、key、路径、library 或网络策略。每个 DNS 答案都必须被允许，解析与连接必须绑定，拒绝重定向，并限制时间、header、正文和条目数。私网/回环目标必须由部署配置显式授权。
6. 把连接探测和手动定向刷新持久化为封闭的 `media-server-probe` 与 `media-server-scan` Operation。两个端点都默认关闭并共用一个配置互斥键；UI action 标记不能替代服务端强制门。唯一变更远端状态的协议是在精确匹配 virtual folder 后调用固定 `POST /Items/{configured-library-id}/Refresh`；`404`、`405` 或 `501` 必须变为 `media_server_targeted_scan_unsupported`，绝不回退全库 `/Library/Refresh`。取消只在 dispatch 前生效。POST 不做 transport retry；dispatch 后的超时、断连、取消或崩溃必须成为不可重试的 `media_server_scan_acceptance_unknown`/`interrupted`，不得虚报成功、安全失败或已取消。持久层只记录白名单证据。
7. 升级 Library、Settings 与 Jobs 页面，展示真实受管树、安全连接姿态、持久探测/扫描活动及资格证据。本地导出成功、请求已接受和 mock 测试都不得推导出真人扫描或可播放样本通过。
8. 增加 migration、单元、集成、API、Web、安全与打包覆盖；既有 Emby 导出、内容/资产浏览器、Operation/Event、migration 与 Web 契约必须继续兼容。

## 资格边界

本执行可以证明本地 manifest/树行为以及 fake 或 mock Emby/Jellyfin 协议行为。当前工作区没有配置服务器 URL、API key 或 library ID。已经实现的连接探测、版本/library 发现和定向刷新接受，在操作者于获授权部署中实际执行前保持真人 `NOT_RUN`。阶段 A 的扫描完成轮询、provider/path 项目查找、播放证据记录和自动导出后扫描属于 `NOT_IMPLEMENTED`，不能写成 `NOT_RUN`。Linux 部署证据及七平台全部真人账户/CDN 行继续为 `NOT_RUN`。

## 延期范围

阶段 A 完成后 0054 仍保持开放：必须另行冻结 0054-B，交付可 mock 的扫描完成进度及 provider/path 项目查找，路线图才能把媒体服务器联动称为完成。播放证据写入需等待操作者鉴权并继续属于 0055；浏览器可写设置、多配置、破坏性清理、保留、孤儿修复、强制覆盖和访问控制也仍属于 0055；最终旧控制台移除仍属于 0056。导出后自动扫描属于尚未冻结执行归属的未来范围。
