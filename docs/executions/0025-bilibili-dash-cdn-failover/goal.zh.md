[English](goal.md) | **中文**

# 执行 0025 目标

- 状态：冻结离线范围已交付；真人验收保持 `NOT_RUN`
- 日期：2026-09-02
- 前置：Execution 0024 closeout `46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- 计划提交：`8e9467d2ecbedfd8f87e8d1d2ffb5a66d6d15591`
- 实现提交：`fe45abcb7262c3d70437aff82a05609e43902af4`
- 范围：对已选择的瞬态 Bilibili DASH 视频与可选音频组件执行有序、有界的主 CDN → 备用 CDN 故障切换

## 目标结果

把执行 0024 已校验但尚未使用的 DASH 备用 URL 接入封闭下载生命周期。每个已选择的视频/音频组件都在既有 Asset 锁、总截止时间、字节上限、请求 profile 与结构门下，按来源顺序尝试主 URL 及最多八个已校验备用 URL。只有严格 Range、总长度与强 validator 证据证明字节连续时，部分组件才可跨候选续传。候选 URL、选中序号及远端失败细节均不得持久化。

## 冻结验收边界

1. 故障切换只适用于 `ResolvedDashLocator.video` 与可选 `.audio`。每个组件使用既有 `ResolvedLocator.urls` 顺序：先主地址，再零至八个互异且已校验的备用地址；主地址成功时不得产生备用地址 DNS 或 HTTP 工作。
2. 单轮候选尝试受既有组件候选数与共享的 `DownloadLimits.total_timeout_seconds` 约束。候选局部 DNS、传输、中断、HTTP 状态及 Range 不兼容失败可推进到下一候选；安全策略、header/encoding、chunk/size、文件系统、探测与合并失败立即失败。
3. 候选只有在 validator 类型/值、总长度及请求 offset 与现有 partial 完全一致时才可追加。非空 partial 遇到返回完整 `200`、不兼容 `206` 或不兼容 `416` 的候选时，在尝试后续候选前不得丢弃既有证据；只有全部候选均不兼容后，既有有界 restart 策略才可丢弃 partial 并启动全新候选轮次。
4. 仍有其他 URL 时，`401`/`403` 属于候选局部失败。若一轮中每个已尝试候选都返回 `401`/`403`，继续返回既有脱敏错误 `locator_refresh_auth_expired`；否则穷尽后返回最后一个合格的脱敏失败，不披露 URL 或 host。
5. 视频与音频独立故障切换。备用组件成功后仍必须经过与主组件相同的结构探测、组合字节上限、固定有界 `ffmpeg -c copy`、成品探测、SHA-256 归档发布及确定性 Emby/Jellyfin 导出。
6. 签名主/备用 URL 继续保持 repr-safe 且只存在于运行时。SQLite、Job payload、partial sidecar、归档/导出元数据、保留运行目录、异常及运维输出均不得保留候选值或胜出候选序号。
7. 既有无备用地址、无声 DASH、progressive 单 P/多分 P、合并失败及已发布成品恢复行为保持兼容；两个锁定上游 checkout 保持未修改且干净。

## 明确排除

Progressive `durl` 备用地址故障切换、多段 progressive、可配置 CDN 排序/评分、并行竞速、跨运行坏 CDN 缓存、候选穷尽后的新详情重试、FLV、字幕/弹幕、超过 64 个分 P、真实 Bilibili 账户/API/CDN 行为及真实 Emby/Jellyfin 扫描/播放继续延期或保持 `NOT_RUN`。本执行不宣称完整 Bilibili 或通用 CDN 故障切换支持。
