[English](goal.md) | **中文**

# 执行 0039 目标

- 状态：冻结的离线小红书多图实况 gallery 范围已完成；真人行保持 `NOT_RUN`
- 日期：2026-09-03
- 前驱：执行 0038 收尾 `064bdb1d4ab493ec2b31afb96a29032a8b939b2d`
- 范围：一条普通小红书 `type="normal"` note，其 2–16 个 `image_list` 条目各携带实况照片，在锁定 store 边界捕获全部被丢弃的 H.264 主流并交付为有界的成对 IMAGE+VIDEO gallery
- 计划提交：记录于收尾索引；从不嵌入本文件
- 实现提交：记录于收尾索引；从不嵌入本文件

## 结果

1. 为锁定实况 shim 扩展 v2 列表捕获：2–16 张图的 `type="normal"` note 且每张图都携带冻结的 `live_photo.stream.h264[0].master_url` 形状时，捕获完整有序 URL 元组；任一图无合法实况、嵌套畸形或超界列表不捕获。
2. 物化 `ContentKind.MIXED`：有序 `{note_id}:image:0..N-1` IMAGE 与 `{note_id}:video:0..N-1` VIDEO 资产；0038 单图形状字节级兼容，畸形 payload 隔离关闭失败。
3. 扩展 creator 回退的 `normal` 类型分支以绑定精确成对 gallery（相等数量、有序 position、重校验实况 URL）；任何漂移关闭失败。
4. 每个资产经 DEFAULT profile 下载（静态图门与 MP4 门）、SHA-256 归档并发布确定性 Emby 带海报剧集，零工作重放。
5. 证明契约与集成组合，同时全部真实账户/API/CDN/媒体服务器行保持 `NOT_RUN`。

## 验收边界

- 只有精确冻结的全图实况配对嵌套形状授予 gallery；部分实况覆盖不捕获（不静默降级）。
- `video_url` 标量必须为空；0017 静态、0018/0037 视频与 0038 单实况形状保持不变。
- 无数据库 schema 或迁移；稳定 Asset 身份不变。`.upstream` 保持只读且不入库。

## 明确延期

H.265 偏好、实况时长、动图漂移及全部真人验收行均不属于本执行。
