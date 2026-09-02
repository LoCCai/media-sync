[English](goal.md) | **中文**

# 执行 0018 目标

- 状态：离线执行已完成；真人验收保持 `NOT_RUN`
- 日期：2026-09-01
- 前置：Execution 0017 closeout commit `00add11`
- 计划提交：`c9d3586`
- 实现提交：`356e254`
- 范围：小红书普通单个可播放视频及可选静态封面的自动闭环

## 目标结果

Execution 0018 把 Execution 0017 已交付的精确小红书作者 Subscription 权限路径从静态笔记扩展到一条普通 `type="video"` 笔记。有界作者查找会重新取得目标 note，并只在内存中选出唯一当前小红书 CDN 视频 locator。另有独立测试让内嵌真实 H.264 MP4 通过生产有界 `FFprobeMediaProbe`；确定性组合则以不可变 SHA-256 身份归档受控媒体字节，并在现有 Emby/Jellyfin 布局中发布可播放 `.mp4`、可选静态封面及元数据。

冻结的离线形状只接受 position 0 的唯一 VIDEO Asset，以及最多一张按序作为封面的 IMAGE Asset。来源行必须保持 `type="video"`；纯视频行成为 `ContentKind.VIDEO`，一张封面加一个视频可继续表示为 `ContentKind.MIXED`。多个或畸形原始候选、非小红书初始媒体 locator 及身份漂移均关闭失败。

## 选择依据

- 锁定上游 `store/xhs/__init__.py` 原生输出 `video_url`：对于 `type="video"`，优先读取 `video.consumer.origin_video_key`/`originVideoKey` 并构造 `http://sns-video-bd.xhscdn.com/<key>`；否则返回 `video.media.stream.h264[].master_url`。无需集成 shim，也无需修改上游。
- media-sync 已能归一化小红书 VIDEO Asset，并支持小红书视频刷新、强制视频探测、SHA-256 归档及 Emby 主视频发布；Execution 0017 只是在自动作者路径的目标门中有意阻止视频。
- 贴吧锁定的 `TiebaNote` 没有媒体字段，首楼文本提取时媒体已被丢弃；知乎锁定的 `ZhihuContent` 同样会在 JSONL 前丢弃回答/文章 HTML 媒体及嵌套可播放视频数据。两者均可作为后续 shim 切片，但都不如小红书视频直接且证据完整。
- 上游使用不带平台 header 的普通 GET 下载小红书 note 媒体，因此在真人证据要求专用 profile 前，现有 `MediaRequestProfile.DEFAULT` 是诚实的离线选择。

## 验收边界

1. 作者结果只包含一条匹配来源行。在信任归一化 Asset 前，原始 `video_url` 必须是只含唯一候选的普通标量字符串，原始 `image_list` 必须是包含零或一个候选的普通标量字符串。空分段、首尾空白、重复、有效/无效混合候选及容器漂移均关闭失败，不能被静默过滤或去重。
2. 该行必须是 `type="video"`，包含 position 0 的唯一 VIDEO Asset、零或一张 IMAGE Asset，不含其他 Asset kind，把原始候选与这些 Asset 一一对应，并保持精确 content/author/source-hint 身份。初始媒体 locator 只能是普通 `http` 或 `https`，不得含 userinfo、与 scheme 不匹配/非默认 port 或 fragment，必须使用非根路径，并在 lowercase/IDNA/尾点处理后规范化为 `xhscdn.com` 或其子域。显式默认 `http:80` 与 `https:443` 端口允许使用。重定向目标继续受现有逐跳公网策略约束；本执行不宣称重定向目标只能是小红书域名。
3. 精确 Subscription 作者权限、有界查找、变更前 preflight、显式 note 覆盖优先及有效 VERIFIED 零 secret 重放继续沿用 Execution 0017 的契约。
4. 内嵌的真实 H.264 MP4 会独立通过生产 `FFprobeMediaProbe`。确定性组合使用受控 MP4 与可选 PNG 字节，贯穿 mock 公网 DNS/HTTP、`MediaRequestProfile.DEFAULT`、记录型 probe、SHA-256 归档及幂等 Emby `.mp4`/poster/NFO/source 发布；仅 query 变化的重放不会再次调用 detail、HTTP、DNS、probe、归档或导出。
5. 带签名的作者/note 权限及媒体 query 值保持瞬态；媒体 fragment 会在下载前被拒绝且绝不持久化。持久 XHS raw 与 Asset hint 保持无 query，已完成 attempt root 被删除，`.upstream` 保持未修改且不纳入跟踪。冻结的作者视频目标门只应用于自动 creator fallback；现有显式精确 note 兼容路径不属于本次新增验收声明。

## 明确排除

- 在没有用户凭据与服务时，真人 QR/Cookie 登录、creator/feed/detail 流量、真实小红书 CDN 字节及真实 Emby/Jellyfin 扫描/播放保持 `NOT_RUN`。
- 多于一张封面/图片、多个视频变体、更广泛的混合媒体形状、H.265/AV1 选择、DASH/HLS manifest、实况照片、动图、音频提取、字幕、评论、媒体版本替换及平台专用 header 继续延期。
- 贴吧/知乎媒体 shim、作者分页加固、权限过期恢复及跨 Asset 刷新缓存仍为后续工作；更大的七平台目标继续推进。
