[English](plan.md) | **中文**

# 执行 0033 计划

- 状态：已执行并验证
- 计划日期：2026-09-03
- 前驱：`41508b1cc57672aa9e18252498d10d98bc371b90`
- 数据库迁移：无计划
- 计划提交：`92651bca24b026e6d2c920d48eddac9fb111e7ae`
- 实现提交：`966ccef562c207e4c77abb3d6828fdf12714988e`

## 基线与审计

执行 0032 在 `41508b1` 干净、已推送并对账。0019 知乎 shim 已按冻结属性优先级解析全部 `<img>` 候选并拒绝禁用媒体，但只捕获恰一张图的形状；多图回答回退 TEXT。贴吧 0020–0022 的兄弟提示刷新绑定（上下文元组、应用层兄弟组装、精确漂移关闭）是成熟模板，静态图门、逐资产刷新、SHA-256 归档与 Emby gallery 发布均平台无关。

实现前记录的基线门禁：0032 专项 `316 passed in 5.09s`、DB 摄取契约 `25 passed in 2.64s`、完整 `1971 passed, 1 skipped in 390.84s`、Ruff/格式干净、strict mypy 干净、docs（288 文件）与 upstream（2 个锁定 checkout）通过。

## 交付顺序

1. 为 `_capture_answer` 扩展有界 2–64 有序元组通路（逐图属性优先级选择、静态校验、两两互异）及一个与 v1 严格防碰撞的新私有 v2 字段。
2. 为 `_normalize_zhihu` 扩展 v2 分支（精确字符串列表形状、2–64 边界、完整重校验、双字段隔离）并把该字段加入递归移除集合。
3. 镜像贴吧兄弟绑定：`MediaCrawlerRefreshContext` 携带 `zhihu_image_source_hints`，应用层从 SQLite 组装并校验完整兄弟元组，刷新器把缺失/新增/重排/替换/重复漂移以 `locator_refresh_schema_changed` 关闭，v1 单图行为保持等价。
4. 为捕获矩阵（1/2/64 捕获，65/无效/重复/禁用媒体不捕获）、归一化结局、刷新绑定与漂移、真实子进程组合与持久不泄密补充单元/契约覆盖。
5. 新增一条生产级 SQLite → 刷新 → mock DNS/HTTP → 静态 JPEG/PNG 探测 → SHA-256 归档 → Emby poster/backdrop/gallery/body/NFO/source 组合并零工作重放。
6. 运行专项与完整套件，加上 Ruff、format、strict mypy、compileall、build、docs、upstream、diff 与仓库审计；更新四份执行文档与根事实，然后创建双语实现/收尾提交，推送并对账 GitHub。

## 计划提交顺序

1. 文档基线
2. 实现
3. 文档收尾

`.upstream` 保持排除、未修改且干净。
