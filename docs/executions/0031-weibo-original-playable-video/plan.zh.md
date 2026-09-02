[English](plan.md) | **中文**

# 执行 0031 计划

- 状态：已执行并验证
- 计划日期：2026-09-02
- 前驱：`e242b16097b2fb1f0f6ee1dc8e863ace1c68ab32`
- 数据库迁移：无计划
- 计划提交：`1c79c6d94fbca2ac4c01ec1f9c2f6e17da7b6e7d`
- 实现提交：`666438d793c18f97af5026e7506c8ee9745eba47`

## 基线与审计

执行 0030 在 `e242b16` 干净、已推送并对账。锁定的微博 store `update_weibo_note` 只保留文本/指标并丢弃 `page_info`，普通原创视频 locator 正如 0016 之前的 `pics` 一样在 store 边界消失。0016 shim 已在定时与 detail 两个子进程的同一边界安装，`_normalize_wb` 已对残留 `page_info` 关闭失败，WB numeric-note detail 引用已端到端校验，通用适配器刷新已能从 fresh detail 记录返回 DEFAULT-profile locator 且持久层只保留无 query 提示。`FFprobeMediaProbe` 已映射 MP4 视频，下载/Emby 路径对 VIDEO 资产平台无关。

实现前记录的基线门禁：0030 专项 `460 passed in 91.95s`、完整 `1916 passed, 1 skipped in 446.64s`、Ruff/格式干净、strict mypy 干净、docs（272 文件）与 upstream（2 个锁定 checkout）通过。

## 交付顺序

1. 新增封闭的微博视频 URL 校验器与跨越精确对象 store 边界的 `_capture_video` 通路；结果置于一个新私有字段下，并与图片字段严格防碰撞。
2. 为 `_normalize_wb` 增加冻结的 VIDEO 分支（精确 `{"url"}` payload、numeric ID、非转发、不与图片字段共存），并把该字段加入递归私有字段移除集合。
3. 把 `AssetKind.VIDEO` 加入 WB 刷新支持集合，使既有通用刷新路径绑定精确资产、在内存中重新捕获当前签名 URL 并返回 DEFAULT-profile 瞬态 locator。
4. 为校验器、shim 捕获矩阵（转发/page_type/media_info 形状/畸形 URL/双字段）、归一化关闭失败结局、真实子进程刷新组合与持久不泄密补充单元/契约覆盖。
5. 新增一条生产 ffprobe 的 SQLite → detail 刷新 → mock DNS/HTTP → SHA-256 归档 → Emby `.mp4`/NFO/source 组合并零工作重放。
6. 运行专项与完整套件，加上 Ruff、format、strict mypy、compileall、build、docs、upstream、diff 与仓库审计；更新四份执行文档与根事实，然后创建双语实现/收尾提交，推送并对账 GitHub。

## 计划提交顺序

1. 文档基线
2. 实现
3. 文档收尾

`.upstream` 保持排除、未修改且干净。
