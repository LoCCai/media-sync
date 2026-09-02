[English](progress.md) | **中文**

# 执行 0034 推进结果

- 状态：冻结的离线快手图集范围已实现并通过门禁；真人行保持 `NOT_RUN`
- 日期：2026-09-03
- 计划提交：`eeff45e`（文档基线）

## 已交付

1. `kuaishou_media.py` 新增封闭 `validate_ks_image_url`（HTTPS、DNS host、容忍 query、无 fragment/userinfo/端口、静态扩展名）、跨越精确 `update_kuaishou_video` 边界的 `_capture_atlas` 通路与带 checkout 校验模块、marker 安全重装和私有字段防碰撞的 `install_kuaishou_media_capture`；shim 在定时 handler 子进程与 detail 子进程两侧安装。
2. `_normalize_ks` 新增冻结 gallery 分支：一个私有字符串列表字段以 1–64 边界、完整重校验与两两互异物化 `ContentKind.IMAGE`（一张）或 `ContentKind.GALLERY`（2–64）及有序 `{video_id}:image:0..N-1` IMAGE 资产加可选 COVER 伴随；畸形 payload 隔离，字段加入递归移除集合。
3. `AssetKind.IMAGE` 加入 KS 刷新支持集合，通用逐资产路径绑定每个图集 position、经一次精确 numeric-ID detail 子进程重新解析当前签名 URL 并以 `locator_refresh_asset_mismatch` 关闭路径漂移；普通视频 photo 字节级兼容。
4. 覆盖：归一化物化/漂移矩阵、真实 store fake checkout 契约组合（图集捕获、insecure/重复/超界不捕获、持久不泄密）与一条生产级 SQLite → detail 刷新 → mock DNS/HTTP → 静态 PNG/JPEG 门 → SHA-256 归档 → Emby 双图 gallery 组合并零工作重放。

## 验证快照

确切命令、退出码与门禁输出见 [`verification.zh.md`](verification.zh.md)。

## 未完成

图集文案/时长、动图漂移、视频+图片混合语义、同 ID 字节替换、专用 CDN header 及全部真人验收行继续延期或保持 `NOT_RUN`。
