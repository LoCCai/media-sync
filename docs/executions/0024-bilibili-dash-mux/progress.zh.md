[English](progress.md) | **中文**

# 执行 0024 推进记录

- 状态：冻结离线范围与文档收尾完成
- 最近更新：2026-09-02
- 前置：`d4c9941d2d5fb1206cd9b1a60ce2cc344a9e66e3`
- 计划提交：`a7d038e383c76f2c29825c6f42ac7ff29b967693`
- 实现提交：`12314b927dcaac97dc9ae184c03f98153f3ef687`

## 已完成

- 已核对 Execution 0023 收尾，审计详情/刷新/下载/归档/Emby 边界，并冻结无迁移的 DASH 生命周期。
- 已审计锁定 MediaCrawler progressive 请求与 bili-sync-up 的 DASH 画质、编码、音频、无声视频及 ffmpeg 行为，且未修改任何 checkout。
- 已增加 repr-safe 的瞬态 single/DASH target 与有界备用 URL 表达；签名组件 URL 均不可持久化。
- 已把严格详情协议升级到 v5，并以 `avid`、目标 `cid`、`qn=127`、`fourk=1`、`fnval=4048` 与 `platform=pc` 发起精确 WBI 请求；progressive fallback 保持兼容。
- 已实现严格受支持流选择：最高视频画质，同画质 AVC → HEV → AV1，以及锁定的普通/杜比/Hi-Res 音频顺序，并支持合法无声形状。
- 已通过内存 JSONL 归一化携带一个类型化私有 target，将其绑定到精确当前分 P/CID 兄弟元组，并在形成持久 raw 前递归移除全部私有字段。
- 已增加 generation-scoped 视频/音频组件 store、严格 Range 续传、组件与成品结构探测、组合字节限制、固定参数且有界的 ffmpeg stream-copy 合并器，以及仅成品进入不可变归档的发布路径。
- 已闭合失败与重启行为：中断组件可续传，合并失败保留已验证组件，不完整成品不可发布，已准备且已发布的成品无需 detail/DNS/HTTP/ffmpeg 即可恢复，对外成功会清理该 generation 的全部工作文件。
- 已把 ffmpeg 接入独立下载与订阅 pipeline 组合，增加 doctor 可见性，并使待处理 Bilibili refresh VIDEO 在缺少合并能力时于持久 child 工作前失败。
- 已证明真实离线 SQLite → 签名组件 HTTP → 生产 ffprobe → 生产 ffmpeg → 成品 ffprobe → SHA-256 归档 → Emby/NFO/source 组合；成品同时含音视频流，且签名 target 数据零留存。
- 最终专项回归通过 `456 passed in 66.47s`；完整套件通过 `1780 passed, 1 skipped in 333.43s`；全部质量/构建/文档/上游/diff 审计通过。
- 已推送双语实现提交 `12314b9`；文档收尾前本地与 tracking `main` 已核对一致。

## 本执行外待实现

备用 CDN 故障切换、分段 progressive、FLV remux、字幕/弹幕、可配置画质策略、超过 64 个分 P、更广 Bilibili/番剧/付费/直播媒体，以及全部真人登录/API/CDN/Emby/Jellyfin 行继续延期或保持 `NOT_RUN`；更大的七平台目标保持进行中。
