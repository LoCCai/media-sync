# Execution 0024 goal / 执行 0024 目标

- Status / 状态：Frozen offline scope delivered; live qualification remains `NOT_RUN` / 冻结离线范围已交付；真人验收保持 `NOT_RUN`
- Date / 日期：2026-09-02
- Predecessor / 前置：Execution 0023 closeout `d4c9941d2d5fb1206cd9b1a60ce2cc344a9e66e3`
- Plan commit / 计划提交：`a7d038e383c76f2c29825c6f42ac7ff29b967693`
- Implementation commit / 实现提交：`12314b927dcaac97dc9ae184c03f98153f3ef687`
- Scope / 范围：Ordinary numeric-aid Bilibili single-page and 2–64-page DASH video/audio selection, bounded component download, ffmpeg stream-copy mux and existing Emby/Jellyfin publication / 普通 numeric-aid Bilibili 单 P 与 2–64 分 P 的 DASH 音视频选择、有界组件下载、ffmpeg stream-copy 合并及既有 Emby/Jellyfin 发布

## Outcome / 目标结果

Extend the delivered Bilibili progressive path with a durable DASH lifecycle rather than a parser-only result. For each unresolved Bilibili VIDEO Asset, the exact target CID is refreshed against the complete persisted page tuple, the best supported video and optional audio streams are selected in memory, generation-scoped components are downloaded and structurally verified, ffmpeg stream-copies them into one verified media file, and only that final file enters the immutable SHA-256 archive and Emby/Jellyfin tree. Existing single-progressive behavior remains compatible. / 在已交付的 Bilibili progressive 链路上增加持久 DASH 生命周期，而不是只增加解析器。每个尚未解析的 Bilibili VIDEO Asset 都以完整持久分 P 元组约束其精确目标 CID，在内存中选择最佳受支持视频流与可选音频流，以 generation 为作用域下载并结构校验组件，再由 ffmpeg 以 stream-copy 合并为一个已验证媒体文件；只有最终文件进入不可变 SHA-256 归档与 Emby/Jellyfin 目录。既有单 progressive 行为保持兼容。

## Frozen acceptance boundary / 冻结验收边界

1. The strict detail child requests `/x/player/wbi/playurl` with WBI signing, `avid`, the exact target `cid`, `qn=127`, `fourk=1`, `fnval=4048` and `platform=pc`. The complete current 1–64 page tuple must still match persisted VIDEO siblings before any target is returned. / 严格详情 child 以 WBI 签名请求 `/x/player/wbi/playurl`，携带 `avid`、精确目标 `cid`、`qn=127`、`fourk=1`、`fnval=4048` 与 `platform=pc`；返回任何目标前，当前完整 1–64 分 P 元组仍必须匹配持久 VIDEO 兄弟项。
2. A DASH result selects the highest supported video quality from `16,32,64,80,112,116,120,125,126,127`, then prefers AVC, HEVC and AV1 in that order at equal quality. It selects the highest supported ordinary, Dolby or Hi-Res audio using the pinned bili-sync-up ordering; no audio is a valid silent-video shape. / DASH 结果从 `16,32,64,80,112,116,120,125,126,127` 中选择最高受支持视频质量，同质量时依次偏好 AVC、HEVC、AV1；音频按锁定 bili-sync-up 的顺序从普通、Dolby 或 Hi-Res 中选择最高受支持项；无音频是有效的无声视频形状。
3. Signed primary/component URLs and private play fields remain ephemeral and repr-safe. They are stripped before normalized raw persistence and never written to SQLite, job payloads, archive metadata, export metadata or retained runtime trees. / 签名主 URL、组件 URL 与私有播放字段保持瞬态且 repr-safe；它们在归一化 raw 持久化前被移除，绝不写入 SQLite、Job payload、归档元数据、导出元数据或保留运行目录。
4. DASH video and optional audio use distinct generation-scoped resumable work files beneath the existing exact asset lock. Each component is structurally probed, their combined bytes remain within the asset limit, ffmpeg runs with fixed argv, bounded time/output and `-c copy`, and the muxed result is probed again before archive publication. / DASH 视频与可选音频在既有精确 Asset 锁下使用互异、generation-scoped 的可恢复工作文件；每个组件均接受结构探测，组件总字节受 Asset 上限约束，ffmpeg 以固定 argv、有界时间/输出及 `-c copy` 运行，合并结果在归档发布前再次探测。
5. Crash/retry behavior is closed: incomplete mux output is never published, verified components may resume, a published final blob plus prepared final sidecar can recover database finalization without detail/DNS/HTTP/ffmpeg work, and outward success cleans final/component work state. / 崩溃与重试行为闭合：未完成合并输出绝不发布，已校验组件可恢复续传，已发布最终 blob 加已准备最终 sidecar 可在不执行 detail/DNS/HTTP/ffmpeg 的情况下恢复数据库收尾，对外成功会清理最终/组件工作状态。
6. A DASH result with audio publishes one muxed VIDEO Asset; a silent DASH result publishes one remuxed VIDEO Asset; a progressive `durl` result continues through the existing downloader unchanged. Single-page and 2–64-page Emby primary/part naming stays deterministic. / 带音频的 DASH 结果发布一个合并 VIDEO Asset；无声 DASH 结果发布一个 remux VIDEO Asset；progressive `durl` 结果继续原样经过既有下载器。单 P 与 2–64 分 P 的 Emby 主媒体/part 命名保持确定性。
7. The pinned upstream checkouts remain unmodified and clean. All implementation belongs to `media-sync`, with source/unit/contract/integration evidence and bilingual local Git history pushed to GitHub. / 两个锁定上游 checkout 保持未修改且干净；全部实现位于 `media-sync`，具备源码/单元/合约/集成证据，并以双语本地 Git 历史推送至 GitHub。

## Explicit exclusions / 明确排除

Backup-CDN failover, multiple progressive `durl` segments, FLV remux, subtitles, danmaku, configurable quality policy, pages above 64, bangumi/paid/live media, real account/API/CDN behavior and real Emby/Jellyfin scan/playback remain deferred or `NOT_RUN`. This execution does not claim complete Bilibili support. / 备用 CDN 故障切换、多段 progressive `durl`、FLV remux、字幕、弹幕、可配置质量策略、超过 64 个分 P、番剧/付费/直播媒体、真实账户/API/CDN 行为及真实 Emby/Jellyfin 扫描/播放继续延期或保持 `NOT_RUN`；本执行不宣称完整 Bilibili 支持。
