[English](progress.md) | **中文**

# 执行 0006 推进结果

- 状态：离线/Fake 范围完成；最终根任务门禁通过
- 计划提交：`c8c4e54`
- 实现日期：2026-08-30
- 网络边界：仅离线夹具、mock transport 与本地 SQLite/文件系统

## 已交付

- 新增迁移 `0004_scheduler_control_plane`：订阅 schedule revision、Job 的订阅/账户/平台/时间 scope、领取/scope 索引、单 active 周期部分唯一性，以及持久平台/账户 lane。downgrade 只移除调度状态，并在 SQLite batch 重建时保留执行 0005 Job 证据与资产下载关联。

- 实现有界 null-first 到期物化、schedule-revision CAS、唯一持久周期身份、fixed-delay 收尾及无追赶风暴；使用独立 SQLite 连接的并发 tick 对每个订阅最多创建一个 active 周期。

- 修正通用 Job 仓储，使 reclaim 与 retry requeue 在变更前按类型限定；`sync.subscription` worker 不会改变或领取 `asset_download`、`export.emby` Job。

- 新增封闭 retry/circuit 策略：有界 equal-jitter 指数退避、有限 `Retry-After` 下界、最大 attempt、固定错误分类、持久 closed/open/half-open 状态及唯一精确 half-open 探针。

- 新增全局容量及持久平台/账户并发与最小启动间隔 lane；领取会跳过阻塞队头，lane policy 修改与 circuit reset 使用 revision CAS。这些保证只覆盖 scheduler 启动节流，不覆盖每次上游 HTTP 请求。

- 新增显式 pause/resume/run-now、休眠的 `waiting_auth`/`waiting_user`、安全 Job resume/cancel、有界类型 scoped reclaim、精确 heartbeat/ABA fencing，以及脱敏 Job/lane 投影。

- 新增封闭 handler registry 与确定性 Fake handler。worker 使用短 claim/start/finalize 事务、并发精确 token heartbeat、协作式取消，以及 handler 持久化前的同 session ownership guard；adapter await 期间不持有 SQLite writer 事务。

- 闭合恶意结果路径：原始 handler 异常、畸形结果、非法 RNG/时间值、未知 adapter/domain 错误码，以及未知或跨订阅 SyncRun ID 均映射为固定错误码。SQLite、Job/lane DTO 与调度运维输出不保留来自不可信 handler 的密钥/路径文本；既有资产/导出领域仍会按设计保存合法归档/输出路径。

- 新增 `subscription pause|resume|run-now`、`scheduler tick|run`、`scheduler job list|resume|cancel` 与 `scheduler lane list|set|reset` CLI。全部批量/容量/租约/policy 输入均有界，输出采用显式白名单，不含 payload、租约 owner/token、凭据、locator 或文件系统根目录。

- 新增可重启离线验收：订阅 → tick → scheduled Fake sync → 显式安全 mock 下载 → 显式 Emby 导出 → 重建服务 → 重跑。该流程证明不会重复调度周期、归档身份或发布身份，同时不宣称已有自动下游 DAG。

## 审查修正

- 最终 P1 审查发现 Fake adapter await 周围存在长 SQLite 事务、worker 缺少 heartbeat/cancel 观察、start 后异常边界开放、结果 Run ID 未校验，以及恶意错误码可能进入 SyncRun 落点。全部问题均在最终门禁前修复，并增加独立 writer/cancel/reclaim、字节哨兵及故障注入回归。

- SQLite 调度决策会在 read/decide/CAS 前取得 writer slot。handler 持久化 guard 在应用变更的同一事务内执行精确 owner/token/expiry no-op update，从而消除取消场景的检查到使用空隙。

## 如实延期

- MediaCrawler 保持执行 0004 的手工 run/ingest 边界；其 scheduled handler、manifest v3 请求延迟绑定、长子进程 heartbeat/cancel 与签名 locator refresh 不由 0006 实现。

- 自动 sync → download → export 规划、REST、常驻守护、Docker/生产打包、分布式 HA/PostgreSQL 锁及公网部署仍属于后续执行。

- 七平台真人二维码/Cookie/保存会话登录/定时运行、真实 CDN 下载及实际 Emby/Jellyfin 扫描/播放继续为 `NOT_RUN`；未授权任何凭据或线上服务。

## 收尾结果

- 最终根任务门禁通过 686 项测试，耗时 152.40 秒，分支感知总覆盖率 80%；调度、迁移、重启、密钥落点、CLI、构建、文档、锁定上游、补丁与运行产物专项检查全部通过。

- 最终干净保留产物门禁通过 40 项测试，并扫描 `.media-sync/verification/0006-closeout-clean-sentinel-root` 下的 58 个文件；六个精确密钥/query/路径模式均返回 `rg` 退出码 1（成功零匹配）。未使用真人账户、平台/CDN 端点或 Emby/Jellyfin 服务。
