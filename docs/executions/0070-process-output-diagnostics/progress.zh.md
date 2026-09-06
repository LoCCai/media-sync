[English](progress.md) | **中文**

# 推进结果

状态：实现及离线发布门禁已完成，实施提交 `b22e938` 已发布到 `origin/main`；本收尾记录随后的文档提交发布。

- 在既有私有 `state_dir/logs` JSONL 分片上新增一套有界进程输出捕获。每个子进程尝试最多 4 MiB、4096 行、每个原始行 64 KiB；乱码、超长、预算耗尽、策略过滤及 sink 拒绝只保存固定计数。
- 接通扫码登录输出且不污染结果帧或事件帧。父进程只快照规范 `operation_id`、`correlation_id`，已提交回调提供精确 `login_session_id`；child 在导入上游前移除并整包校验封闭环境信封，本地账户/platform 事实覆盖传播输入。
- 接通通用 MediaCrawler 作者采集 runner。安全事件保留 manifest 中精确 account、subscription、Job、Run、platform、attempt，以及存在时的规范父 Operation 关联。协议 stdout 只排空并汇总，绝不作为自由文字保存。
- 新增闭集 `process_output`、`process_output_summary`、`process_output_dropped` 事件；自由文字只允许出现在 `process_output`，并在事件边界再次独立校验。
- 对 Cookie object、`Set-Cookie`、Authorization、storage state、QR/base64、JWT/不透明凭据、签名 URL、Windows/POSIX 私有路径、结构化 JSON、HTML/DOM 及疑似作者正文字段执行 fail-closed 过滤。不安全行只留下固定 `[REDACTED]` 证据或丢弃计数。
- 独立审查发现锁定版 MediaCrawler 前缀（`时间 MediaCrawler LEVEL (文件:行) - 消息`）最初会被策略过滤。捕获层与事件校验现在共用一个精确规范化器，先转换成 `LEVEL 消息`，再执行同一套正文与秘密关闭过滤。真实格式的扫码/作者 child 契约同时覆盖可保留诊断及敌对载荷拒绝。
- 已鉴权日志中心现在解析并展示安全 message、stream、汇总计数及中文丢弃/错误说明。普通失败及回收后的 `interrupted` 登录保留唯一可信 Operation ID，账户页可直达按该 Operation 筛选的日志；中断态不会编造 runner 结果。
- 收尾时只读检查当前部署的日志中心，确认最新抖音尝试在 199 ms 内成功启动 Chromium，随后在“打开平台页面”阶段等待 30,005 ms 超时；Operation 于 40,501 ms 后终止失败。该已部署版本没有保存本次 child 进程输出，因此仍不能区分代理、网络、页面响应或上游适配原因；没有触发重试。
- 本轮没有部署、恢复 supervisor、发起生产登录、作者采集、下载或媒体服务器操作；旧部署已经丢弃的输出无法恢复。

## 待继续

- 将同一捕获策略接入独立 Cookie 校验、创作者资料、detail 和 download runner。它们既有的闭集生命周期事件仍可用，但子进程输出尚未保存。
- 部署本 revision 后，由操作者只复现一个失败扫码平台。只有这次新记录才能判断真实原因是浏览器启动、导航、网络、平台挑战、超时或其他运行时错误。
- 继续七平台订阅、历史回填、风控友好下载、增量刷新及 Emby/Jellyfin 兼容目录目标。本次可观测性增量只补证据，不等于已经修复平台登录。
