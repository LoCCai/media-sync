[English](progress.md) | **中文**

# 执行 0038 推进结果

- 状态：冻结的离线小红书实况照片范围已实现并通过门禁；真人行保持 `NOT_RUN`
- 日期：2026-09-03
- 计划提交：`650c256`（文档基线）

## 已交付

1. 新的锁定 store shim（`xhs_live.py`）为恰一张图的 `type="normal"` note 精确捕获冻结的 `image_list[0].live_photo.stream.h264[0].master_url` 形状，定时与 detail 双子进程安装；嵌套畸形、外域、超过一张图与错误类型不捕获。
2. `_normalize_xhs` 新增冻结实况分支：MIXED 内容与一个 `{note_id}:image:0` IMAGE（store 保留 URL）加一个 `{note_id}:video:0` VIDEO（实况流），`video_url` 标量为空；畸形 payload 隔离，私有字段加入递归移除集合。
3. creator 回退的 `normal` 类型分支接受精确的一图加一视频目标——该形状对 normal 类型 note 无歧义——并重校验实况 URL；普通 `normal`/`video` note 字节级兼容。
4. 覆盖：摄取物化与 payload/形状漂移矩阵、双资产刷新解析与路径漂移关闭，以及一条生产级 SQLite → 刷新 → 双下载 → 归档 → Emby 带海报剧集的零工作重放组合与持久不泄密。

## 验证快照

确切命令、退出码与门禁输出见 [`verification.zh.md`](verification.zh.md)。

## 未完成

多图实况 gallery、H.265 偏好、实况时长语义及全部真人验收行继续延期或保持 `NOT_RUN`。
