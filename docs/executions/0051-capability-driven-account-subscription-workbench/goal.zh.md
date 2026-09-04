[English](goal.md) | **中文**

# 执行 0051 目标

- 状态：已规划；尚未开始实现
- 日期：2026-09-04
- 前驱：`38e0ebe`（Console v2 之后 Linux 运行时预检全绿）
- 范围：能力契约驱动的账户登录与创作者订阅工作台
- 数据库迁移：无
- 计划提交：包含本记录的提交（不嵌入自身 SHA）

## 结果

1. 建立一个有界的七平台能力契约，统一描述登录方式、作者输入规则、全历史确认要求、已通过离线资格的媒体形状、已知限制和如实的真人资格状态。
2. 把账户/订阅草稿校验与创建移入 CLI 和 REST API 共用的 application service。任何 Account、Author 或 Subscription 行写入前拒绝无效或未确认草稿，响应永不返回凭据引用或作者 secret reference 原值。
3. 新增只检查登录前提的账户级登录预检。缺少 ffmpeg/ffprobe 不得阻塞登录；数据库、许可证、checkout、运行时、浏览器/profile 和账户锁失败必须在创建 Operation 或启动子进程前停止。
4. 把二维码读取绑定到精确 `LoginSession`，同时保留账户级端点用于兼容。维持明确的 `202` 等待、`200` 图片、`410` 已终止和 `404` 未知生命周期。
5. 把账户与订阅页面升级为能力驱动工作台：解释账户组合状态与预检失败，再通过账户/平台选择、已校验作者预览和策略确认三步引导创建订阅。
6. 在详情页暴露安全的订阅策略和 checkpoint 摘要，不返回原始 cursor、签名作者 URL、凭据引用、profile 路径或私有运行时路径。

## 验收边界

- 七个 MediaCrawler 平台标识均只有一份后端拥有的能力描述，前端消费该描述而不重复硬编码平台规则。
- Bilibili、抖音、快手和微博的订阅草稿必须在任何持久写入前显式确认全历史；同一份已接受草稿经 CLI 与 API 生成相同 policy payload。
- 登录预检与启动登录共用同一 evaluator。任一强制项失败时，不得分配内存 Operation、创建 `LoginSession` 或启动 child。
- 二维码响应绑定精确 session 身份；兼容端点不得返回其他尝试的图片。
- 哨兵测试证明 capability、preview、account、subscription 和 QR 元数据响应中没有 secret、签名 URL、原始 cursor 或本地路径。
- 离线测试不授予真人平台资格。Execution 0047 出现操作者证据前，所有真人登录/采集/CDN 和真实 Emby/Jellyfin 行保持 `NOT_RUN`。

## 明确延期

持久 Operation/Event、SSE、结构化日志、通用取消、重启后操作历史、订阅删除/审计和支持包仍归 Execution 0052。丰富内容恢复归 0053，媒体服务器控制/资格归 0054，操作者鉴权归 0055，最终迁移/发布归 0056。
