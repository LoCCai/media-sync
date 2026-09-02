[English](goal.md) | **中文**

# 执行 0031 目标

- 状态：冻结的离线普通原创可播放视频范围已完成；真人行保持 `NOT_RUN`
- 日期：2026-09-02
- 前驱：执行 0030 收尾 `e242b16097b2fb1f0f6ee1dc8e863ace1c68ab32`
- 范围：一条携带 `mblog.page_info` 视频的普通原创 numeric-ID 微博，在锁定 store 边界捕获，并经签名 URL 适配器刷新交付为一个可播放的 Emby MP4
- 计划提交：`1c79c6d94fbca2ac4c01ec1f9c2f6e17da7b6e7d`
- 实现提交：`666438d793c18f97af5026e7506c8ee9745eba47`

## 结果

1. 扩展锁定的微博 store shim：对 `page_info.page_type` 精确为 `video`、非转发、numeric-ID 的普通 `mblog`，在锁定 store 拍平丢弃之前精确捕获一个标量 `media_info.stream_url`。
2. 以 media-sync 自有私有字段持久化一个精确 `{"url"}` payload：严格防碰撞、持久化前递归移除，并配套封闭 URL 校验器（HTTPS `sinaimg.cn`/`*.sinaimg.cn`/`f.video.weibocdn.com` host、非根 `.mp4` 路径、无 fragment/userinfo、允许签名 query）。
3. 把该帖归一化为 `ContentKind.VIDEO` 与精确一个 position-0 VIDEO 资产 `{note_id}:video:0`；对转发、与图片字段共存、畸形 payload 与不合格身份一律关闭失败。
4. 把惰性适配器刷新扩展到微博 VIDEO 资产：一次精确 numeric-note detail 运行在内存中重新捕获当前签名 URL 并返回 DEFAULT-profile 瞬态 locator；持久状态只保留无 query 提示。
5. 通过既有有界候选轮次下载，含结构化 MP4 探测、SHA-256 归档与确定性 Emby `.mp4`/NFO/source 发布，支持零工作重放。
6. 以一条生产级 SQLite → detail 刷新 → mock HTTP → ffprobe → 归档 → Emby 组合证明全链路，同时全部真实账户/API/CDN/媒体服务器行保持 `NOT_RUN`。

## 验收边界

- 每帖精确一个视频，只来自封闭 `page_type == "video"` 加标量 `stream_url` 形状；`playback_list` 数组、画质变体、封面、时长、转发、直播/付费媒体与图文混合帖不属于本执行。
- 纯图片帖保持 0016 语义字节级兼容；同时携带两个私有字段的帖子关闭失败。
- 签名 query 只存在于瞬态子进程 frame、进程内存与 HTTP 请求中；持久资产、raw envelope、Job、归档与导出均不保留带 query 的 URL。
- 无数据库 schema 或迁移；稳定 Asset 身份与冻结媒体形状计数不变。`.upstream` 保持只读且不入库。

## 明确延期

`playback_list`/画质选择、视频封面与时长、转发、GIF、直播/付费媒体、混合媒体帖、更广微博分页、CDN 排序/竞速/跨运行缓存、字幕/弹幕、超过 64 个分 P、REST/生产打包及全部真人验收行均不属于本执行。
