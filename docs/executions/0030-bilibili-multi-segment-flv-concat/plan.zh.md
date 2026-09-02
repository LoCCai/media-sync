[English](plan.md) | **中文**

# 执行 0030 计划

- 状态：已执行并验证
- 计划日期：2026-09-02
- 前驱：`dbd06075eac67377a911b503de9aa609fdc30c79`
- 数据库迁移：无计划
- 计划提交：`e7395fb41a4c11cd59548bd0f95f7bc2d5b5b04e`
- 实现提交：`564f80f7dca04ee5a8acb79797833238fb376004`

## 基线与审计

执行 0029 在 `dbd0607` 干净、已推送并对账。严格 v8 详情路径接受有界普通多段 `durl` 元组，并把顶层 FLV 格式且多段关闭为不支持；类型化下载分支要求每段精确 MP4 探测与一次固定拼接调用。`FFprobeMediaProbe` 已允许 FLV 视频，`FFmpegStreamCopyMuxer.concat` 已具备 concat-demuxer 形态，分段 `_PartStore` 角色与尝试内脚本处理均已就位。

锁定的 MediaCrawler 下载器仍只选取一个 `durl` 条目；锁定的 bili-sync-up 分析器也只取 `durl[0]`。两个 checkout 保持只读设计证据。实现前记录的基线门禁：0029 专项 `447 passed in 70.97s`、完整 `1902 passed, 1 skipped in 409.85s`、Bilibili 组合 `5 passed in 10.93s`、Ruff/格式干净、strict mypy 干净、docs（260 文件）与 upstream（2 个锁定 checkout）通过。

## 交付顺序

1. 新增 repr-safe 瞬态 `ResolvedFlvSegmentsLocator` 包装一个 `ResolvedSegmentsLocator`；扩展封闭运行时联合类型、导出与 resolver 契约，不改变持久 locator v1。
2. 把详情协议升级到 v9：有界有序 `durl` 元组且顶层格式分类为 FLV 时产出类型化 FLV 分段目标；精确一段、多段普通与 DASH 路径保持字节级兼容。
3. 在 segments payload 内扩展精确可选 `"format": "flv"` 标记；保持与全部既有私有字段的严格防碰撞、持久化前递归移除、精确 payload CID 绑定与重建漂移关闭失败。
4. 把类型化下载分支泛化为接受两种分段目标类型：共享字节上限与截止时间下的逐段有序下载、FLV 变体的逐段精确 `flv` 扩展名探测、必须返回同类型同分段数的一次全鉴权刷新、一次固定 concat-demuxer `ffmpeg -c copy` 调用、精确 MP4 成品门、不可变发布、已备成品恢复与安全失败保留。
5. 为类型化 locator、协议 v9 分类、桥接标记/碰撞/移除、刷新重建、逐段故障切换/鉴权漂移/预算/探测语义、失败保留、恢复、清理与向后兼容补充单元/契约覆盖。
6. 新增生产 ffmpeg/ffprobe 的 SQLite → 主地址失败 → 备用 → 双段 FLV 拼接 → SHA-256 MP4 归档 → Emby 组合并零工作重放；不保留签名 URL、原始 FLV 分段或私有标记。
7. 运行专项与完整套件，加上 Ruff、format、strict mypy、compileall、build、docs、upstream、diff 与仓库审计；更新四份执行文档与根事实，然后创建双语实现/收尾提交，推送并对账 GitHub。

## 计划提交顺序

1. 文档基线
2. 实现
3. 文档收尾

`.upstream` 保持排除、未修改且干净。
