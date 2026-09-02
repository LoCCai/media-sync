[English](plan.md) | **中文**

# 执行 0038 计划

- 状态：已执行并验证
- 计划日期：2026-09-03
- 前驱：`b9c88c4afab6ba2d9d2a43efea63f63cd6cd31ca`
- 数据库迁移：无计划
- 计划提交：记录于收尾索引；从不嵌入本文件
- 实现提交：记录于收尾索引；从不嵌入本文件

## 基线与审计

执行 0037 在 `b9c88c4` 干净、已推送并对账。锁定小红书 store 把 `image_list` 拍平为图片 URL 逗号拼接并丢弃嵌套的 `live_photo` 流；`update_xhs_note(note_detail)` 接收完整原始 API note，因此微博式边界 shim 可以捕获它们。0017 的 `normal` 类型 creator 分支只接受全 IMAGE 目标，0018/0037 的 `video` 类型分支冻结 `video_url` 标量元组。

实现前记录的基线门禁：0037 专项 `344 passed in 6.32s`、完整 `2020 passed, 1 skipped in 370.56s`、Ruff/格式干净、strict mypy 干净、docs（328 文件）与 upstream（2 个锁定 checkout）通过。

## 交付顺序

1. 新增捕获 shim：一个私有字段携带精确的实况 `master_url`，checkout 校验模块、marker 安全重装与防碰撞，双子进程安装。
2. 为 `_normalize_xhs` 扩展冻结实况分支（MIXED、一 IMAGE 加一 VIDEO、空 `video_url`、恰一张图）并把字段加入递归移除集合。
3. 扩展 creator 回退的 `normal` 类型分支：实况字段存在时接受精确的一图加一视频目标并重校验实况 URL。
4. 通过真实子进程补充契约覆盖（捕获、漂移关闭、仅视频兼容），并为双资产 下载 → 归档 → Emby 零工作重放组合补充集成覆盖。
5. 运行专项与完整套件及全部质量门家族；更新四份执行文档与根事实，然后创建双语实现/收尾提交，推送并对账 GitHub。

## 计划提交顺序

1. 文档基线
2. 实现
3. 文档收尾

`.upstream` 保持排除、未修改且干净。
