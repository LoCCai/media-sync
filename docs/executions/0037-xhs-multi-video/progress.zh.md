[English](progress.md) | **中文**

# 执行 0037 推进结果

- 状态：冻结的离线小红书多视频范围已实现并通过门禁；真人行保持 `NOT_RUN`
- 日期：2026-09-03
- 计划提交：`d858147`（文档基线）

## 已交付

1. `_normalize_xhs` 现在对视频字段拆分超过 16 个候选的记录隔离，其余保持既有宽容逗号拆分解析；1–16 个候选物化有序 `{note_id}:video:0..N-1` VIDEO 资产。
2. `_validated_xhs_media_scalar` 从精确一个放宽为有界 1–16 有序互异元组，`_validate_xhs_creator_video_target` 现在绑定完整视频元组——数量、position 0..N-1 与精确 URL 顺序——而不再要求 position 0 恰一个视频。
3. 从歧义门移除一个 0018 时代的拒绝参数（两个互异视频 URL），代之以逐 position 接受与漂移覆盖：每个 position 经 creator 回退解析其当前 URL，替换路径以 `locator_refresh_asset_mismatch` 关闭，17 候选标量以 `locator_refresh_schema_changed` 关闭。
4. 集成覆盖：双视频 note 物化两个有界资产、经 DEFAULT profile 与 MP4 探测双下载、归档不同 SHA-256 摘要并发布两个 Emby 集，零工作重放；17 候选记录在归一化期间隔离。

## 验证快照

确切命令、退出码与门禁输出见 [`verification.zh.md`](verification.zh.md)。

## 未完成

实况照片语义、动图漂移、同 ID 字节替换及全部真人验收行继续延期或保持 `NOT_RUN`。
