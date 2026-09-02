[English](goal.md) | **中文**

# 执行 0015 目标

- 状态：离线冻结切片已完成；全部真人验收行仍为 `NOT_RUN`
- 开始时间：2026-08-31 07:24 +08:00
- 完成时间：2026-08-31
- 前置：Execution 0014 closeout commit `6098923`
- 计划提交：`76b1973`
- 实现提交：`95d314d`

## 结果

以平台专项离线证据收口一个抖音普通单视频路径。对于一个受信 Subscription，以及一条包含 numeric `aweme_id`、空 `note_download_url`、精确一个合法 `video_download_url`、无音乐 Asset 与可选封面的归一化记录，证明纯 ID detail、绑定精确 Account/Subscription 的刷新、确定性下载与强制探测、不可变归档发布，以及 Emby/Jellyfin 主 `.mp4` 与海报/元数据输出。

本执行验收已有单视频原语，并只修复契约暴露的问题；不宣称图集、把关联音乐作为外挂音轨、有界作者分页、真实 CDN 兼容或专用抖音 request profile。

## 设计依据

- 锁定版抖音 helper 接受纯 numeric ID；detail 模式把它写入 `DY_SPECIFIED_ID_LIST`，获取一个 aweme，并持久化 `aweme_id`、`video_download_url`、`cover_url`、`music_download_url` 与逗号拼接的 `note_download_url`。
- media-sync 已把非图集记录映射为 video/audio/cover Asset，持久化稳定 `mediacrawler` 刷新 locator 与精确 AssetRefreshSource 来源，并按 content ID、remote ID、kind、position 及无 query source hint 选择 detail 候选。默认 HTTP profile、强制探测、SHA-256 归档及 Emby 主媒体 layout 均与平台无关。
- 本执行关闭的产品缺口是：与快手不同，抖音媒体字段此前尚未在保留归一化 raw 前结构化去 query，因此未知 query-key 值、URL userinfo、fragment 或漂移的嵌套对象可能越过瞬态边界。`note_download_url` 现在遵循 normalizer 的逗号列表语义，不再把整段拼接字符串当作一个 URL。

## 验收

1. **封闭普通视频形状** numeric `aweme_id`、空图片列表字段及精确一个合法视频 URL 产生一个 position 0 视频 Asset；可选合法封面产生一个 position 0 cover。验收夹具中的音乐字段为空；remote ID、position、MIME/source hint 与稳定 locator 均精确断言。
2. **持久媒体 URL 边界** `video_download_url`、`cover_url`、`music_download_url` 及逗号分隔的每个 `note_download_url` 项，在持久 raw 中只保留规范 origin/path。逗号拼接的 note 标量会变成有序平面序列；被拒绝的不透明子项会成为 `null` 槽位，不会保留嵌套数据。userinfo、全部 query 值与 fragment 均被移除；内存 discovery/detail 中被接受的 Asset 仍保留其完整瞬态 URL。
3. **锁定纯 ID detail** 真实隔离 fake checkout 证明 `platform=dy`、numeric `DY_SPECIFIED_ID_LIST`、detail/JSONL/媒体关闭/并发开关、有界 child framing、repr 安全、保存 profile 形状及正常成功 attempt 清理。
4. **精确来源与刷新** 惰性 runtime 构造绑定精确合格的 AssetRefreshSource、Account 与 Subscription。只接受 content/remote ID/kind/position/无 query source hint 全部精确的候选；缺失、漂移、重复或错误 Subscription 在媒体传输前失败。
5. **默认 HTTP 与可播放发布** 视频与封面使用 `MediaRequestProfile.DEFAULT`；媒体 HTTP 请求不发送 Cookie、Authorization、Referer、Origin 或调用方自定义 header。确定性 MP4/PNG 字节通过 mock 公网 DNS 固定与边界，视频执行受控强制探测，两项 Asset 以 SHA-256 归档路径收尾，本地 Emby layout 包含主 `.mp4`、可选海报、NFO 与白名单 source 元数据。
6. **重放与封闭落点** 仅 query 变化的 forward URL 轮换保留身份、generation 与已验证字节。在组合 E2E 中，重放返回 `already_verified`/`already_exported`，不会第二次调用 fake detail runner、HTTP、DNS 或 probe。动态哨兵不会进入 ORM、dispose 后 SQLite/sidecar、runtime/work/archive/library、对象表示或 Git 可见保留文件。
7. **真实验收** 专项门禁通过 231 项测试；最终完整套件通过 1209 项测试，另有一项在 Windows 不适用而跳过。不宣称运行过覆盖率。真人登录/会话、作者扫描、detail/CDN、平台字节及 Emby/Jellyfin 服务器行保持 `NOT_RUN`。

## 已知身份与清理限制

持久身份由 `<aweme_id>:<kind>:0` 与无 query source hint 组成。若同 ID/同 origin/path 原地替换字节而只轮换 query，已验证字节无法自动失效；CDN host/path 迁移可能重置 generation 或导致精确刷新失败。detail 输出还会继承受信 Subscription 的归属，不能独立证明 aweme 仍属于该作者。

本执行覆盖 detail 正常成功清理；注入文件系统清理失败仍缺少 scheduled runner 的完整 quarantine/incident/账户阻断协议，不宣称该场景零留存。

## 明确排除

- 抖音图集/图片、关联音乐/音频语义、多视频或封面 URL、slideshow、字幕、评论、直播/付费/受限/已删除内容及可信作者 profile。
- 有界作者分页；锁定 creator client 会遍历到 `has_more != 1`，当前使用仍需 `allow_full_history` 与外层 watchdog。
- 任何未经证明的平台专用 CDN header 与全部真人验收行。
