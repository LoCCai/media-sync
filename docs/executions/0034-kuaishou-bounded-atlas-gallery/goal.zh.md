[English](goal.md) | **中文**

# 执行 0034 目标

- 状态：冻结的离线快手图集范围已完成；真人行保持 `NOT_RUN`
- 日期：2026-09-03
- 前驱：执行 0033 收尾 `e9d1fcdb8970b5a10f84e3947e1570159c9f9011`
- 范围：一条普通快手图集 photo，其 `photo.ext_params.atlas.pics` 携带 1–64 张有序 CDN 图片，在锁定 store 边界捕获，交付为带逐图适配器刷新与 Emby 发布的有界 IMAGE/GALLERY 内容
- 计划提交：`eeff45e2d862a7615d9a74c06914310dcd9f4272`
- 实现提交：`26c2b3ea974fbba8ea41a9eb496f25738b1718be`

## 结果

1. 为 `update_kuaishou_video` 安装锁定 store 捕获 shim：精确校验冻结的 `photo.ext_params.atlas.pics[].cdn` 形状——HTTPS、容忍 query、无 fragment/userinfo/端口、静态 `.jpg/.jpeg/.png/.webp` 扩展、1–64 个两两互异候选——并以 media-sync 自有私有字段注入；任何漂移不捕获。
2. 归一化为 `ContentKind.IMAGE`（一张）或 `ContentKind.GALLERY`（2–64）及有序 `{video_id}:image:0..N-1` IMAGE 资产，可选封面保持 0014 的 COVER 资产；畸形 payload 隔离关闭失败，私有字段持久化前递归移除。
3. 把 `AssetKind.IMAGE` 加入 KS 刷新支持集合，使既有逐资产适配器刷新绑定每个 position、经一次精确 numeric-ID detail 子进程在内存中重新解析当前签名 URL，并以 `locator_refresh_asset_mismatch` 关闭路径漂移。
4. 每张图片经 DEFAULT-profile 候选轮次下载，含结构化静态图门、SHA-256 归档与确定性 Emby poster/backdrop/gallery/NFO/source 发布，支持零工作重放。
5. 以一条生产级 SQLite → detail 刷新 → mock DNS/HTTP → 静态探测 → 归档 → Emby 组合证明全链路，同时全部真实账户/API/CDN/媒体服务器行保持 `NOT_RUN`。

## 验收边界

- 图集授权只来自冻结的嵌套 store 输入形状；URL 后缀、响应 MIME 与下载字节都不能授予该授权。普通视频 photo 保持 0014 语义字节级兼容。
- 图集 photo 的 `photoUrl` 视频字段按锁定爬虫的图片优先选择被忽略；封面保持可选。
- 无数据库 schema 或迁移；稳定 Asset 身份不变。`.upstream` 保持只读且不入库。

## 明确延期

图集文案/时长、静态门之外的动图漂移、视频+图片混合 Asset 语义、同 ID 字节替换、有界作者分页、专用 CDN header 及全部真人验收行均不属于本执行。
