[English](progress.md) | **中文**

# 执行 0051 推进结果

- 状态：已实现并通过离线验证；真人资格仍为 `NOT_RUN`
- 日期：2026-09-04
- 基线：`38e0ebe`
- 数据库迁移：无

## 已交付

1. 新增 `GET /api/v1/platform-capabilities` 及一份后端拥有的 v1 契约，平台固定顺序为 `xhs`、`dy`、`ks`、`bili`、`wb`、`tieba`、`zhihu`。契约描述登录方式、QR 支持、作者输入提示、已验证媒体形状、限制及如实的真人证据状态。
2. 将 MediaCrawler 作者输入收口到保守的 `[A-Za-z0-9._-]{1,255}` 边界。只有 XHS 接受不透明作者 secret reference；Bilibili、抖音、快手和微博必须在任何 Author 或 Subscription 变更前提供 `allow_full_history=true`。
3. 新增 CLI 与 REST 共用的 application `WorkbenchService`，统一账户/订阅校验、预览和幂等创建。CLI 保留旧有 JSON 输出，同时两个入口现在共用同一套策略与持久化规则。
4. 新增登录专用预检，覆盖数据库、账户资格、许可证、checkout、运行时、浏览器、profile 可写性和账户锁。登录启动会在分配进程内 Operation 前调用同一 evaluator；ffmpeg 与 ffprobe 被明确排除。
5. 新增精确 `LoginSession` 二维码路由，同时保留账户路由作为兼容解析器。新的二维码尝试会在账户锁内移除旧材料；读取被限制为 2 MiB 的普通文件，并检查 inode/大小，随后复验持久化 session。
6. Accounts 页面新增能力元数据、组合状态、预检诊断与 session 绑定的 QR 轮询。Subscriptions 页面升级为账户选择、作者/策略输入、服务端预览与显式确认三个阶段。
7. 新增白名单化的策略与 checkpoint 摘要。不返回原始 cursor、签名作者 URL、凭据/secret reference、本地 profile 或运行时路径；请求校验失败也不会回显恶意输入。

## 安全与并发结果

- 无效或未确认草稿会在 Account、Author 或 Subscription 写入前失败。SQLite 新写入会取得 workbench 范围的 `BEGIN IMMEDIATE` writer reservation，使等价并发草稿收敛为唯一持久化 Account 或 Subscription，且没有 schema 变更或 migration。
- 二维码响应保留 `202` 等待、`200` 图片、`410` 终态和 `404` 未知/不合格生命周期。精确活动 session 所有权、QR 方法资格、放弃态协调、普通文件与大小边界、同文件校验及读取后 session 复验均按失败关闭处理。
- 成功的登录预检只是一份快照。它经由进程内 Operation 进入后台登录服务的过程并非跨 API 进程原子操作，因此两个进程可能同时通过预检。持久化 `LoginSession` compare-and-set 与账户 OS 锁仍是权威边界，并会安全关闭落败尝试。
- 该预检到 Operation 的竞态属于非阻塞协调与 UX 残余，不是二维码读取/复验间隙，也不是凭据或二维码权限绕过。持久化 Operations 与跨进程幂等归 Execution 0052。

## 验证结果

- Python 完整套件：`2135 passed, 3 skipped`。
- Web：Prettier、0 error/0 warning 的 `svelte-check`、七个 Vitest 测试及 adapter-static 生产构建全部通过。
- 静态/打包：Ruff、Ruff format、覆盖 90 个源码文件的 strict mypy、compileall 与 `uv build` 全部通过，并生成 sdist 和 wheel。
- 文档与锁定上游检查通过。MediaCrawler 保持在 `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`，bili-sync-up 保持在 `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`，两个 checkout 均干净。
- 聚焦契约覆盖能力形状/顺序、CLI/API 等价、拒绝时零写入、同草稿并发收敛、预检分配边界、二维码所有权/读取加固、UI 状态及 secret/path/cursor 哨兵。

## 剩余工作

- 本轮没有使用真人浏览器账户、作者端点、平台 API/CDN 或 Emby/Jellyfin 服务。七个平台的真人账户行与真实扫描/播放证据仍在 Execution 0047 下保持 `NOT_RUN`。
- Execution 0052 负责持久化 Operations、跨进程幂等、Event 存储、SSE、结构化日志、取消、重启后历史、订阅审计/删除及支持包。
- Execution 0053 保留富内容恢复；0054 保留媒体服务器控制与资格验证；0055 保留操作者认证；0056 保留最终迁移与发布工作。
