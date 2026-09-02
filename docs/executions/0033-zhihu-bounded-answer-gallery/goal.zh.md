[English](goal.md) | **中文**

# 执行 0033 目标

- 状态：冻结的离线知乎回答有界图集范围已完成；真人行保持 `NOT_RUN`
- 日期：2026-09-03
- 前驱：执行 0032 收尾 `41508b1cc57672aa9e18252498d10d98bc371b90`
- 范围：HTML 含 2–64 张有序静态图片的普通知乎回答，在锁定 extractor 边界捕获，交付为兄弟绑定的有界 IMAGE 图集
- 计划提交：`92651bca24b026e6d2c920d48eddac9fb111e7ae`
- 实现提交：`966ccef562c207e4c77abb3d6828fdf12714988e`

## 结果

1. 扩展锁定知乎 extractor shim：恰一张图的普通回答保持 0019 v1 捕获字节级兼容；2–64 张有序图片——每张按冻结的 `data-original` → `data-actualsrc` → `src` 属性优先级选出、静态合法且两两互异——捕获为一个完整有序元组；任何禁用媒体漂移、无效或重复图片、超过 64 张的图集不捕获。
2. 元组置于一个新的私有 v2 字段下：与 v1 字段严格防碰撞、持久化前递归移除，归一化物化为 ARTICLE 与 `{content_id}:image:0..N-1` IMAGE 资产。
3. 惰性适配器刷新绑定完整持久兄弟元组：刷新上下文携带有序无 query 提示，一次精确 canonical-answer detail 运行在内存中重新解析每个 position 的当前 URL，任何缺失、新增、重排、替换、重复或畸形漂移以 `locator_refresh_schema_changed` 关闭。
4. 每个 position 经 DEFAULT-profile 候选轮次下载，含结构化静态图门、SHA-256 归档与确定性 Emby poster/backdrop/gallery/body/NFO/source 发布，支持零工作重放。
5. 以一条生产级 SQLite → detail 刷新 → mock DNS/HTTP → 静态探测 → 归档 → Emby 组合证明全链路，同时全部真实账户/API/CDN/媒体服务器行保持 `NOT_RUN`。

## 验收边界

- 精确以冻结属性优先级与封闭 zhimg 静态图校验器决定资格；0019 单图语义、禁用媒体拒绝与无媒体回答的 TEXT 回退保持字节级兼容。
- 超过 64 张的图集与混合禁用媒体的回答不捕获而非截断。
- 无数据库 schema 或迁移；稳定 Asset 身份不变。`.upstream` 保持只读且不入库。

## 明确延期

文章、zvideo、静态门之外的动图/WebP 动图漂移、同 ID 字节替换、有界作者分页变更、更丰富 HTML 媒体及全部真人验收行均不属于本执行。
