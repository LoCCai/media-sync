# Execution 0004 progress / 执行 0004 推进结果

- Status / 状态：Complete / 已完成
- Started / 开始时间：2026-08-30 04:40 +08:00
- Finished / 完成时间：2026-08-30 06:22 +08:00

## Delivered / 已交付

- Preserved both exact upstream pins and kept MediaCrawler as a separately installed, license-gated runtime; no upstream source was vendored or modified.
- Added typed `env:`, optional `keyring:` and confined `file:` secret references. A resolved signed creator reference retains `SecretValue` provenance through bridge preparation; ambiguous plain query URLs fail closed. Raw Cookie and signed creator-reference values are rejected or redacted at CLI, manifest, exception, event, JSON and SQLite sinks.
- Implemented exact-SHA checkout verification, account-isolated browser profiles, unique job/output roots, bounded watchdogs, an independent child runner and the Zhihu creator-input shim.
- Bound manifest schema v2 to account, subscription, job, crawl revision, intended mode, login method, item cap and author/creator-reference fingerprints. Ingest recomputes the subscription-authorized creator fingerprint, resolving signed references only in memory. The public child argument vector contains no secret.
- Added a sealed completion receipt written only after successful child exit, descendant cleanup and a quiet period. Receipt validation binds exact files, byte sizes and SHA-256 digests and rejects symlink/reparse, hardlink, descriptor-swap, missing, failed or truncated output. The parent refuses to seal output that echoes an exact known Cookie or signed creator reference, including JSON-escaped values.
- Made ingestion consume an immutable in-memory byte snapshot from that receipt. Any semantic quarantine or truncated JSONL tail rejects the complete forward ingest before a run or checkpoint is created.
- Added versioned fixtures and normalized author/content/ordered-asset contracts for `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba` and `zhihu`, including Bilibili dynamics.
- Added migration `0002_checkpoint_fencing`, independent forward/backfill cursors, publish-time plus same-timestamp-ID watermarks and optimistic checkpoint revisions.
- Implemented bounded short transactions, oldest-first forward batches and atomic content/checkpoint/run publication. A sealed older crawl can recover only its missing records after an interleaved newer run without regressing the newer watermark or cursor.
- Added MediaCrawler doctor/dry-run, adapter-aware account creation, secret creator-reference subscription input and sealed-output ingest CLI paths.
- Proved command, receipt, normalization, checkpoint, recovery and secret-sink behavior with offline tests for all seven platform identifiers.

- 保留两个上游的精确锁定版本，并继续把 MediaCrawler 作为独立安装、需要许可证确认的外部运行时；未内嵌或修改上游源码。
- 新增类型化 `env:`、可选 `keyring:` 和受限 `file:` 密钥引用。解析后的签名作者引用在桥接准备全程保留 `SecretValue` 来源标记，含义不明的普通 query URL 默认拒绝。原始 Cookie 与带签名参数的作者引用会在 CLI、manifest、异常、事件、JSON 与 SQLite 落点被拒绝或脱敏。
- 实现精确 SHA 检出验证、账户隔离浏览器目录、唯一任务/输出根目录、有界看门狗、独立子 runner 及知乎作者输入兼容层。
- manifest v2 绑定账户、订阅、任务、爬取起始 revision、预期模式、登录方式、数量上限及作者/真实引用指纹；导入会重新计算订阅授权的作者引用指纹，签名引用只在内存解析；公开子进程参数不含密钥。
- 子进程成功退出、后代清理且输出静默后才写密封完成回执。回执绑定精确文件、字节数与 SHA-256，并拒绝符号链接/reparse、硬链接、文件描述符替换、缺失、失败或截断输出；父进程也拒绝密封在普通字段回显已知 Cookie 或签名作者引用（含 JSON 转义）的输出。
- 导入只消费回执验证后的不可变内存字节快照；任何语义隔离记录或 JSONL 末行截断都会在创建 run/checkpoint 前拒绝整次前向导入。
- 为七个平台及 B 站动态添加版本化夹具，验证作者、内容与有序资产的归一化契约。
- 新增 `0002_checkpoint_fencing` 迁移、独立前向/回填游标、发布时间加同时间戳 ID 水位，以及乐观 checkpoint revision。
- 实现有界短事务、前向旧到新批次，以及内容/checkpoint/run 的原子发布。旧密封爬取在新运行交错推进后只能补齐缺失记录，不能回退新水位或游标。
- 新增 MediaCrawler 诊断/dry-run、支持 adapter 的账户创建、密钥作者引用订阅输入及密封输出导入 CLI。
- 用全离线测试覆盖七个平台标识的命令、回执、归一化、检查点、恢复和密钥落点行为。

## Deferred truthfully / 如实延期

- Media downloading and Emby/Jellyfin export belong to execution 0005; this bridge intentionally leaves upstream binary downloading disabled.
- Scheduler/API/operations and release readiness remain later executions.
- No authorized account, browser challenge or platform endpoint was used. Every live qualification remains `NOT_RUN`.

- 媒体下载与 Emby/Jellyfin 导出属于执行 0005；本桥接有意保持上游二进制下载关闭。
- 调度/API/运维及发布准备留待后续执行。
- 本轮未使用授权账户、浏览器挑战或平台端点，全部真人资格验证继续保持 `NOT_RUN`。
