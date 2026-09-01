# Execution 0025 goal / 执行 0025 目标

- Status / 状态：Frozen offline scope delivered; live qualification remains `NOT_RUN` / 冻结离线范围已交付；真人验收保持 `NOT_RUN`
- Date / 日期：2026-09-02
- Predecessor / 前置：Execution 0024 closeout `46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- Plan commit / 计划提交：`8e9467d2ecbedfd8f87e8d1d2ffb5a66d6d15591`
- Implementation commit / 实现提交：`fe45abcb7262c3d70437aff82a05609e43902af4`
- Scope / 范围：Ordered, bounded primary-to-backup CDN failover for the already-selected ephemeral Bilibili DASH video and optional audio components / 对已选择的瞬态 Bilibili DASH 视频与可选音频组件执行有序、有界的主 CDN → 备用 CDN 故障切换

## Outcome / 目标结果

Turn the validated but unused DASH backup URLs delivered by execution 0024 into a closed download lifecycle. Each selected video/audio component tries its primary URL and then at most eight validated backups in source order under the existing asset lock, total deadline, byte limit, request profile and structural gates. A partial component may cross candidates only when strict Range, total-length and strong-validator evidence proves byte continuity. No candidate URL, selected index or remote failure detail becomes durable. / 把执行 0024 已校验但尚未使用的 DASH 备用 URL 接入封闭下载生命周期。每个已选择的视频/音频组件都在既有 Asset 锁、总截止时间、字节上限、请求 profile 与结构门下，按来源顺序尝试主 URL 及最多八个已校验备用 URL。只有严格 Range、总长度与强 validator 证据证明字节连续时，部分组件才可跨候选续传。候选 URL、选中序号及远端失败细节均不得持久化。

## Frozen acceptance boundary / 冻结验收边界

1. Failover applies only to `ResolvedDashLocator.video` and optional `.audio`. Each component uses the existing `ResolvedLocator.urls` order: primary first, followed by zero to eight distinct validated backups; a primary success performs no backup DNS or HTTP work. / 故障切换只适用于 `ResolvedDashLocator.video` 与可选 `.audio`。每个组件使用既有 `ResolvedLocator.urls` 顺序：先主地址，再零至八个互异且已校验的备用地址；主地址成功时不得产生备用地址 DNS 或 HTTP 工作。
2. One candidate pass is bounded by the existing component candidate count and one shared `DownloadLimits.total_timeout_seconds`. Candidate-local DNS, transport, interruption, HTTP status and Range incompatibility failures may advance to the next candidate; security-policy, header/encoding, chunk/size, filesystem, probe and mux failures fail immediately. / 单轮候选尝试受既有组件候选数与共享的 `DownloadLimits.total_timeout_seconds` 约束。候选局部 DNS、传输、中断、HTTP 状态及 Range 不兼容失败可推进到下一候选；安全策略、header/encoding、chunk/size、文件系统、探测与合并失败立即失败。
3. A candidate may append to an existing partial only with the exact existing validator kind/value, total length and requested offset. A candidate that returns full `200`, incompatible `206` or incompatible `416` for a non-empty partial cannot discard that evidence before later candidates are tried. Only after every candidate is incompatible may the existing bounded restart policy discard the partial and start a fresh candidate pass. / 候选只有在 validator 类型/值、总长度及请求 offset 与现有 partial 完全一致时才可追加。非空 partial 遇到返回完整 `200`、不兼容 `206` 或不兼容 `416` 的候选时，在尝试后续候选前不得丢弃既有证据；只有全部候选均不兼容后，既有有界 restart 策略才可丢弃 partial 并启动全新候选轮次。
4. `401`/`403` are candidate-local while another URL remains. If every attempted candidate in a pass returns `401`/`403`, the existing redaction-safe `locator_refresh_auth_expired` result is preserved; otherwise exhaustion returns the last eligible redaction-safe failure without URL or host disclosure. / 仍有其他 URL 时，`401`/`403` 属于候选局部失败。若一轮中每个已尝试候选都返回 `401`/`403`，继续返回既有脱敏错误 `locator_refresh_auth_expired`；否则穷尽后返回最后一个合格的脱敏失败，不披露 URL 或 host。
5. Video and audio fail over independently. A successful backup component still undergoes the same structural probe, combined byte cap, fixed bounded `ffmpeg -c copy`, final probe, SHA-256 archive publication and deterministic Emby/Jellyfin export as a primary component. / 视频与音频独立故障切换。备用组件成功后仍必须经过与主组件相同的结构探测、组合字节上限、固定有界 `ffmpeg -c copy`、成品探测、SHA-256 归档发布及确定性 Emby/Jellyfin 导出。
6. Signed primary/backup URLs remain repr-safe and runtime-only. SQLite, Job payloads, partial sidecars, archive/export metadata, retained runtime trees, exceptions and operator-facing output retain neither candidate values nor the winning candidate index. / 签名主/备用 URL 继续保持 repr-safe 且只存在于运行时。SQLite、Job payload、partial sidecar、归档/导出元数据、保留运行目录、异常及运维输出均不得保留候选值或胜出候选序号。
7. Existing no-backup, silent DASH, progressive single-/multi-page, failed-mux and published-final recovery behavior remains compatible. Both pinned upstream checkouts remain unmodified and clean. / 既有无备用地址、无声 DASH、progressive 单 P/多分 P、合并失败及已发布成品恢复行为保持兼容；两个锁定上游 checkout 保持未修改且干净。

## Explicit exclusions / 明确排除

Progressive `durl` backup failover, multiple progressive segments, configurable CDN sorting/scoring, parallel racing, cross-run bad-CDN caches, fresh-detail retry after candidate exhaustion, FLV, subtitles/danmaku, pages above 64, real Bilibili account/API/CDN behavior and real Emby/Jellyfin scan/playback remain deferred or `NOT_RUN`. This execution does not claim complete Bilibili or general-purpose CDN failover support. / Progressive `durl` 备用地址故障切换、多段 progressive、可配置 CDN 排序/评分、并行竞速、跨运行坏 CDN 缓存、候选穷尽后的新详情重试、FLV、字幕/弹幕、超过 64 个分 P、真实 Bilibili 账户/API/CDN 行为及真实 Emby/Jellyfin 扫描/播放继续延期或保持 `NOT_RUN`。本执行不宣称完整 Bilibili 或通用 CDN 故障切换支持。
