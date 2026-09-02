[English](progress.md) | **中文**

# 执行 0036 推进结果

- 状态：冻结的离线微博视频封面范围已实现并通过门禁；真人行保持 `NOT_RUN`
- 日期：2026-09-03
- 计划提交：`1ad49a7`（文档基线）

## 已交付

1. 微博 store shim 的视频捕获现在还捕获封闭的 `page_info.pic_info.pic_big.url` 封面——HTTPS `sinaimg.cn` 族 host、静态扩展、有界路径——且仅当视频本身（标量或 `playback_list`）先成功捕获；缺失、畸形、外域或非静态封面仅捕获视频。
2. 一个新的私有 `{"url"}` 封面字段以严格防碰撞与递归移除跨越边界；`_normalize_wb` 在 VIDEO 旁物化 `{note_id}:cover:0` COVER 资产，并对畸形封面 payload 隔离。
3. `AssetKind.COVER` 加入 WB 刷新支持集合，封面像视频一样经一次精确 numeric-note detail 子进程重新解析。
4. 覆盖：真实子进程契约组合（流旁的封面、外域/动图/错误扩展漂移仅捕获视频）与集成组合证明双资产 归一化 → 摄取 → 刷新 → 下载 → 归档 → Emby poster 发布，零工作重放且持久不泄密。

## 验证快照

确切命令、退出码与门禁输出见 [`verification.zh.md`](verification.zh.md)。

## 未完成

其他封面尺寸、GIF/动图封面、转发、直播/付费媒体及全部真人验收行继续延期或保持 `NOT_RUN`。
