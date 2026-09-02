[English](progress.md) | **中文**

# 执行 0014 推进结果

- 状态：离线实现与收尾门禁完成；真人验收仍为 `NOT_RUN`
- 开始时间：2026-08-31 06:25 +08:00
- 完成时间：2026-08-31 06:59 +08:00
- 计划提交：`95c7082`
- 实现提交：`c4ab537`

## 已实现

- 一条包含精确一个合法 `video_play_url` 的快手普通记录会产生 `<video_id>:video:0`；可选的合法 `video_cover_url` 会产生 `<video_id>:cover:0`。测试精确绑定内容类型、remote ID、position、MIME hint、无 query source hint 与稳定 `mediacrawler` 刷新 locator。
- 持久快手播放/封面 raw 元数据现在只保留规范 HTTP(S) origin/path。userinfo、已知与未知 query 值及 fragment 均被结构化移除；非字符串或嵌套 schema 漂移会关闭失败，不再保留不透明签名数据。内存中的 `AssetSnapshot.source_url` 仍携带发现与刷新所需的完整瞬态 URL。
- 真实隔离 fake checkout 已经过 `MediaCrawlerDetailProcessRunner`，证明 `platform=ks`、纯 ID `KS_SPECIFIED_ID_LIST`、detail/JSONL/媒体关闭/并发配置、保存 profile 派生、有界结果 framing、repr 安全及成功时 UUID attempt 清理。缺失、漂移及重复候选返回固定失败。
- 平台集成写入精确 SQLite Account/Author/Subscription 与 `AssetRefreshSource`，仅在需要时构造惰性 refresher，并把视频与封面 detail 请求绑定到精确 Account、Subscription、内容、Asset 身份及 runner 配置。快手继续使用 `MediaRequestProfile.DEFAULT`；mock HTTP 请求不含 Cookie、Authorization、Referer、Origin 或调用方自定义 header。
- 确定性 MP4 与 PNG 字节经过公网 DNS 固定及有界下载器；视频执行强制受控结构探测；两项资产均以不可变 SHA-256 归档路径及持久 succeeded Asset/Job 状态收尾。
- Emby/Jellyfin layout 把已验证 `.mp4` 发布为 episode 主媒体、把封面发布为 poster，并生成 NFO 与白名单 `source.json`。仅 query 变化的 forward URL 轮换会保留 Asset generation 与已验证字节；重放返回 `already_verified`/`already_exported`，不会新增 detail runner、HTTP、DNS、probe、归档或媒体库变更。
- 独立审查发现并关闭三项证据缺陷：嵌套快手媒体字段可能保留签名 raw、重放 detail 调用断言使用了过期 list 快照、平台 E2E 缺少精确 Account/runner 构造断言。最终复核没有剩余可执行问题。
- 专项门禁通过 `228` 项；完整套件通过 `1206` 项，另有一项在 Windows 不适用而跳过。Ruff、格式、严格类型、文档、锁定上游、构建、补丁及保留标记门禁全部通过；准确命令与结果见 `verification.md`。

## 已知限制

- 持久身份由 `<video_id>:<kind>:0` 与无 query source hint 组成。如果快手在同一 video ID 与 origin/path 下替换字节且只变化 query，已验证字节不会自动失效；反之，无害 CDN host/path 迁移可能触发 generation reset 或精确刷新不匹配。
- 已证明 detail 正常成功清理；注入文件系统清理失败时仍缺少 scheduled runner 的完整 quarantine、incident 与账户阻断协议，因此本执行不宣称该失败场景零留存。

## 执行 0014 之外待实现

- 真人快手 QR/Cookie/saved-session 登录、作者同步、detail/CDN 传输、真实平台字节探测及 Emby/Jellyfin 服务器重扫/播放；全部保持 `NOT_RUN`。
- 有界快手作者分页、图集、多播放 URL、音频、字幕、评论、直播/付费/受限/已删除媒体、可信作者 profile 及任何经过证明的平台专用 CDN header。
- 清理失败 quarantine/incident/账户阻断、媒体版本感知替换、其他平台的更多主媒体形状、REST/API 运维、部署/服务集成及跨主机 HA。
