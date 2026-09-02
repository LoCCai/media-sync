[English](plan.md) | **中文**

# 执行 0027 计划

- 状态：已执行并通过验证
- 计划日期：2026-09-02
- 前置：`245e8e377761ee8343b33f581dfcd27295eac532`
- 数据库迁移：计划无
- 计划提交：`ec7095a9cc5e85fda1aee66f256eb16345c1294a`
- 实现提交：`7f99aa480328a25b7e9c2acc8a9c2234128e7b74`

## 基线与审计

Execution 0026 在 `245e8e3` 保持干净并已核对。严格 v6 详情路径接受精确一个 progressive `durl`，瞬态传递其主/备用地址，并在结构探测后直接发布下载字节。`FFprobeMediaProbe` 当前未将 FLV 加入允许列表，`ResolvedMediaTarget` 没有格式感知 progressive 衍生类型，`FFmpegStreamCopyMuxer` 可合并 DASH 视频与可选外部音频，却不能从一个混合输入保留可选音频。CLI 与 pipeline 已要求 Bilibili adapter-refresh VIDEO 工作具备可启动 ffmpeg，因此无需新增操作员能力开关。

锁定 MediaCrawler 下载器选择最大的 `durl` 项并直接写为 `.mp4`，不修复格式。锁定 bili-sync-up analyzer 识别顶层 format 中的 `flv`，仍只选择 `durl[0]`，并用 ffmpeg 转封装混合 FLV。两个 checkout 均只作为只读设计证据；两者都不提供后续目标的多段契约。基线门禁为 Execution 0026 专项 `490 passed in 73.31s`、完整 `1814 passed, 1 skipped in 342.33s`、收尾单 P/多分 P/DASH 组合 `1.45s`/`1.70s`/`1.87s`、120 份 Markdown、两个锁定且干净的 checkout、308 个跟踪文件，以及零未跟踪/runtime/upstream/dist 跟踪文件。

## 交付顺序

1. 增加一个 repr-safe 瞬态 FLV target，包装一个 Bilibili profile `ResolvedLocator`；扩展封闭运行时 union、刷新校验及导出，同时不改变持久 locator v1。
2. 把详情协议升级到 v7，只分类封闭的顶层 FLV format，并通过单 P 与多分 P payload 传递精确私有格式标记，同时加入碰撞检测与递归移除。
3. 扩展归一化器与惰性刷新，使历史仅主地址/主加备用 progressive payload 继续为普通类型，而合法 FLV 标记重建类型化瞬态 target；schema 漂移关闭失败。
4. 将结构化探测通过的 FLV 视频加入允许列表，增加固定参数单输入转封装并保留视频与可选音频，同时约束输入/输出文件身份、字节上限、超时及有界 child 输出。
5. 增加 generation-scoped FLV 源 store 与类型化下载分支，复用有序候选故障切换、严格续传及一次全鉴权刷新，探测源、转封装一次，只探测/发布成品，并保持安全恢复/清理行为。
6. 增加单元/合约覆盖：格式分类、私有桥接、repr/不保留、FLV 探测/转封装参数、候选/鉴权行为、失败保留、已准备成品恢复及向后兼容。
7. 增加生产 ffmpeg/ffprobe 的 SQLite → 主地址失败 → 备用 FLV → 转封装 MP4 → SHA-256 归档 → Emby 组合与零工作重放；不保留签名 URL、原始 FLV 发布或私有标记。
8. 运行专项与完整套件，以及 Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与仓库审计；更新执行四件套与根真值，再创建双语实现/收尾提交，推送并核对 GitHub。

## 计划提交序列

1. 文档基线 — `docs: 启动 Bilibili 单段 FLV 转封装 / start Bilibili single-segment FLV remux`
2. 实现 — `feat: 闭环 Bilibili 单段 FLV 转封装 / close Bilibili single-segment FLV remux`
3. 文档收尾 — `docs: 收尾 Bilibili 单段 FLV 转封装 / close Bilibili single-segment FLV remux`

`.upstream` 继续排除在跟踪外、保持未修改且干净。
