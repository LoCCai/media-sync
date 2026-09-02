[English](progress.md) | **中文**

# 执行 0029 推进结果

- 状态：冻结的离线多段普通 `durl` 范围已实现并通过门禁；真人行保持 `NOT_RUN`
- 日期：2026-09-02
- 计划提交：`9a40968`（文档基线）

## 已交付

1. `ResolvedSegmentsLocator`（2–64 个有序、主地址两两互异的 Bilibili-profile 分段）扩展封闭 `ResolvedMediaTarget` 联合类型、导出与 resolver 契约；持久 locator v1 不变。
2. 严格详情协议 v8 接受有界有序 `durl` 元组；DASH 保持优先，精确一段行为字节级兼容，顶层 FLV 格式且分段数大于一保持 `_ChildUnsupportedError`。
3. 新私有桥接字段 `__media_sync_bili_progressive_segments_v1` 以 `{"cid", "segments": [{"url", "backup_urls"}...]}` 形状同时服务单页与多分 P 页面元组，与全部既有私有字段防碰撞，加入递归移除集合，且仅当 payload CID 与所选分 P 匹配时才重建。
4. `_PartStore` 新增有界分段角色（`bili-segment-000..063`）；`cleanup_partial` 会丢弃全部分段 store 与尝试内的 concat 脚本。
5. 类型化下载分支在共享字节上限/截止时间下按序下载分段，要求每段精确 MP4 结构探测，允许一次必须返回相同分段数的全鉴权刷新，以受控 parts 目录内相对文件名脚本执行一次固定 concat-demuxer `ffmpeg -c copy` 调用，成品门要求精确 MP4，不可变发布并保留已备成品恢复。
6. `FFmpegStreamCopyMuxer.concat` 新增封闭 concat-demuxer argv，含输入/输出身份、大小与有界输出检查。
7. 覆盖：locator 边界/互异性、concat argv/列表/身份/失败、逐段故障切换/鉴权漂移/预算/探测/失败保留/恢复/清理、桥接重建/碰撞/畸形 payload、协议 v8 子进程组合，以及一条生产级 SQLite → 主地址失败 → 备用 → 双段拼接 → SHA-256 归档 → Emby 重放。

## 验证快照

确切命令、退出码与门禁输出见 [`verification.zh.md`](verification.zh.md)。

## 未完成

多段 FLV 拼接/转封装、转码、CDN 排序/竞速/跨运行缓存、混合/非鉴权穷尽刷新、字幕/弹幕、超过 64 个分 P、番剧/付费/直播媒体及全部真人验收行继续延期或保持 `NOT_RUN`。
