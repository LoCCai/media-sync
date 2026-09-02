# Execution 0027 progress / 执行 0027 推进记录

- Status / 状态：Frozen offline scope and implementation verification complete / 冻结离线范围与实现验证完成
- Last updated / 最近更新：2026-09-02
- Predecessor / 前置：`245e8e377761ee8343b33f581dfcd27295eac532`
- Plan commit / 计划提交：`ec7095a9cc5e85fda1aee66f256eb16345c1294a`
- Implementation commit / 实现提交：`7f99aa480328a25b7e9c2acc8a9c2234128e7b74`

## Implemented / 已实现

- [x] Reconciled Execution 0026, audited both pinned upstreams without modifying them, and froze a no-migration, exactly-one-segment, stream-copy-only contract. / 已核对 Execution 0026，在不修改两个锁定上游的前提下完成审计，并冻结无需 migration、精确单段、仅 stream-copy 的契约。
- [x] Upgraded the bounded detail protocol to v7 and classified only an explicit closed top-level playback `format`: absent/`None` and MP4 remain ordinary progressive, FLV creates a typed target, while unknown, mixed and malformed values fail closed. / 已把有界详情协议升级到 v7，并只分类显式封闭的顶层播放 `format`：缺失/`None` 与 MP4 保持普通 progressive，FLV 构造类型化 target，未知、混合与畸形值关闭失败。
- [x] Added repr-safe `ResolvedFlvLocator`, single-page and multipart private format bridges, collision detection and recursive stripping; historical primary-only and primary-plus-backup payloads remain compatible. / 已增加 repr-safe `ResolvedFlvLocator`、单 P/多分 P 私有格式桥接、碰撞检测与递归移除；历史仅主地址及主地址加备用 payload 保持兼容。
- [x] Allowlisted structurally probed video-bearing FLV and added fixed non-shell single-input ffmpeg remux arguments selecting the first video plus optional first audio stream, with timeout, output, media-size and file-identity bounds. / 已允许结构化探测为含视频流的 FLV，并增加固定、非 shell 的单输入 ffmpeg 转封装参数，选择首个视频流与可选首个音频流，同时约束超时、输出、媒体大小及文件身份。
- [x] Added a generation-scoped `bili-flv-source` store and downloader branch reusing ordered primary/backups, strict Range/validator continuity, whole-pass restart and one all-auth adapter refresh; refresh type drift fails closed. / 已增加 generation-scoped `bili-flv-source` store 与下载分支，复用有序主/备用、严格 Range/validator 连续、整轮 restart 与一次全鉴权 adapter 刷新；刷新类型漂移关闭失败。
- [x] Required the source to probe exactly as FLV video and the final exactly as MP4 video; only the final MP4 reaches SHA-256 archive/Emby, while remux/final-probe failure retains the verified source and discards an unprepared final. / 已要求源精确探测为 FLV 视频、成品精确探测为 MP4 视频；只有 MP4 成品进入 SHA-256 归档/Emby，转封装/成品探测失败会保留已验证源并丢弃未准备成品。
- [x] Preserved published-final recovery and cleanup across source/final stores, and added focused coverage for locator/profile/repr, format bridges, FLV probe, exact remux argv, candidate/auth behavior, type/container drift, source retention and recovery. / 已保持已发布成品恢复及源/成品 store 清理，并增加专项覆盖 locator/profile/repr、格式桥接、FLV 探测、精确转封装参数、候选/鉴权行为、类型/容器漂移、源保留与恢复。
- [x] Added a real local H.264+AAC FLV composition: SQLite → exact detail → primary `503` → backup FLV → production ffprobe → production ffmpeg stream-copy → final ffprobe → SHA-256 MP4 archive → Emby MP4/NFO/source; replay adds zero detail/DNS/HTTP/probe/ffmpeg/archive/export work. / 已增加本地真实 H.264+AAC FLV 组合：SQLite → 精确详情 → 主地址 `503` → 备用 FLV → 生产 ffprobe → 生产 ffmpeg stream-copy → 最终 ffprobe → SHA-256 MP4 归档 → Emby MP4/NFO/source；重放不新增 detail/DNS/HTTP/probe/ffmpeg/archive/export 工作。
- [x] Passed focused `394`, Bilibili compositions `4`, complete `1848 + 1 skip`, Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository gates; pushed and reconciled the bilingual plan and implementation commits. / 已通过专项 `394`、Bilibili 组合 `4`、完整 `1848 + 1 skip`、Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与仓库门禁；双语计划与实现提交已推送并核对。

## Remaining / 待实现

Multiple `durl` segments and ordered FLV concatenation, transcoding/codec repair, CDN ranking/racing/cross-run cache, fresh-detail refresh after mixed/non-auth exhaustion, subtitles/danmaku, pages above 64, bangumi/paid/live media, broader platform shapes, REST/production packaging and every live account/API/CDN/media-server row remain deferred or `NOT_RUN`; the broader seven-platform goal stays active. / 多 `durl` 分段与有序 FLV 拼接、转码/编码修复、CDN 排序/竞速/跨运行缓存、混合/非鉴权穷尽后的新详情刷新、字幕/弹幕、超过 64 个分 P、番剧/付费/直播媒体、更广平台形状、REST/生产打包及全部真人账户/API/CDN/媒体服务器行继续延期或保持 `NOT_RUN`；更大的七平台目标保持进行中。
