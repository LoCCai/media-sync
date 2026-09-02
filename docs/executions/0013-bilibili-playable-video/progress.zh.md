[English](progress.md) | **中文**

# 执行 0013 推进结果

- 状态：离线实现与收尾门禁完成；真人验收仍为 `NOT_RUN`
- 开始时间：2026-08-31 05:12 +08:00
- 完成时间：2026-08-31 06:05 +08:00
- 计划提交：`46323bd`
- 实现提交：`dd6cfec`

## 已实现

- Bilibili 普通视频发现现在会产生一个稳定、仅含 locator 的 position `0` `video` Asset，其 remote ID 为 `<aid>:video:0`、`source_url=NULL`，并复用既有 `mediacrawler` `adapter_refresh` locator。动态记录不会合成该 Asset；重放保持身份与 generation，无需 schema migration。
- 可空 source 例外被封闭到唯一精确形状：`platform=bili`、content remote type 为 `content`、kind 为 `video`、position 为 `0`、remote ID 为 `<aid>:video:0`，且 source hint 为 `NULL`。近似形状及非空 hint 会在解析密钥或构造 child 前以 `locator_refresh_configuration_invalid` 关闭失败。
- 隔离 detail child 会把请求 numeric aid 与 `View.aid` 绑定，选择并校验逻辑首 CID（仅当 pages 缺失或为空时才使用经过验证的兼容字段 `View.cid`），调用锁定的播放地址任务，并且只接受一个合法主 `durl.url`。
- 播放地址缺失或调用失败映射为可重试的 `locator_refresh_temporary`；仅 DASH、空或多段 `durl` 固定映射为 `locator_refresh_unsupported`；身份漂移及非法响应固定映射为 `locator_refresh_result_invalid`。Bilibili 封面刷新仍不依赖 progressive 查询。
- 签名 URL 只经过 repr-safe 私有结果、有界 child frame、内存 JSONL 桥和当前 HTTP 请求。内存桥会在归一化前拒绝私有字段碰撞。detail-only normalizer gate 默认关闭；显式开启时会接受并递归移除该私有字段，再保留 Content/Asset raw 元数据；attempt JSONL 树绝不会被写入该 URL。
- `ResolvedLocator` 现在可携带封闭的 `BILIBILI_MEDIA` request profile。有界 HTTP client 提供固定浏览器型 User-Agent、Bilibili Referer 与 Origin，只接受 Range/If-Range 续传状态，并拒绝 Cookie、Authorization 及任意调用方 header。重定向、续传、DNS 固定、响应边界及一次 401/403 URL 重解析都会保留该 profile。
- 离线端到端测试组合合成 MediaCrawler 元数据、绑定 Subscription 的刷新、确定性 mock CDN 字节、受控 MP4 探测、SHA-256 归档发布、持久 Asset/Job 收尾及 Emby/Jellyfin 目录发布。已验证 `.mp4` 成为 episode 主媒体，同时产生 NFO/source 元数据；重放返回 `already_verified`/`already_exported`，不会再次调用 detail、HTTP 或 probe。
- 独立审查关闭了两个问题：Bilibili detail 无结果应可重试而不是永久 `asset_not_found`；非空 Bilibili video hint 不能绕过既有 source-hint 约束。复核后没有剩余可执行问题。
- 最终专项门禁通过 `223` 项；完整套件通过 `1199` 项，另有一项在 Windows 不适用而跳过。lint、格式、严格类型、文档、锁定上游、构建、补丁及精确瞬态标记审计全部通过；准确命令与计数见 `verification.md`。

## 已知限制

forward 发现元数据不包含 CID，因此持久身份是逻辑 `<aid>:video:0` 槽。尚未解析时会校验当前首 CID；但如果 Bilibili 后续在同一 aid 下替换该 CID，已经验证的字节不会自动失效，Asset generation 也不会提升。CID-aware 发现、替换失效与多 P 身份仍作为后续整体工作。

## 执行 0013 之外待实现

- Bilibili DASH 音视频选择与合并、FLV remux、多 `durl` 拼接、多 P 发现/下载、字幕、弹幕、备用 URL 故障切换，以及番剧/付费/直播媒体。
- 为当前仍只产生元数据或封面的其他爬虫平台补齐可下载主媒体，并补充更广的自动作者权限引导，例如小红书多 note 查找。
- REST/API 管理面、部署打包/服务集成，以及跨主机/HA 运行。
- 七个平台的真人 QR/保存会话登录、作者同步、签名 CDN 传输及 Emby/Jellyfin 重扫/播放验收。所有这些行仍为 `NOT_RUN`；离线 mock 不会提升它们。
