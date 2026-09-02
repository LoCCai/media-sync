[English](progress.md) | **中文**

# 执行 0023 推进记录

- 状态：冻结离线范围与文档收尾完成
- 最近更新：2026-09-02
- 前置：`27e45c89f20e8eb6bc871ab1505fe25167b70ae3`
- 计划提交：`bd45478b28cc61a7f35b6211faf3a0fc1eb94138`
- 实现提交：`24fd41c600eb30fb2df22079e3cf52778589959e`

## 已完成

- 已在 Execution 0022 收尾点核对干净的本地/tracking/GitHub `main`。
- 已审计当前 normalizer、详情 child、刷新、下载器、归档与 Emby 多 part 布局边界。
- 已审计锁定 MediaCrawler 的 `View.pages`/`get_video_play_url(aid,cid)` 与 bili-sync-up 的 PageInfo/DASH/ffmpeg 行为。
- 已把有界多分 P progressive 与后续 DASH 衍生物生命周期拆分，并冻结 2–64 分 P 验收边界。
- 已增加校验、任务局部的 forward shim，在锁定 store 丢弃前捕获规范 1–64 项 `page`/`cid`；畸形、重复、不连续与 65 分 P 声明均关闭失败。
- 已保留精确单 P `<aid>:video:0` 兼容，并为合格 2–64 分 P 投稿输出有序 `<aid>:video:cid:<cid>`、仅 locator 的 VIDEO Asset。
- 已把严格详情协议升级至 v4 并增加 `bili_video_cid`；每次刷新只请求目标 CID，并绑定完整当前 VIDEO 兄弟元组。
- 已在返回 URL 前拒绝缺失、新增、重排、替换、重复或畸形的当前分 P 元组；持久化前递归移除私有分 P/播放字段与签名 URL。
- 已证明三分 P SQLite → 定向详情 → Bilibili-profile DNS/HTTP → 探测 → SHA-256 归档 → Emby 主媒体/两个 part/NFO/source 的不同字节组合。
- 已证明仅 query 变化的重放不新增 detail、DNS、HTTP、probe、archive 或 export 工作。
- 专项回归通过 `436 passed in 53.96s`；完整套件通过 `1739 passed, 1 skipped in 321.25s`；全部质量/构建/文档/上游/审计门通过。
- 已推送实现 `24fd41c`；本地、tracking 与 GitHub `main` 已核对一致。

## 本执行外待实现

DASH 合并与恢复、分段 progressive 媒体、字幕/弹幕、备用故障切换、更广 Bilibili 类型及全部登录/现网验收行继续延期或保持 `NOT_RUN`；更大的目标保持进行中。
