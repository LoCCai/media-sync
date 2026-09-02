[English](goal.md) | **中文**

# 执行 0014 目标

- 状态：离线冻结切片已完成；全部真人验收行仍为 `NOT_RUN`
- 开始时间：2026-08-31 06:25 +08:00
- 完成时间：2026-08-31 06:59 +08:00
- 前置：Execution 0013 closeout commit `be979d6`
- 计划提交：`95c7082`
- 实现提交：`c4ab537`

## 结果

以平台专项离线证据收口一个快手普通单视频路径。对于一个受信 Subscription，以及一条包含合法 `video_id`、精确一个 `video_play_url` 和可选封面的归一化记录，证明既有稳定 MediaCrawler refresh locator 能解析当前签名 URL，下载并探测确定性字节，发布不可变归档 blob，并在 Emby/Jellyfin 目录中导出可播放主 `.mp4`、海报与元数据。

本执行对已经组合好的产品路径做平台级验收，并且只修复契约/端到端测试暴露的问题；不发明新 locator schema，不宣称快手作者分页有界，也不把离线 mock 冒充真人兼容。

## 设计依据

- 锁定版 MediaCrawler 快手 detail 路径接受 `KS_SPECIFIED_ID_LIST` 中的纯视频 ID，经 `parse_video_info_from_url` 解析后调用 `get_video_info_task`，并把 `photo.id`、`photo.photoUrl` 及可选 `photo.coverUrl` 写成 `video_id`、`video_play_url` 与 `video_cover_url`。
- media-sync 已把一个合法播放 URL 映射为 `<video_id>:video:0`，把可选封面映射为 `<video_id>:cover:0`，持久化无 query 的 source hint 与稳定 `mediacrawler` `adapter_refresh`，并按精确 content/remote ID/kind/position/source hint 选择 detail 候选。执行 0014 必须关闭一个已发现缺口：快手媒体 URL 中未知 query key 的值也必须从持久归一化 raw 元数据中移除，不能只依赖通用已知 key 脱敏器。
- 通用下载器、强制有界视频探测、SHA-256 归档及 Emby layout 已存在；执行 0014 补齐缺失的锁定 checkout 与平台组合证据，而不是复制这些组件。

## 验收

1. **封闭发现形状** 一条包含合法 `video_id` 与精确一个合法 `video_play_url` 的夹具记录产生一个 position 0 视频 Asset；合法封面 URL 另产生一个 position 0 封面。必须断言 remote ID、MIME hint、稳定 source hint、locator 及重放身份；即使参数名未知，快手播放/封面 URL 的每份持久 raw 副本也必须去除 query 与 fragment。缺失或非法必需身份进入 quarantine。
2. **锁定 detail 契约** 真实隔离 fake checkout 证明 `platform=ks`、`CRAWLER_TYPE=detail`、纯 ID `KS_SPECIFIED_ID_LIST`、JSONL 输出、并发/评论/媒体下载开关、保存 profile 形状、有界 child framing 及正常成功时 attempt 完整清理；返回记录必须绑定请求 `video_id`。
3. **精确刷新** runtime 把 Asset 绑定到一个当前 Subscription/Account，只接受 content、remote ID、kind、position 及无 query origin/path hint 全部精确的唯一归一化候选。仅 query 的签名轮换可在内存中接受；缺失、漂移或重复候选使用既有固定 locator 错误关闭失败。
4. **瞬态 URL 边界** 签名 URL 可存在于上游 UUID-scoped 临时 detail JSONL、有界 child frame、进程内存及当前 HTTP 请求中，但成功调用必须在返回前删除其精确 attempt 根；它绝不写入稳定 SQLite source/locator/raw 字段、归档名称、Emby 元数据、Job/SyncRun payload 或 Git 可见文件，结果与请求 `repr` 保持不披露。
5. **默认 HTTP 配置** 快手继续使用封闭的默认 request profile；client 不发送 Cookie、Authorization 或调用方可控 header。DNS 固定、重定向、续传规则、响应边界及仅 adapter 使用的一次 401/403 重解析继续生效；不增加未经证明的平台专用 header。
6. **可播放视频与封面发布** 确定性 MP4 与图片字节通过既有下载器；视频必须经过受控结构探测。两项 Asset 都以不可变 SHA-256 路径完成持久收尾，Emby layout 包含主 `.mp4`、海报、NFO 与白名单 source 元数据。
7. **重放与 generation 真值** 使用仅 query 轮换的 URL 重复导入会保留 Asset 身份/generation 与已验证字节；重复下载/导出返回 `already_verified`/`already_exported`，不会再次调用 detail、HTTP 或 probe。host/path 漂移遵循既有 generation/reset 或 refresh-mismatch 规则，不能静默接受。
8. **真实验收** 只有平台专项测试与完整仓库门禁通过后才能宣称完成。真人登录/会话、作者分页、detail/CDN 流量、平台字节及 Emby/Jellyfin 服务器行全部保持 `NOT_RUN`。

## 已知身份与清理限制

持久身份由 `<video_id>:video:0` 与无 query source hint 组成。如果快手在同一 video ID 与 origin/path 下替换字节、只变化 query，已验证字节不会自动失效；反之，无害 CDN host/path 迁移也可能需要新 discovery generation 或导致精确刷新失败。自动检测媒体替换需要上游版本/字节身份，继续延期。

当前 detail runner 在普通 `rmtree` 清理失败时返回固定失败，但尚未提供 scheduled runner 的完整 quarantine/incident/account-block 协议。执行 0014 证明成功清理，并把清理失败强化列为后续项；不宣称注入文件系统清理失败后仍能实现凭据材料零留存。

## 明确排除

- 快手图集、直播/付费/受限/已删除媒体、多播放 URL、音频、字幕、评论及可信作者 profile。
- 有界上游作者分页；锁定版 creator 路径遍历到 `no_more`，当前使用仍需 `allow_full_history` 与外层 watchdog。
- 平台专用 CDN header 与全部真人验收行。
