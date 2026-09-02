[English](progress.md) | **中文**

# 执行 0032 推进结果

- 状态：冻结的离线有界抖音图集范围已实现并通过门禁；真人行保持 `NOT_RUN`
- 日期：2026-09-02
- 计划提交：`286dac9`（文档基线）

## 已交付

1. 严格 `_dy_note_images` 解析器冻结锁定的逗号拼接 `note_download_url` 形状：接受字符串或 JSON 冻结序列输入，逐项校验字符串/无内嵌逗号/合法 URL，封闭重复处理与 1–64 边界；漂移抛出 `RecordNormalizationError` 而非静默丢弃子项，空/缺失字段保持为空。
2. `_normalize_dy` 现物化 `ContentKind.IMAGE`（一张）或 `ContentKind.GALLERY`（2–64）及有序 `{aweme_id}:image:0..N-1` IMAGE 资产；video/music/cover 字段保持既有宽容解析、锁定爬虫的图片优先选择不变，0015 单视频/音频/文本形状保持字节级兼容。
3. 既有逐资产适配器刷新对图集 position 完成验收：一次精确 numeric-ID detail 运行在内存中重新解析每个 position 的当前签名 URL，路径漂移以 `locator_refresh_asset_mismatch` 关闭。
4. 覆盖：1/2/64 张图的摄取契约物化、65 张边界与逐项漂移；两个 position 与路径漂移的刷新覆盖；一条生产级 SQLite → detail 刷新 → mock DNS/HTTP → 静态 PNG sniff 门 → SHA-256 归档 → Emby poster/backdrop/gallery/NFO 组合并零工作重放。
5. 持久状态只保留无 query 提示；detail 签名、其哨兵与两个签名 URL 不出现在任何留存的 runtime/work/archive/export/library 树或 SQLite 产物中。

## 验证快照

确切命令、退出码与门禁输出见 [`verification.zh.md`](verification.zh.md)。

## 未完成

视频+图片混合 Asset 语义、图集关联音乐、静态门之外的动图漂移、同 ID 字节替换、有界作者分页、专用 CDN header、清理失败 quarantine 及全部真人验收行继续延期或保持 `NOT_RUN`。
