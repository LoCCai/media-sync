# Execution 0004 goal / 执行 0004 目标

Deliver a credential-safe, license-gated MediaCrawler process bridge for all seven pinned platform identifiers, plus fixture-proven normalization and restart-safe forward/backfill checkpoints. The default test suite remains network-free and never launches a browser or uses a real account.

交付覆盖锁定版本全部七个平台标识的 MediaCrawler 外部进程桥接，并实现安全凭据、显式许可证确认、夹具验证的归一化，以及可重启的前向/回填检查点。默认测试套件保持离线，不启动浏览器，也不使用真人账户。

## Acceptance / 验收

- A bridge doctor verifies the configured external checkout, exact locked SHA, Python entry point and license acknowledgement without modifying upstream files.
- QR, Cookie and saved-session capabilities are exposed only where the pinned source supports them; phone login remains unavailable.
- Raw credentials never enter command arguments, SQLite, manifests, events, logs, exception text or Git. A child receives a secret through one private environment variable and removes it before upstream execution.
- Every run uses a path-confined, unique job/profile/output directory, conservative item/time limits and an explicit full-history acknowledgement for upstream paths known to ignore the item cap.
- Safe dry-run command contracts cover `xhs`, `dy`, `ks`, `bili`, `wb`, `tieba` and `zhihu`, including the Zhihu creator-input compatibility shim.
- Versioned fixture JSONL for all seven platforms normalizes authors, text/image/gallery/video/audio/dynamic content and ordered assets without copying upstream source.
- Incremental ingestion tolerates a truncated final line, quarantines malformed/unknown records, enforces output limits and is idempotent under replay.
- Forward scans consume publish watermark plus same-timestamp known IDs; historical continuation uses a separate backfill cursor. Checkpoint publication uses optimistic fencing and cannot erase `next_run_at` or overwrite a newer run.
- Browser/network waits occur outside SQLite write transactions; each accepted batch plus its checkpoint commits atomically.
- Ruff, format, strict mypy, offline unit/contract/integration tests, package build, documentation and secret-sentinel scans pass with exact evidence recorded here.

- 桥接诊断会检查外部检出、锁定 SHA、Python 入口和许可证确认，且不修改上游文件。
- 仅开放锁定源码实际支持的二维码、Cookie 和保存会话；不开放手机号登录。
- 原始凭据不得进入命令参数、SQLite、manifest、事件、日志、异常文本或 Git；子进程只通过一个私有环境变量接收密钥，并在执行上游前删除。
- 每次运行使用路径受限且唯一的任务/profile/输出目录、保守数量/时间上限；对已知忽略数量上限的上游路径必须显式确认全历史风险。
- 七个平台的安全 dry-run 命令契约全部通过，并包含知乎作者参数兼容修正。
- 七平台版本化 JSONL 夹具可归一化作者、图文/图片集/视频/音频/动态和有序资产，且不复制上游源码。
- 增量导入容忍末行截断、隔离畸形/未知记录、限制输出数量，重放保持幂等。
- 前向扫描消费发布时间水位与同时间戳已知 ID；历史翻页使用独立回填 cursor。检查点发布使用乐观 fencing，不得清空 `next_run_at` 或覆盖更新运行。
- 浏览器/网络等待位于 SQLite 写事务之外；每个已接受批次与其检查点原子提交。
- Ruff、格式、严格 mypy、离线单元/契约/集成测试、包构建、文档和密钥哨兵扫描全部通过，并在此记录准确证据。

## Truth boundary / 真实性边界

Dry-run commands and fixtures prove our bridge contract only. Until a user supplies authorized credentials and completes interactive checks, all seven live login, creator scan and media outcomes remain `NOT_RUN`; no automated result may promote them to `PASS`.

Dry-run 与夹具只证明本项目的桥接契约。用户提供授权凭据并完成人机交互验证前，七个平台的真人登录、作者扫描和媒体结果全部保持 `NOT_RUN`，任何自动化结果都不得将其提升为 `PASS`。
