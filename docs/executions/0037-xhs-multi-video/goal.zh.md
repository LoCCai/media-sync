[English](goal.md) | **中文**

# 执行 0037 目标

- 状态：冻结的离线小红书多视频范围已完成；真人行保持 `NOT_RUN`
- 日期：2026-09-03
- 前驱：执行 0036 收尾 `145176f8624f5c1518b6cd28cea3f9aa3d938454`
- 范围：一条普通小红书 `type="video"` note，其锁定 store 把有序多视频列表拼接进标量 `video_url`，交付为带逐 position 适配器刷新的有界 1–16 VIDEO 资产元组
- 计划提交：记录于收尾索引；从不嵌入本文件
- 实现提交：记录于收尾索引；从不嵌入本文件

## 结果

1. 把逗号拼接的 `video_url` 标量冻结为有界有序多视频形状：1–16 个两两互异候选，每个都校验为合法 `xhscdn.com` HTTP(S) URL，零或一个图片伴随保持不变。
2. 物化有序 `{note_id}:video:0..N-1` VIDEO 资产（加可选 position-0 IMAGE），超界记录隔离关闭失败；0017/0018 单视频语义字节级兼容。
3. 把 creator 回退刷新绑定到完整有序视频元组：`_validated_xhs_media_scalar` 接受有界列表，`_validate_xhs_creator_video_target` 要求 fresh 资产精确复现数量、顺序、position 与 URL，每个 position 经既有 detail 权限重新解析，路径漂移关闭失败。
4. 每个 position 经 DEFAULT-profile 候选轮次下载，含 MP4 探测、SHA-256 归档与确定性 Emby 多集发布，零工作重放。
5. 为双视频 note 证明契约与集成组合，同时全部真实账户/API/CDN/媒体服务器行保持 `NOT_RUN`。

## 验收边界

- 只有带有序互异候选的冻结逗号拼接标量授予元组；重复、内嵌漂移、超界列表与 schema 漂移隔离或关闭失败。
- 0017/0018 的定时摄取 URL 宽容度与图片伴随语义不变；只有 detail 刷新契约从精确一个放宽为有界元组。
- 无数据库 schema 或迁移；稳定 Asset 身份不变。`.upstream` 保持只读且不入库。

## 明确延期

实况照片语义、动图漂移、同 ID 字节替换、有界作者分页变更、专用 CDN header 及全部真人验收行均不属于本执行。
