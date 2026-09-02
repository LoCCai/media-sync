[English](plan.md) | **中文**

# 执行 0037 计划

- 状态：已执行并验证
- 计划日期：2026-09-03
- 前驱：`145176f8624f5c1518b6cd28cea3f9aa3d938454`
- 数据库迁移：无计划
- 计划提交：`d858147`
- 实现提交：`c5682e5`

## 基线与审计

执行 0036 在 `145176f` 干净、已推送并对账。锁定小红书 store 把 `get_video_url_arr` 拼接进标量 `video_url`，`_url_list` 已在归一化期间拆分为有序 VIDEO 资产，且定时 fixture 依赖该宽容度支持非 CDN fixture host。0018 的 detail 刷新契约冻结精确一个视频：`_validated_xhs_media_scalar` 拒绝 `len(candidates) != 1`，`_validate_xhs_creator_video_target` 要求 position 0 恰一个视频资产。

实现前记录的基线门禁：0036 专项 `341 passed in 4.29s`、完整 `2016 passed, 1 skipped in 370.47s`、Ruff/格式干净、strict mypy 干净、docs（320 文件）与 upstream（2 个锁定 checkout）通过。

## 交付顺序

1. 归一化加界：`_normalize_xhs` 对视频字段拆分超过 16 个候选的记录隔离，其余保持既有宽容解析。
2. 把 `_validated_xhs_media_scalar` 放宽为有界 1–16 有序互异元组，并把 `_validate_xhs_creator_video_target` 放宽为绑定完整视频元组（数量、position 0..N-1、精确 URL 顺序）。
3. 补充单元/契约覆盖：1/2/16 视频物化与刷新绑定、17 视频隔离、替换/重排路径漂移关闭。
4. 为双视频 note 新增一条集成组合（SQLite → 刷新 → 双下载 → 归档 → Emby 零工作重放与不泄密）。
5. 运行专项与完整套件及全部质量门家族；更新四份执行文档与根事实，然后创建双语实现/收尾提交，推送并对账 GitHub。

## 计划提交顺序

1. 文档基线
2. 实现
3. 文档收尾

`.upstream` 保持排除、未修改且干净。
