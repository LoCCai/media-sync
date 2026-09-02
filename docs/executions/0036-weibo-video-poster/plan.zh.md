[English](plan.md) | **中文**

# 执行 0036 计划

- 状态：已执行并验证
- 计划日期：2026-09-03
- 前驱：`5a27e99949c54a5032454d91b8809d28afad7086`
- 数据库迁移：无计划
- 计划提交：记录于收尾索引；从不嵌入本文件
- 实现提交：记录于收尾索引；从不嵌入本文件

## 基线与审计

执行 0035 在 `5a27e99` 干净、已推送并对账。微博 shim 捕获视频 URL（标量或 `playback_list`）但随拍平丢弃 `page_info.pic_info`；0016 图片代理校验器、DY/KS 的 COVER 资产模式与平台无关的 Emby poster 发布均已成熟。`_supported_kinds(WB)` 只覆盖 IMAGE 与 VIDEO。

实现前记录的基线门禁：0035 专项 `451 passed in 74.84s`、微博管线 `4 passed in 2.70s`、完整 `2010 passed, 1 skipped in 360.55s`、Ruff/格式干净、strict mypy 干净、docs（312 文件）与 upstream（2 个锁定 checkout）通过。

## 交付顺序

1. 新增封闭 `validate_weibo_poster_url`（HTTPS `sinaimg.cn` 族 host、静态扩展、有界路径、无 fragment/userinfo/端口），并为 shim 的视频捕获扩展经一个新私有字段（严格防碰撞）携带的 `pic_info.pic_big.url` 通路。
2. 扩展 `_normalize_wb`：合法封面字段在 VIDEO 旁物化 `{note_id}:cover:0` COVER 资产，畸形/双字段漂移隔离，并把该字段加入递归移除集合。
3. 把 `AssetKind.COVER` 加入 WB 刷新支持集合，使封面经一次精确 numeric-note detail 子进程重新解析。
4. 为封面矩阵（标量与 playback 视频旁的有效封面、缺失/畸形/外域/动图漂移、仅视频回退）补充单元/契约覆盖，并为双资产 SQLite → 刷新 → 下载 → 归档 → Emby 零工作重放组合补充集成覆盖。
5. 运行专项与完整套件，加上 Ruff、format、strict mypy、compileall、build、docs、upstream、diff 与仓库审计；更新四份执行文档与根事实，然后创建双语实现/收尾提交，推送并对账 GitHub。

## 计划提交顺序

1. 文档基线
2. 实现
3. 文档收尾

`.upstream` 保持排除、未修改且干净。
