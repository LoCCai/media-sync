# Execution 0027 goal / 执行 0027 目标

- Status / 状态：Complete for the frozen offline single-segment FLV-remux scope; live rows remain `NOT_RUN` / 冻结的离线单段 FLV 转封装范围已完成；真人行保持 `NOT_RUN`
- Date / 日期：2026-09-02
- Predecessor / 前置：Execution 0026 closeout `245e8e377761ee8343b33f581dfcd27295eac532`
- Scope / 范围：Format-aware, bounded stream-copy remux of the already-supported exactly-one-segment Bilibili progressive `durl` FLV shape into an Emby-compatible MP4 / 对既有“精确一个分段”的 Bilibili progressive `durl` FLV 形状执行格式感知、有界 stream-copy 转封装，产出 Emby 兼容 MP4
- Plan commit / 计划提交：`ec7095a9cc5e85fda1aee66f256eb16345c1294a`
- Implementation commit / 实现提交：`7f99aa480328a25b7e9c2acc8a9c2234128e7b74`

## Outcome / 目标结果

1. Upgrade the strict detail process protocol to v7 and distinguish an explicitly declared FLV `durl` from the compatible ordinary progressive path without persisting format authority or signed URLs. / 把严格详情进程协议升级到 v7，在不持久化格式权限或签名 URL 的前提下区分显式声明的 FLV `durl` 与兼容普通 progressive 路径。
2. Carry one repr-safe ephemeral FLV target containing the existing ordered primary plus at most eight backups through the single-page and multipart private bridges; historical payloads without the new format marker remain compatible. / 通过单 P 与多分 P 私有桥接传递一个 repr-safe 瞬态 FLV target，其中沿用有序主地址及最多八个备用地址；不含新格式标记的历史 payload 保持兼容。
3. Download the FLV source with the proven candidate-pass, strict resume, whole-pass restart and one all-auth adapter refresh semantics, then require structural FLV probing before any remux. / 使用已验证候选轮次、严格续传、整轮 restart 及一次全鉴权 adapter 刷新语义下载 FLV 源，并在任何转封装前强制执行结构化 FLV 探测。
4. Run fixed-argument, bounded `ffmpeg -c copy` remux preserving the first video and optional first audio stream; require final production-compatible probing and publish only the MP4 final to SHA-256 archive and Emby layout. / 运行固定参数、有界 `ffmpeg -c copy` 转封装，保留首个视频流与可选首个音频流；强制最终生产兼容探测，并只把 MP4 成品发布到 SHA-256 归档与 Emby 布局。
5. Keep the generation-scoped FLV source resumable after remux/probe failure, prevent incomplete finals from recovery, and preserve published-final recovery plus zero-work replay. / 转封装/探测失败后保留 generation-scoped FLV 源以便续用，禁止不完整成品进入恢复，并保持已发布成品恢复与零工作重放。
6. Prove a real local FLV → MP4 ffmpeg/ffprobe composition and retained-tree non-disclosure while keeping all real account/API/CDN/media-server rows `NOT_RUN`. / 以本地真实 FLV → MP4 ffmpeg/ffprobe 组合及保留树不披露证据完成证明，同时全部真人账户/API/CDN/媒体服务器行保持 `NOT_RUN`。

## Acceptance boundaries / 验收边界

- Exactly one `durl` segment remains required. Multiple segments, concatenation and per-segment ordering/size semantics are not claimed. / 继续要求精确一个 `durl` 分段；不声明支持多段、拼接及逐段顺序/大小语义。
- FLV is detected only from the closed top-level playback format contract; URL suffixes, response MIME and downloaded bytes cannot grant FLV authority. / FLV 只由封闭的顶层播放格式契约识别；URL 后缀、响应 MIME 与下载字节均不能授予 FLV 权限。
- The source must structurally probe as FLV video, and the final must structurally probe as MP4 video. No transcoding, codec repair, subtitle/danmaku embedding or fallback publication of raw FLV is allowed. / 源必须结构化探测为 FLV 视频，成品必须结构化探测为 MP4 视频；不允许转码、编码修复、字幕/弹幕嵌入或原始 FLV 降级发布。
- Source and final bytes share the existing asset byte cap and deadline. ffmpeg output is bounded, fixed-argv and non-shell. / 源与成品共用既有 Asset 字节上限与截止时间；ffmpeg 输出有界、参数固定且不经过 shell。
- No database schema or migration is planned; stable Asset identity and the twelve frozen media-shape count do not change. / 不计划数据库 schema 或 migration；稳定 Asset 身份与十二个冻结媒体形状计数均不变化。
- `.upstream` remains read-only and untracked. / `.upstream` 继续只读且不纳入跟踪。

## Explicitly deferred / 明确延期

Multiple `durl` segments, FLV concatenation, transcoding, CDN ranking/racing/cross-run cache, mixed/non-auth exhaustion refresh, subtitles/danmaku, pages above 64, bangumi/paid/live media, broader platform shapes, REST/production packaging and every live qualification row remain outside this execution. / 多 `durl` 分段、FLV 拼接、转码、CDN 排序/竞速/跨运行缓存、混合/非鉴权穷尽刷新、字幕/弹幕、超过 64 个分 P、番剧/付费/直播媒体、更广平台形状、REST/生产打包及全部真人验收行均不在本执行范围内。
