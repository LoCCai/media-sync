[English](usage.md) | **中文**

# 安全进程日志使用说明

新增记录继续使用已鉴权的 **日志中心** `/logs`，不提供原始输出浏览器，也不创建无管理日志目录。

1. API 与 supervisor 部署同一个镜像，并继续共享既有 `/data` volume。
2. 两个服务保持三项日志预算一致：`MEDIA_SYNC_LOG_SEGMENT_MAX_BYTES`、`MEDIA_SYNC_LOG_TOTAL_MAX_BYTES`、`MEDIA_SYNC_LOG_RETENTION_DAYS`。
3. 只复现一个失败平台登录；不要对同一账户并行发起多次扫码。
4. 在账户结果卡点击 **查看本次日志**，链接会按精确 Operation 筛选；相邻生命周期证据可继续查看 Job/诊断链接。
5. 记录 Operation ID 以及页面显示的 event code、phase、stream、安全 message、summary 与 drop counter。不要把 Cookie 值、二维码图片、浏览器 profile 或第三方原始页面复制进 issue。

`[REDACTED]` 与 `policy_filtered` 是预期安全结果，不代表 logger 失败；`log_sink_rejected` 表示部分本可保留的证据未被 sink 接受，应结合 writer health 事件核查。summary 统计该 stream 读取的全部行，不表示每一行都已持久化。

受管日志仍属于私密运维数据。备份或清理必须沿用既有日志中心的 state volume 流程，切勿把整个分片发布到 GitHub。
