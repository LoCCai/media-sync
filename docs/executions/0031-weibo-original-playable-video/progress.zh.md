[English](progress.md) | **中文**

# 执行 0031 推进结果

- 状态：冻结的离线普通原创可播放视频范围已实现并通过门禁；真人行保持 `NOT_RUN`
- 日期：2026-09-02
- 计划提交：`1c79c6d`（文档基线）

## 已交付

1. 锁定的微博 store shim 现在还从 `page_info.page_type` 精确为 `video`、非转发、numeric-ID 的普通 `mblog` 中，在与 0016 图片捕获相同的精确对象 store 边界上捕获精确一个标量 `media_info.stream_url`；转发、非视频 page 类型与漂移形状不捕获任何内容。
2. 一个新的私有 `{"url"}` payload 以与图片字段严格防碰撞的方式跨越边界，加入持久化前递归移除集合，并绑定封闭 URL 校验器（HTTPS `sinaimg.cn`/`*.sinaimg.cn`/`f.video.weibocdn.com` host、非根大小写不敏感 `.mp4` 路径、无 fragment/userinfo/端口、允许签名 query）。
3. `_normalize_wb` 新增冻结的 VIDEO 分支：`ContentKind.VIDEO` 与精确一个 position-0 `{note_id}:video:0` VIDEO 资产；对图片字段共存、残留 `page_info`、转发、非规范身份与畸形 payload 一律关闭失败。
4. `AssetKind.VIDEO` 加入 WB 刷新支持集合，使既有通用刷新绑定精确资产、经一次 numeric-note detail 子进程在内存中重新捕获当前签名 URL 并返回 DEFAULT-profile 瞬态 locator，而持久状态只保留无 query 提示。
5. 覆盖：校验器接受/拒绝矩阵、经真实子进程的 shim 捕获矩阵、归一化关闭失败结局、刷新漂移结局、持久不泄密，以及一条生产级 SQLite → detail 刷新 → mock DNS/HTTP → MP4 探测 → SHA-256 归档 → Emby `.mp4`/NFO/source 组合并零工作重放。

## 验证快照

确切命令、退出码与门禁输出见 [`verification.zh.md`](verification.zh.md)。

## 未完成

`playback_list`/画质选择、封面、时长、转发、GIF、直播/付费媒体、混合媒体帖、更广分页、CDN 排序/竞速/跨运行缓存及全部真人验收行继续延期或保持 `NOT_RUN`。
