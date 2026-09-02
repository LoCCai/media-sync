[English](plan.md) | **中文**

# 执行 0035 计划

- 状态：已执行并验证
- 计划日期：2026-09-03
- 前驱：`3cdd0fc`
- 数据库迁移：无计划
- 计划提交：`ecc08dab850a1e9b4007b4758e7d225f2f7aed15`
- 实现提交：`f2f4bc91790fd0cad30a86a644920824ca03a049`

## 基线与审计

执行 0034 在 `3cdd0fc` 完成（推送因 GitHub TLS 瞬时故障延迟，本执行期间重试）。0031 微博视频捕获只接受标量 `media_info.stream_url`；`playback_list` 帖不捕获并回退 TEXT。封闭 URL 校验器、私有字段管线、VIDEO 归一化与 WB VIDEO 适配器刷新不变且可复用。

实现前记录的基线门禁：0034 专项 `445 passed`、detail 契约 `106 passed in 69.98s`、完整 `2002 passed, 1 skipped in 352.79s`、Ruff/格式干净、strict mypy 干净、docs（304 文件）与 upstream（2 个锁定 checkout）通过。

## 交付顺序

1. 为 `weibo_media.py` 的 `_capture_video` 扩展有界封闭 `playback_list` 回退与画质偏好；标量路径保持第一且字节级兼容。
2. 为选择矩阵（层级优先、未知/缺失画质、无效 URL、超界列表、非列表形状）补充单元覆盖，并通过真实子进程为标量优先、列表选择与关闭补充契约覆盖。
3. 为仅列表帖新增一条集成组合（SQLite → 刷新 → mock DNS/HTTP → MP4 探测 → 归档 → Emby 零工作重放与不泄密）。
4. 运行专项与完整套件，加上 Ruff、format、strict mypy、compileall、build、docs、upstream、diff 与仓库审计；更新四份执行文档与根事实，然后创建双语实现/收尾提交，重试延迟的推送并对账 GitHub。

## 计划提交顺序

1. 文档基线
2. 实现
3. 文档收尾

`.upstream` 保持排除、未修改且干净。
