# Execution 0018 goal / 执行 0018 目标

- Status / 状态：Planned / 已计划
- Date / 日期：2026-09-01
- Predecessor / 前置：Execution 0017 closeout commit `00add11`
- Scope / 范围：Automatic XHS ordinary single playable video with optional static artwork / 小红书普通单个可播放视频及可选静态封面的自动闭环

## Outcome / 目标结果

Extend the exact XHS author-Subscription authority path delivered in Execution 0017 from static notes to one ordinary `type="video"` note. A bounded creator lookup must reacquire the target note, select exactly one current XHS CDN video locator in memory, pass synthetic MP4 bytes through mandatory bounded probing and immutable SHA-256 archival, and publish a playable `.mp4` plus optional static artwork and metadata in the existing Emby/Jellyfin layout. / 把 Execution 0017 已交付的精确小红书作者 Subscription 权限路径从静态笔记扩展到一条普通 `type="video"` 笔记。有界作者查找必须重新取得目标 note，只在内存中选出唯一当前小红书 CDN 视频 locator，把合成 MP4 字节送入强制且有界的探测与不可变 SHA-256 归档，并在现有 Emby/Jellyfin 布局中发布可播放 `.mp4`、可选静态封面及元数据。

The frozen offline shape accepts exactly one VIDEO Asset at position zero and at most one ordered IMAGE Asset used as artwork. The source row must remain `type="video"`; a video-only row becomes `ContentKind.VIDEO`, while one cover plus one video may remain `ContentKind.MIXED`. Multiple video variants, multiple images, non-XHS media hosts and identity drift fail closed. / 冻结的离线形状只接受 position 0 的唯一 VIDEO Asset，以及最多一张按序作为封面的 IMAGE Asset。来源行必须保持 `type="video"`；纯视频行成为 `ContentKind.VIDEO`，一张封面加一个视频可继续表示为 `ContentKind.MIXED`。多个视频变体、多张图片、非小红书媒体 host 及身份漂移均关闭失败。

## Why this slice / 选择依据

- Locked upstream `store/xhs/__init__.py` natively emits `video_url`: for `type="video"`, it prefers `video.consumer.origin_video_key`/`originVideoKey` and constructs `http://sns-video-bd.xhscdn.com/<key>`; otherwise it returns `video.media.stream.h264[].master_url`. No integration shim or upstream edit is required. / 锁定上游 `store/xhs/__init__.py` 原生输出 `video_url`：对于 `type="video"`，优先读取 `video.consumer.origin_video_key`/`originVideoKey` 并构造 `http://sns-video-bd.xhscdn.com/<key>`；否则返回 `video.media.stream.h264[].master_url`。无需集成 shim，也无需修改上游。
- media-sync already normalizes XHS VIDEO Assets, supports XHS video refresh, mandatory video probing, SHA-256 archives and Emby primary-video publication. Execution 0017 deliberately blocked only the automatic creator-video target gate. / media-sync 已能归一化小红书 VIDEO Asset，并支持小红书视频刷新、强制视频探测、SHA-256 归档及 Emby 主视频发布；Execution 0017 只是在自动作者路径的目标门中有意阻止视频。
- Tieba's locked `TiebaNote` contains no media field; media is discarded while extracting first-floor text. Zhihu's locked `ZhihuContent` likewise discards answer/article HTML media and nested playable-video data before JSONL. Both can be future shim slices, but neither is as direct or as evidence-complete as XHS video. / 贴吧锁定的 `TiebaNote` 没有媒体字段，首楼文本提取时媒体已被丢弃；知乎锁定的 `ZhihuContent` 同样会在 JSONL 前丢弃回答/文章 HTML 媒体及嵌套可播放视频数据。两者均可作为后续 shim 切片，但都不如小红书视频直接且证据完整。
- Upstream downloads XHS note media with a plain GET and no platform headers. The existing `MediaRequestProfile.DEFAULT` is therefore the truthful offline profile until live evidence requires a dedicated one. / 上游使用不带平台 header 的普通 GET 下载小红书 note 媒体，因此在真人证据要求专用 profile 前，现有 `MediaRequestProfile.DEFAULT` 是诚实的离线选择。

## Acceptance boundary / 验收边界

1. The creator result contains exactly one matching source row. It is `type="video"`, has exactly one VIDEO Asset at position zero, has zero or one IMAGE Asset, contains no other Asset kind, and retains exact content/author/source-hint identity. / 作者结果只包含一条匹配来源行；该行必须是 `type="video"`，包含 position 0 的唯一 VIDEO Asset、零或一张 IMAGE Asset，不含其他 Asset kind，并保持精确 content/author/source-hint 身份。
2. The video locator is ordinary `http` or `https`, has no userinfo, non-default port or fragment, has a non-empty path, and its normalized hostname is `xhscdn.com` or a subdomain. Exactly one candidate is accepted; fallback codec/quality arrays with multiple candidates are rejected. / 视频 locator 只能是普通 `http` 或 `https`，不得含 userinfo、非默认端口或 fragment，必须具有非空路径，规范化 hostname 必须是 `xhscdn.com` 或其子域。只接受唯一候选；包含多个候选的 fallback 编解码/清晰度数组会被拒绝。
3. Exact Subscription creator authority, bounded lookup, preflight-before-mutation, explicit note override precedence and valid VERIFIED zero-secret replay remain unchanged from Execution 0017. / 精确 Subscription 作者权限、有界查找、变更前 preflight、显式 note 覆盖优先及有效 VERIFIED 零 secret 重放继续沿用 Execution 0017 的契约。
4. Synthetic MP4 plus optional PNG bytes traverse mock public DNS/HTTP, `MediaRequestProfile.DEFAULT`, mandatory controlled `ffprobe`, SHA-256 archives and idempotent Emby `.mp4`/poster/NFO/source publication. Query-only replay performs no second detail, HTTP, DNS or probe call. / 合成 MP4 与可选 PNG 字节贯穿 mock 公网 DNS/HTTP、`MediaRequestProfile.DEFAULT`、强制受控 `ffprobe`、SHA-256 归档及幂等 Emby `.mp4`/poster/NFO/source 发布；仅 query 变化的重放不得再次调用 detail、HTTP、DNS 或 probe。
5. Signed creator/note authority and media query/fragment values remain transient. Durable XHS raw and Asset hints stay query-free, completed attempt roots are removed, and `.upstream` remains unmodified and untracked. / 带签名的作者/note 权限及媒体 query/fragment 值保持瞬态；持久 XHS raw 与 Asset hint 保持无 query，已完成 attempt root 被删除，`.upstream` 保持未修改且不纳入跟踪。

## Explicit exclusions / 明确排除

- Real QR/Cookie login, creator/feed/detail traffic, real XHS CDN bytes and real Emby/Jellyfin scan/playback remain `NOT_RUN` without user credentials and services. / 在没有用户凭据与服务时，真人 QR/Cookie 登录、creator/feed/detail 流量、真实小红书 CDN 字节及真实 Emby/Jellyfin 扫描/播放保持 `NOT_RUN`。
- More than one cover/image, multiple video variants, H.265/AV1 selection, DASH/HLS manifests, live photo, animation, audio extraction, subtitles, comments, media-version replacement and platform-specific headers remain deferred. / 多于一张封面/图片、多个视频变体、H.265/AV1 选择、DASH/HLS manifest、实况照片、动图、音频提取、字幕、评论、媒体版本替换及平台专用 header 继续延期。
- Tieba/Zhihu media shims, creator pagination hardening, authority-expiry recovery and cross-Asset refresh caching remain future work. The broader seven-platform goal stays active. / 贴吧/知乎媒体 shim、作者分页加固、权限过期恢复及跨 Asset 刷新缓存仍为后续工作；更大的七平台目标继续推进。
