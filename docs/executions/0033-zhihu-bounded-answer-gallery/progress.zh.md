[English](progress.md) | **中文**

# 执行 0033 推进结果

- 状态：冻结的离线知乎回答有界图集范围已实现并通过门禁；真人行保持 `NOT_RUN`
- 日期：2026-09-03
- 计划提交：`92651bc`（文档基线）

## 已交付

1. `_capture_answer` 现为 2–64 张图片物化一个完整有序元组（逐图冻结属性优先级选择、静态校验、两两互异），恰一张图的形状保持 0019 v1 捕获字节级兼容；禁用媒体、无效或重复图片与超过 64 张的图集不捕获。
2. 一个新的私有 v2 字段携带该元组：与 v1 严格防碰撞、持久化前递归移除，归一化物化为 ARTICLE 与 `{content_id}:image:0..N-1` IMAGE 资产；双字段、畸形、单项与超界 payload 隔离关闭失败。
3. 惰性适配器刷新通过新的 `zhihu_image_source_hints` 上下文字段（由应用层组装并校验）绑定完整持久兄弟元组；缺失、新增、重排、替换或重复漂移以 `locator_refresh_schema_changed` 关闭，v1 单图行为保持等价（一个既有漂移期望从 `asset_mismatch` 更新为兄弟绑定的 `schema_changed`）。
4. 覆盖：经真实子进程的捕获矩阵、归一化结局、刷新绑定与漂移，以及一条生产级 SQLite → detail 刷新 → mock DNS/HTTP → 静态 PNG sniff 门 → SHA-256 归档 → Emby poster/backdrop/两张 gallery 图/body/NFO 组合，零工作重放且持久不泄密。

## 验证快照

确切命令、退出码与门禁输出见 [`verification.zh.md`](verification.zh.md)。

## 未完成

文章、zvideo、静态门之外的动图漂移、同 ID 字节替换、更丰富 HTML 媒体及全部真人验收行继续延期或保持 `NOT_RUN`。
