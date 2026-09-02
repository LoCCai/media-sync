[English](goal.md) | **中文**

# 执行 0032 目标

- 状态：冻结的离线有界抖音图集范围已完成；真人行保持 `NOT_RUN`
- 日期：2026-09-02
- 前驱：执行 0031 收尾 `2e9e3b5378dd8966f56e068dced5f799e115f92b`
- 范围：一条普通 numeric-ID 抖音 note，其锁定 store 把有序 note 图片列表拼接进标量 `note_download_url`，交付为有界 IMAGE/GALLERY 内容，含逐图适配器刷新、静态探测与 Emby 发布
- 计划提交：`286dac9b78710c8fd99e9ec8f260d0fac6d4f5ac`
- 实现提交：`95758c2e6b3623a02f3a035590934da816e3cc6f`

## 结果

1. 把锁定的逗号拼接 `note_download_url` 形状冻结为严格全有或全无的有序解析器：每个候选必须是恰好一个合法的（带或不带 query 的）HTTP(S) URL 且不含内嵌逗号，重复候选取证关闭，冻结图集边界为 1–64 张。
2. 精确一张图物化为 `ContentKind.IMAGE`，2–64 张物化为带有序 `{aweme_id}:image:0..N-1` IMAGE 资产的 `ContentKind.GALLERY`；任何内嵌逗号漂移、非字符串项、无效 URL、重复候选或超过 64 张的图集一律隔离关闭失败，而非静默丢弃子项。
3. 保持 0015 语义字节级兼容：空或缺失的 `note_download_url` 仍回退到视频/音频/文本形状，video/music/cover 字段保持既有宽容解析。
4. 验收既有逐资产适配器刷新对图集 position 的支持：一次精确 numeric-ID detail 运行在内存中重新解析每个 position 的当前签名 URL，路径漂移以 `locator_refresh_asset_mismatch` 关闭。
5. 每张图集图片经 DEFAULT-profile 候选轮次下载，含结构化静态图门（仅 JPEG/PNG/WebP）、SHA-256 归档与确定性 Emby poster/backdrop/gallery/NFO/source 发布，支持零工作重放。
6. 以一条生产级 SQLite → detail 刷新 → mock DNS/HTTP → 静态探测 → 归档 → Emby 组合证明全链路，同时全部真实账户/API/CDN/媒体服务器行保持 `NOT_RUN`。

## 验收边界

- 精确以标量逗号拼接 store 字段为图集权威；list 形状 payload 仅作为同一有序形状的 JSON 冻结等价物被接受。
- 图文混合 note 沿用锁定爬虫的图片优先选择（与 0015 一致）；图集 note 的 video URL 仍作为潜在音频流被忽略。
- 无数据库 schema 或迁移；稳定 Asset 身份不变；冻结媒体形状家族新增有界抖音图集形状。`.upstream` 保持只读且不入库。

## 明确延期

视频+图片混合 Asset 语义、图集的关联音乐、静态门之外的动图/WebP 动图漂移、同 ID 字节替换、有界作者分页、专用 CDN header、清理失败 quarantine 及全部真人验收行均不属于本执行。
