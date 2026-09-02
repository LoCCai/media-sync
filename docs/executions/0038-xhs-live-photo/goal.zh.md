[English](goal.md) | **中文**

# 执行 0038 目标

- 状态：冻结的离线小红书实况照片范围已完成；真人行保持 `NOT_RUN`
- 日期：2026-09-03
- 前驱：执行 0037 收尾 `b9c88c4afab6ba2d9d2a43efea63f63cd6cd31ca`
- 范围：一条普通小红书 `type="normal"` note，其唯一 `image_list` 条目携带实况照片，在锁定 store 边界捕获被丢弃的 H.264 主流并交付一张 IMAGE 加一个可播放 VIDEO
- 计划提交：`650c256`
- 实现提交：`8c80073`

## 结果

1. 为 `update_xhs_note` 安装锁定 store 捕获 shim：对恰一张图的 `type="normal"` note，精确校验冻结的 `image_list[0].live_photo.stream.h264[0].master_url` 形状——恰一个合法 `xhscdn.com` HTTP(S) URL——并以 media-sync 自有私有字段注入；任何漂移不捕获。
2. 物化 `ContentKind.MIXED`：一个 `{note_id}:image:0` IMAGE（store 保留的图片 URL）加一个 `{note_id}:video:0` VIDEO（实况流）；普通 `normal`/`video` note 字节级兼容，畸形 payload 隔离关闭失败。
3. 扩展 creator 回退刷新：实况目标接受精确的一图加一视频资产形状，实况 URL 经 detail 权限重新解析；路径漂移关闭失败。
4. 双资产经 DEFAULT profile 下载——IMAGE 走静态图门、VIDEO 走 MP4 探测——SHA-256 归档并发布带 poster 的 Emby 集，零工作重放。
5. 证明契约与集成组合，同时全部真实账户/API/CDN/媒体服务器行保持 `NOT_RUN`。

## 验收边界

- 只有精确冻结的嵌套 store 输入形状授予实况视频；URL 后缀、响应 MIME 与下载字节都不能影响它。无实况照片、嵌套畸形或超过一张图的 note 不捕获。
- 实况 note 的 `video_url` 标量必须为空；0017 静态与 0018/0037 视频形状保持不变。
- 无数据库 schema 或迁移；稳定 Asset 身份不变。`.upstream` 保持只读且不入库。

## 明确延期

多图实况 gallery、H.265 偏好、实况时长语义、动图漂移及全部真人验收行均不属于本执行。
