# Execution 0016 goal / 执行 0016 目标

- Status / 状态：Planned and baselined; implementation pending / 已完成计划与基线；实现待开始
- Started / 开始时间：2026-08-31
- Predecessor / 前置：Execution 0015 closeout commit `b105d00`
- Plan commit / 计划提交：Pending / 待提交
- Implementation commit / 实现提交：Pending / 待提交

## Outcome / 结果

Close one ordinary original Weibo image-post path from creator discovery through exact detail refresh, image download/probe, immutable SHA-256 archive publication and Emby/Jellyfin image-library output. The frozen accepted shape uses a numeric creator ID, a numeric note ID, no `retweeted_status`, no media `page_info`, and a flat ordered `mblog.pics` list containing one or more dictionary entries with a non-empty `pid` and HTTPS `url`. One picture becomes `ContentKind.IMAGE`; multiple pictures become `ContentKind.GALLERY`; image Assets use positions `0..N-1`. / 收口一条普通原创微博图片帖路径：从作者发现到精确 detail 刷新、图片下载/探测、不可变 SHA-256 归档发布及 Emby/Jellyfin 图片媒体库输出。冻结的可接受形状使用 numeric 作者 ID、numeric note ID，不含 `retweeted_status`，不含媒体 `page_info`，并包含由一个或多个字典项组成的扁平有序 `mblog.pics`；每项具有非空 `pid` 与 HTTPS `url`。单图归一化为 `ContentKind.IMAGE`，多图归一化为 `ContentKind.GALLERY`，图片 Asset position 为 `0..N-1`。

This execution must add media discovery to the creator child as well as detail refresh. Adding detail alone cannot create the initial Asset and exact `AssetRefreshSource` required by the automatic pipeline. / 本执行必须同时为 creator child 增加媒体发现并接通 detail 刷新；只增加 detail 无法创建自动流水线所需的初始 Asset 与精确 `AssetRefreshSource`。

## Design basis / 设计依据

- The pinned MediaCrawler Weibo creator/detail paths receive raw `mblog.pics`, but `store/weibo/__init__.py` drops pictures before JSONL persistence. Creator mode also does not call the upstream image downloader. / 锁定版 MediaCrawler 的微博 creator/detail 路径能收到原始 `mblog.pics`，但 `store/weibo/__init__.py` 在持久化 JSONL 前丢弃图片；creator 模式也不会调用上游图片下载器。
- The pinned client converts a Sina image URL to query-free `https://i1.wp.com/<source-host>/large/<filename>` before downloading. Execution 0016 follows that pinned transformation so the existing closed `DEFAULT` request profile remains applicable without inventing unproven Sina Referer/Cookie headers. / 锁定客户端会在下载前把新浪图片 URL 转换为无 query 的 `https://i1.wp.com/<source-host>/large/<filename>`。执行 0016 沿用该锁定转换，使现有封闭 `DEFAULT` 请求 profile 可继续适用，不虚构未经证明的新浪 Referer/Cookie header。
- The media-sync creator/detail children can install an integration-owned runtime shim after the verified external checkout is imported. The shim must enrich only the JSONL boundary and must never modify the pinned `.upstream` checkout. / media-sync 的 creator/detail child 可在导入已验证的外部 checkout 后安装由本集成拥有的运行时 shim；该 shim 只能增强 JSONL 边界，绝不能修改锁定的 `.upstream` checkout。
- The existing normalized repository, lazy runtime, downloader, image probe, SHA-256 archive and Emby layout are platform-neutral. Once exact Weibo Assets exist, the first image can be poster/backdrop and all images can be emitted as gallery files. / 现有归一化仓储、惰性 runtime、下载器、图片 probe、SHA-256 归档及 Emby layout 均与平台无关。一旦存在精确微博 Asset，首图可成为 poster/backdrop，全部图片可输出为 gallery 文件。

## Acceptance / 验收

1. **Creator discovery / 作者发现** — the real child integration shim captures the supported raw `mblog.pics` shape during creator mode and enriches the corresponding contents JSONL record before sealing. Normalization and SQLite ingestion create exact image Assets, stable adapter refresh locators and exact Account/Subscription-bound `AssetRefreshSource` rows. / 真实 child 集成 shim 在 creator 模式捕获受支持的原始 `mblog.pics` 形状，并在封存前增强对应 contents JSONL。归一化与 SQLite 导入创建精确图片 Asset、稳定 adapter refresh locator 及绑定精确 Account/Subscription 的 `AssetRefreshSource`。
2. **Closed shape and durable boundary / 封闭形状与持久边界** — only ordinary original numeric-ID posts with a flat ordered list of valid `pid` plus HTTPS URL dictionaries emit image Assets. String/nested/missing/duplicate/drifted picture shapes, retweets and `page_info` media fail closed to no image Assets. The integration-private field is absent from durable normalized raw. / 只有普通原创 numeric-ID 帖子中由合法 `pid` 与 HTTPS URL 字典组成的扁平有序列表会产生图片 Asset。字符串/嵌套/缺字段/重复/漂移图片形状、转发及 `page_info` 媒体均关闭失败为不产生图片 Asset；集成私有字段不会进入持久归一化 raw。
3. **Exact detail refresh / 精确 detail 刷新** — the real isolated fake checkout proves `platform=wb`, numeric `WEIBO_SPECIFIED_ID_LIST`, detail/JSONL/media-off/concurrency controls, account/profile scope, bounded framing and normal-success cleanup. Refresh accepts only the exact content/remote ID/kind/position/query-free source hint candidate. / 真实隔离 fake checkout 证明 `platform=wb`、numeric `WEIBO_SPECIFIED_ID_LIST`、detail/JSONL/媒体关闭/并发控制、账户/profile 范围、有界 framing 及正常成功清理。刷新只接受 content/remote ID/kind/position/无 query source hint 全部精确的候选。
4. **Image transfer and Emby publication / 图片传输与 Emby 发布** — deterministic image bytes use `MediaRequestProfile.DEFAULT` without Cookie, Authorization, Referer or Origin, pass public-DNS and image probing controls, finalize under SHA-256 archive paths, and publish poster, backdrop, gallery, NFO and allowlisted source metadata. / 确定性图片字节使用不含 Cookie、Authorization、Referer 或 Origin 的 `MediaRequestProfile.DEFAULT`，通过公网 DNS 与图片探测控制，在 SHA-256 归档路径下收尾，并发布 poster、backdrop、gallery、NFO 与白名单 source 元数据。
5. **Replay and truthfulness / 重放与真实性** — replay of already verified/exported Assets performs no second detail, HTTP, DNS or probe call. Focused and complete offline gates pass. Real login, author scan, detail/CDN bytes and Emby/Jellyfin server validation remain `NOT_RUN`. / 已验证/已导出 Asset 的重放不会第二次调用 detail、HTTP、DNS 或 probe。专项及完整离线门禁通过；真人登录、作者扫描、detail/CDN 字节与 Emby/Jellyfin 服务器验证保持 `NOT_RUN`。

## Explicit exclusions / 明确排除

- Weibo video, `page_info`, live/paid/restricted media, retweets, animated-image semantics, long-image special handling, comments and creator-avatar media. / 微博视频、`page_info`、直播/付费/受限媒体、转发、动图语义、长图特殊处理、评论及作者头像媒体。
- Bounded creator pagination. The pinned Weibo creator client walks full history, so explicit `allow_full_history` plus outer watchdogs remain mandatory. / 有界作者分页；锁定微博 creator client 会遍历完整历史，因此显式 `allow_full_history` 与外层 watchdog 仍为强制要求。
- A Sina-direct CDN profile, third-party proxy availability claims, same-ID media replacement detection, injected cleanup-failure quarantine and every live qualification row. / 新浪直连 CDN profile、第三方代理可用性声明、同 ID 媒体替换检测、注入清理失败 quarantine 及全部真人验收行。
