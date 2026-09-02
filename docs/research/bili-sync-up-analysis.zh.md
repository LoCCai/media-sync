[English](bili-sync-up-analysis.md) | **中文**

# bili-sync-up 专项审计

- 仓库：`https://github.com/NeeYoonc/bili-sync-up`
- Commit：`dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`
- 工作区版本：`3.0.9`
- 许可证：MIT

本报告来自只读源码审计，没有运行 Rust 构建/测试，因此没有生成上游 `target/` 或运行数据。以下路径均相对于 `.upstream/bili-sync-up`。

## 架构与工作流

项目组合 Rust/Tokio 后端、Axum API/WebSocket、SeaORM/SQLite 和 Svelte 管理界面。启动时执行迁移、恢复断点/任务，然后监督 HTTP、凭据刷新和周期同步。

```text
source summary -> detail/pages -> media and sidecars -> retry this round's failures
```

摘要每批落库，风控中断前已取数据仍被保留；即使没有新内容，也会修复未完成详情、分页和边车。相关入口位于 `crates/bili_sync/src/workflow.rs:1179-1395,1538-1751` 和 `crates/bili_sync/src/task/video_downloader.rs:446-610,900-1027`。

Submission 来源会持久化“最新行、下次扫描、连续失败”状态（`crates/bili_sync_entity/src/entities/submission.rs:7-50`），并提供 checkpoint 辅助（`crates/bili_sync/src/utils/submission_checkpoint.rs:1-114`）。其增量能力高度依赖发布时间（`crates/bili_sync/src/adapter/submission.rs:59-129`）；`media-sync` 额外增加平台 ID 去重与重叠窗口，以处理相同时间戳与迟到内容。

## 登录凭据

- 支持手动 Cookie 与二维码登录。
- 二维码挑战 180 秒过期，并区分等待、已扫码、过期与成功状态（`crates/bili_sync/src/bilibili/auth/mod.rs:46-345,389-435`）。
- 凭据刷新实现了 Bilibili refresh/confirm 链（`crates/bili_sync/src/bilibili/credential.rs:75-260`）。
- 调度了每日刷新与扫描时的过期登录恢复（`crates/bili_sync/src/task/video_downloader.rs:261-303,819-899`）。

不得照抄的安全模式：

- 凭据与 `auth_token` JSON 以明文存于 SQLite。
- 配置历史会复制完整的新旧机密值（`crates/bili_sync/src/config/manager.rs:711-805,836-919`）。
- 默认监听 `0.0.0.0:12345`，且多个凭据/二维码路由绕过鉴权（`crates/bili_sync/src/config/mod.rs:96-97`；`crates/bili_sync/src/api/auth.rs:25-47`）。

因此 `media-sync` 只保存机密引用，QR/OTP 材料仅存于内存，默认只监听环回地址，并在持久化与记录日志之前先脱敏。

## 任务状态与恢复

Video/Page 工作使用紧凑的位状态字段，带有限失败次数与特殊的取消终态（`crates/bili_sync/src/utils/status.rs:3-198`）。这样高效但难以演进，因此未被沿用。

通用任务队列声明了 `Processing`，但领取时并不持久化该状态；执行期间记录仍是 `Pending`（`crates/bili_sync/src/task/mod.rs:303-500`）。这在崩溃后带来 at-least-once 恢复，但如果最终状态写入丢失，可能重复已完成的副作用。失败任务只递增计数器，没有可见的调度性重排队。

新设计方案：显式 `leased/running/retry_wait/waiting_auth` 状态、租约过期、稳定幂等键与事务化副作用调度。

## 下载与处理

值得借鉴的点包括流式下载、native/aria2 回退、有界轮询、停滞检测与 FFmpeg stream-copy 合并。重要限制如下：

- 原生下载直接写最终路径，没有跨重启续传、`.part` 原子提交或 SHA-256（`crates/bili_sync/src/downloader.rs:175-298,514-549`）。
- aria2 设置 `continue=true`，但启动前会删除目标文件，使跨任务续传不可靠（`crates/bili_sync/src/aria2_downloader.rs:1011-1030,1143-1165`）。
- 调试日志可能包含完整的签名媒体 URL（`crates/bili_sync/src/aria2_downloader.rs:1138-1141`）。
- DASH 下载使用 `tmp_video/tmp_audio` 与 FFmpeg 合并并在失败时清理（`crates/bili_sync/src/workflow.rs:8493-8577`），但输出不经过原子暂存。
- FLV 转封装失败时，原始 FLV 可能被重命名为 `.mp4` 路径，使扩展名与容器不一致（`crates/bili_sync/src/workflow.rs:8444-8469`）。

新设计方案：`.part` 加 Range 续传、内容/MIME/大小校验、SHA-256、ffprobe、暂存合并输出、原子替换，且绝不记录签名 URL。

## Emby/Jellyfin 价值

最值得复用的设计证据是它的边车覆盖：

- 根目录：`tvshow.nfo`、poster/folder/thumb/fanart 图。
- 季：`Season XX/season.nfo` 与季图。
- 集：同主干媒体、NFO、封面、ASS 弹幕与 SRT 字幕。
- 创作者/人物：`folder.jpg` 与 `person.nfo`。

NFO 变体覆盖 `movie`、`tvshow`、`episodedetails`、`season` 与 `person`（`crates/bili_sync/src/utils/nfo.rs:13-20,210-237`）。剧集输出包含标题、剧情、季/集、稳定 ID、日期、时长、创作者与图（`crates/bili_sync/src/utils/nfo.rs:1030-1326`）。工作流入口位于 `crates/bili_sync/src/workflow.rs:10084-10710`。

`media-sync` 独立重实现了带命名空间唯一 ID 的平台无关 XML 生成、canonical 归档与确定性导出指纹。如果后续实际复制或大幅改编其 MIT 源码，必须更新 [`THIRD_PARTY_NOTICES.zh.md`](../../THIRD_PARTY_NOTICES.zh.md) 中的受影响路径与完整声明。

## 测试与交付证据

- Rust 工具链锁定在 `1.97.1`（`rust-toolchain.toml:1-2`）。
- 静态搜索发现约 245 个 Rust 测试属性，集中在 workflow、API、NFO 与工具模块。
- 未发现前端 `*.test.*` 或 `*.spec.*` 文件。
- 构建工作流只编译产物/镜像，不运行 `cargo test`、Clippy、fmt 或前端测试（`.github/workflows/build.yml`、`docker-build.yml`）。

## 复用结论

可以借鉴该 MIT 项目的分阶段持久化、凭据刷新、扫描 checkpoint、错误分类与 Emby 边车设计；不要采用其 Bilibili 专用枚举、压缩状态位、明文凭据历史、非原子输出路径或单体工作流。`bili_sync` crate 只暴露二进制目标（`crates/bili_sync/Cargo.toml:88-90`），长期作为 sidecar 运行会重复数据库、任务系统与导出树。
