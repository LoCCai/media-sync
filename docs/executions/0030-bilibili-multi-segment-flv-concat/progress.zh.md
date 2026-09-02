[English](progress.md) | **中文**

# 执行 0030 推进结果

- 状态：冻结的离线多段 FLV 拼接范围已实现并通过门禁；真人行保持 `NOT_RUN`
- 日期：2026-09-02
- 计划提交：`e7395fb`（文档基线）

## 已交付

1. `ResolvedFlvSegmentsLocator` 精确包装一个 `ResolvedSegmentsLocator`；封闭 `ResolvedMediaTarget` 联合类型、导出与 resolver 契约接受它，持久 locator v1 不变。
2. 严格详情协议 v9 只在封闭顶层格式分类加有界 2–64 `durl` 元组下授予多段 FLV 权限；精确一段 FLV、多段普通与 DASH 路径保持字节级兼容。
3. 私有 segments 桥接为单页与多分 P 元组携带精确可选 `"format": "flv"` 标记；既有私有字段仍全部防碰撞，持久化前仍递归移除，重建仍要求 payload CID 精确匹配且漂移关闭失败。
4. 类型化下载分支接受两种分段目标类型：共享字节上限/截止时间下的逐段有序下载与既有候选故障切换、FLV 变体的逐段精确 `flv` 扩展名探测（续传指纹绑定 flavor）、必须返回同类型同分段数的一次全鉴权刷新、一次固定 concat-demuxer `ffmpeg -c copy` 调用、精确 MP4 成品门、不可变发布、已备成品恢复与安全失败保留。
5. 覆盖：类型化 locator 校验、协议 v9 分类、桥接标记/碰撞/畸形 payload、刷新重建、FLV 逐段故障切换/鉴权漂移/探测/成品门语义、失败保留、恢复、清理，以及一条生产级 SQLite → 主地址失败 → 备用 → 双段 FLV 拼接 → SHA-256 MP4 → Emby 重放（零工作重放且不保留原始 FLV）。

## 验证快照

确切命令、退出码与门禁输出见 [`verification.zh.md`](verification.zh.md)。

## 未完成

转码、编解码修复、FLV 分段字节级预拼接、CDN 排序/竞速/跨运行缓存、混合/非鉴权穷尽刷新、字幕/弹幕、超过 64 个分 P、番剧/付费/直播媒体及全部真人验收行继续延期或保持 `NOT_RUN`。
