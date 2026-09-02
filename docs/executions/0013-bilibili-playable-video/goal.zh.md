[English](goal.md) | **中文**

# 执行 0013 目标

- 状态：离线冻结切片已完成；全部真人验收行仍为 `NOT_RUN`
- 开始时间：2026-08-31 05:12 +08:00
- 完成时间：2026-08-31 06:05 +08:00
- 前置：Execution 0012 closeout commit `7c6f567`
- 计划提交：`46323bd`
- 实现提交：`dd6cfec`

## 结果

交付首个经过离线证明的 Bilibili 可播放切片：一个以 `aid` 标识的普通投稿会产生一个可刷新的“首 P、单段 progressive”视频 Asset；既有持久 pipeline 解析其当前签名 URL、下载并探测字节，再把主视频与元数据发布到既有 Emby/Jellyfin 目录。签名 URL 与账户凭据保持瞬态；尚不支持的 DASH、音视频分离及多 P 形状必须显式失败，不能冒充可播放。

## 设计依据

- 锁定版 MediaCrawler client 提供 `get_video_info(aid|bvid)`，并以 WBI 签名请求 `/x/player/wbi/playurl`，参数包含 `avid`、`cid`、配置的 `qn`、`fourk=1`、`fnval=1` 与 `platform=pc`；其当前下载路径使用 `View.aid` 与 `View.cid`，且只消费 `durl`。
- 锁定版 bili-sync-up 源码证明：即使向 CDN 下载时不发送 Cookie，Bilibili 媒体请求仍需要浏览器型 User-Agent 与 Bilibili Referer。它还提供后续 DASH/多 P 设计参考，但执行 0013 不复制、也不宣称已交付这些更宽能力。
- MediaCrawler 继续是可选、由用户另行获取、受许可证 gate 约束的外部研究运行时；不内嵌或复制上游源码。

## 验收

1. **仅 locator 的发现身份** 归一化 Bilibili 视频元数据时，除封面外精确产生一个 position 0 的 `video` Asset。该逻辑首 P 槽使用稳定 remote ID `<aid>:video:0`、`NULL` source URL 与既有 `mediacrawler` `adapter_refresh` locator；绝不把页面 URL 或播放 URL 作为媒体持久化。重放保持同一 Asset 身份与 generation，且无需 schema migration。
2. **精确首 P 查询** detail child 把持久 numeric `aid` 与返回的 `View.aid` 绑定；存在 `pages` 时选择 `pages[0].cid`，否则使用经过验证的兼容字段 `View.cid`，再在既有账户、watchdog 与许可证边界内调用锁定 client 的播放地址方法。身份漂移、ID 缺失或非法形状全部关闭失败。
3. **单段 progressive 契约** 只接受 `durl` 中精确包含一个合法 HTTP(S) 主 URL 的响应。仅 DASH、空、多个分段或非法响应返回固定的不支持/非法结果；绝不部分下载或冒充完整媒体。备用 URL failover 延后实现。
4. **纯内存 locator 与固定 Bilibili 请求配置** 签名播放 URL 只存在于具名私有 detail 结果、有界 child frame、进程内存及当前 HTTP 请求；只有显式 detail-only gate 才会在内存中把它加入待归一化字节，并从保留 raw 元数据中移除，绝不写入 attempt JSONL 树。解析后的 locator 选择一个封闭 Bilibili header profile，只包含固定且非密钥的 User-Agent、Referer 与 Origin。Cookie 与任意调用方 header 不得进入 CDN 请求；断点续传、重定向、DNS 固定及字节/时长/header 限制继续生效。
5. **持久可播放流水线** 离线集成组合 MediaCrawler 元数据导入、绑定精确 Subscription 的刷新、确定性 HTTP 字节、强制视频探测、归档发布、Asset/Job 收尾及 Emby 导出；主要已验证视频会作为 episode 媒体文件安装，重放保持幂等。
6. **固定失败与恢复行为** 播放地址获取失败保持可重试；不支持的 progressive 形状与瞬时失败相区分；401/403 可复用既有的一次 adapter 重解析；任何失败路径都不得把稳定 locator 改写为带签名的 direct URL。
7. **真实排除项** DASH 音视频选择与合并、FLV remux、多段拼接、多 P、字幕、弹幕、付费/番剧/直播媒体、备用 URL failover 及真人账户/CDN/Emby 验收均不属于本执行；全部真人行保持 `NOT_RUN`。
8. **封闭验证** 只有归一化、detail、刷新、网络、下载、pipeline、Emby 专项测试，以及完整套件、lint、格式、类型、文档/上游检查、构建、补丁检查与保留产物/密钥审计全部通过后，才能宣称完成。

## 身份限制

发现阶段 JSONL 不包含 CID，因此执行 0013 把“该 aid 当前的逻辑首 P”建模为 `<aid>:video:0`。每次尚未解析的 detail 查询都会校验当前首 CID，但如果 Bilibili 后续在同一 aid 下替换首 P CID，本执行无法自动使已经验证的字节失效。CID-aware 发现、generation 替换及多 P 身份一并延期；必须持续记录这一限制，不能隐藏。
