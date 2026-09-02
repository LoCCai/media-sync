[English](plan.md) | **中文**

# 执行 0032 计划

- 状态：已执行并验证
- 计划日期：2026-09-02
- 前驱：`2e9e3b5378dd8966f56e068dced5f799e115f92b`
- 数据库迁移：无计划
- 计划提交：`286dac9b78710c8fd99e9ec8f260d0fac6d4f5ac`
- 实现提交：`95758c2e6b3623a02f3a035590934da816e3cc6f`

## 基线与审计

执行 0031 在 `2e9e3b5` 干净、已推送并对账。锁定的抖音 store 已把 `_extract_note_image_list` 拼接进标量 `note_download_url`（逗号分隔、每图取无水印 `url_list[-1]`），且 `_normalize_dy` 已把该字段拆分为 IMAGE（一张）或 GALLERY（多张）及 `{aweme_id}:image:{position}` 资产。`_supported_kinds(DY)` 已含 IMAGE，DEFAULT-profile 刷新按资产独立，结构化静态图门与 Emby gallery 发布平台无关；0015 恰好留下有界多图端到端与严格性未验收：现行解析器静默丢弃无效候选且不设图集上界。

实现前记录的基线门禁：0031 专项 `302 passed in 4.04s`、detail 契约 `100 passed in 70.92s`、完整 `1956 passed, 1 skipped in 408.57s`、Ruff/格式干净、strict mypy 干净、docs（280 文件）与 upstream（2 个锁定 checkout）通过。

## 交付顺序

1. 为冻结的逗号拼接形状新增严格 `_dy_note_images` 解析器：接受字符串或 JSON 冻结序列输入，逐项校验字符串/无内嵌逗号/合法 URL，封闭重复处理与 1–64 边界；漂移抛出 `RecordNormalizationError` 而非丢弃子项，空/缺失字段保持为空。
2. video/music/cover 字段保持既有宽容 `_dy_url_list` 解析与锁定爬虫的图片优先选择不变。
3. 为 1/2/64 张图的物化、65 张边界、逐项漂移（非字符串、内嵌逗号、无效 URL、重复）与空字段回退补充摄取契约覆盖。
4. 补充刷新覆盖：每个图集 position 经一次精确 numeric-ID detail 运行重新解析其当前签名 URL，路径漂移关闭失败。
5. 新增一条生产级 SQLite → 刷新 → mock DNS/HTTP → 静态 JPEG/PNG 探测 → SHA-256 归档 → Emby poster/backdrop/gallery/NFO/source 组合并零工作重放与持久不泄密。
6. 运行专项与完整套件，加上 Ruff、format、strict mypy、compileall、build、docs、upstream、diff 与仓库审计；更新四份执行文档与根事实，然后创建双语实现/收尾提交，推送并对账 GitHub。

## 计划提交顺序

1. 文档基线
2. 实现
3. 文档收尾

`.upstream` 保持排除、未修改且干净。
