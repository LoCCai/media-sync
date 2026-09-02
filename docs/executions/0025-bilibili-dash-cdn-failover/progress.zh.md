[English](progress.md) | **中文**

# 执行 0025 推进记录

- 状态：冻结离线范围与文档收尾完成
- 最近更新：2026-09-02
- 前置：`46905a50bbba19b7c4b74a0f7a274d5efdb013d6`
- 计划提交：`8e9467d2ecbedfd8f87e8d1d2ffb5a66d6d15591`
- 实现提交：`fe45abcb7262c3d70437aff82a05609e43902af4`

## 已完成

- 已核对 Execution 0024 收尾，并审计瞬态 target、组件 sidecar、严格续传、探测/合并/归档及恢复边界。
- 已确认“主地址 + 最多八个互异备用候选”已完成校验、repr-safe 且只存在于运行时；已审计锁定 bili-sync-up 的顺序，且未修改任何 checkout。
- 已在既有 Asset 锁、组件字节上限及共享总截止时间下，为 DASH 视频与可选音频增加仅 DASH、主地址优先的候选轮次。
- 已把故障切换限制为候选局部 DNS、timeout、传输、中断、HTTP 状态及 Range 不兼容结果；网络策略、header/encoding、chunk/size、文件系统、探测及合并失败继续立即失败。
- 已在候选间重新加载 partial 状态，并要求 Range offset、总长度与 validator 完全连续；混合候选失败时 partial 保留，只有完整候选轮次均拒绝时才执行破坏性 restart。
- 已保持全部候选 `401`/`403` 穷尽结果为 `locator_refresh_auth_expired`，其他情况只返回固定脱敏错误，且不保留 URL、host 或胜出序号。
- 已增加 17 个 DASH 下载器单元用例，覆盖主地址短路、有序视频/音频 fallback、DNS fallback、穷尽、网络安全/大小上限关闭失败、跨候选续传、partial 保留及整轮 restart。
- 已扩展生产集成组合：视频主地址 `503`、音频主地址 `403` 后独立切换到本地真实 H.264/AAC 组件，再贯穿 ffprobe → ffmpeg → 最终 ffprobe → SHA-256 归档 → Emby 双流发布与零工作重放。
- 已证明签名主/备用候选与私有播放字段不存在于保留 SQLite、Job、runtime、work、归档与导出产物中。
- 已通过专项 `466`、完整 `1790 + 1 skip`、生产进程、Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与仓库审计门。
- 已创建并推送双语计划与实现提交；本次收尾已对齐根真值文档。

## 本执行外待实现

Progressive 备用故障切换、分段 progressive、CDN 排序/竞速/缓存、新详情重试、FLV、字幕/弹幕、可配置质量策略及更广 Bilibili/现网验收继续延期；更大的七平台目标保持进行中。
