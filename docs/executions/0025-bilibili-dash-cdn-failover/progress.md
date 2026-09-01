# Execution 0025 progress / 执行 0025 推进记录

- Status / 状态：Frozen offline scope and documentation closeout complete / 冻结离线范围与文档收尾完成
- Last updated / 最近更新：2026-09-02
- Predecessor / 前置：`46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- Plan commit / 计划提交：`8e9467d2ecbedfd8f87e8d1d2ffb5a66d6d15591`
- Implementation commit / 实现提交：`fe45abcb7262c3d70437aff82a05609e43902af4`

## Completed / 已完成

- [x] Reconciled the Execution 0024 closeout and audited the ephemeral target, component sidecar, strict resume, probe/mux/archive and recovery boundaries. / 已核对 Execution 0024 收尾，并审计瞬态 target、组件 sidecar、严格续传、探测/合并/归档及恢复边界。
- [x] Verified that primary plus at most eight distinct backup candidates were already validated, repr-safe and runtime-only; audited pinned bili-sync-up ordering without modifying either checkout. / 已确认“主地址 + 最多八个互异备用候选”已完成校验、repr-safe 且只存在于运行时；已审计锁定 bili-sync-up 的顺序，且未修改任何 checkout。
- [x] Added a DASH-only primary-first candidate pass for video and optional audio under the existing asset lock, component byte cap and shared total deadline. / 已在既有 Asset 锁、组件字节上限及共享总截止时间下，为 DASH 视频与可选音频增加仅 DASH、主地址优先的候选轮次。
- [x] Limited failover to candidate-local DNS, timeout, transport, interruption, HTTP status and Range incompatibility outcomes. Network-policy, header/encoding, chunk/size, filesystem, probe and mux failures remain immediate. / 已把故障切换限制为候选局部 DNS、timeout、传输、中断、HTTP 状态及 Range 不兼容结果；网络策略、header/encoding、chunk/size、文件系统、探测及合并失败继续立即失败。
- [x] Reloaded partial state between candidates and required exact Range offset, total length and validator continuity. A partial survives mixed candidate failures; destructive restart occurs only after the complete candidate pass rejects it. / 已在候选间重新加载 partial 状态，并要求 Range offset、总长度与 validator 完全连续；混合候选失败时 partial 保留，只有完整候选轮次均拒绝时才执行破坏性 restart。
- [x] Preserved all-candidate `401`/`403` exhaustion as `locator_refresh_auth_expired`, returned only fixed redaction-safe errors otherwise and retained no URL, host or winning index. / 已保持全部候选 `401`/`403` 穷尽结果为 `locator_refresh_auth_expired`，其他情况只返回固定脱敏错误，且不保留 URL、host 或胜出序号。
- [x] Added 17 DASH-downloader unit cases covering primary short-circuit, ordered video/audio fallback, DNS fallback, exhaustion, fail-closed security/size limits, cross-candidate resume, partial preservation and whole-pass restart. / 已增加 17 个 DASH 下载器单元用例，覆盖主地址短路、有序视频/音频 fallback、DNS fallback、穷尽、网络安全/大小上限关闭失败、跨候选续传、partial 保留及整轮 restart。
- [x] Extended the production integration composition so video primary `503` and audio primary `403` fall back independently to real local H.264/AAC components, then pass ffprobe → ffmpeg → final ffprobe → SHA-256 archive → Emby dual-stream publication and zero-work replay. / 已扩展生产集成组合：视频主地址 `503`、音频主地址 `403` 后独立切换到本地真实 H.264/AAC 组件，再贯穿 ffprobe → ffmpeg → 最终 ffprobe → SHA-256 归档 → Emby 双流发布与零工作重放。
- [x] Proved signed primary/backup candidates and private play fields absent from retained SQLite, Job, runtime, work, archive and export artifacts. / 已证明签名主/备用候选与私有播放字段不存在于保留 SQLite、Job、runtime、work、归档与导出产物中。
- [x] Passed focused `466`, complete `1790 + 1 skip`, production-process, Ruff, format, strict mypy, compileall, build, docs, upstream, diff and repository audit gates. / 已通过专项 `466`、完整 `1790 + 1 skip`、生产进程、Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与仓库审计门。
- [x] Created and pushed bilingual plan and implementation commits; aligned root truth documents for this closeout. / 已创建并推送双语计划与实现提交；本次收尾已对齐根真值文档。

## Remaining outside this execution / 本执行外待实现

Progressive backup failover, segmented progressive media, CDN sorting/racing/cache, fresh-detail retry, FLV, subtitles/danmaku, configurable quality policy and broader Bilibili/live qualification remain deferred; the broader seven-platform goal stays active. / Progressive 备用故障切换、分段 progressive、CDN 排序/竞速/缓存、新详情重试、FLV、字幕/弹幕、可配置质量策略及更广 Bilibili/现网验收继续延期；更大的七平台目标保持进行中。
