[English](verification.md) | **中文**

# 执行 0006 验证

- 验证日期：2026-08-30 12:34 +08:00
- 网络与账户策略：仅离线夹具、mock transport、生成媒体与本地 SQLite/文件系统
- 结果：完整离线/Fake 范围通过

## 行为证据

最终根任务运行了完整分支感知测试套件及下列全部专项门禁。未使用真实凭据、平台/CDN 端点或 Emby/Jellyfin 服务。mock/Fake 成功只验收离线契约，不能提升任何真人行。

| 范围 | 证据 | 最终状态 |
| --- | --- | --- |
| 重试与 circuit 策略 | 注入时钟/RNG、equal jitter、`Retry-After`、边界、非法数字/时间、最大 attempt 与精确 half-open 结果 | 通过 |
| 原子到期物化 | 有界 null-first 排序、schedule-revision CAS、独立 SQLite 并发 tick、fixed delay 与无追赶风暴 | 通过 |
| 启动 lane 与容量 | 独立连接全局容量、账户容量、持久最小启动截止、队列扫描公平与唯一 half-open 探针胜者 | 通过 |
| 执行 0005 隔离 | 类型 scoped reclaim/requeue/claim 保持下载/导出 payload、attempt、租约与恢复证据不变 | 通过 |
| Worker fencing 与等待 | 短事务、精确 heartbeat、取消/reclaim/ABA 竞争、同 session ownership guard 与仅显式恢复等待态 | 通过 |
| 封闭 handler registry | Fake handler 生命周期，以及到期 MediaCrawler 订阅以 `handler_unsupported` 终止且无 runner、导入、SyncRun、内容、下游 Job 或运行根副作用 | 通过 |
| 重启流水线 | 订阅 → tick → Fake 同步 → 显式安全 mock 下载 → 显式 Emby 导出 → 重建 → 重跑并复用身份 | 通过 |
| 密钥与恶意结果落点 | SQLite、Job/lane DTO、调度运维输出、归档/导出与保留产物精确扫描 | 通过 |
| 迁移 | 空库/当前库、源码真实 `0003 → 0004 → 0003 → 0004` 及解包 wheel 空库升级 | 通过 |

迁移证据有意限定范围。真实源码往返证明：`0003` 可表达的 Job 字段（包括 JSON 存储类型）、ExportRecord 与 `assets.download_job_id` 在释放 scheduler 身份时保持逐字段一致；不宣称 SQLite 文件物理字节一致。解包 wheel 测试只证明随包资源可导入且空库可升级到 `0004`，并非基于 wheel 的真实 `0003` 往返。

## 最终质量门禁

| 检查 | 最终准确命令 | 状态与证据 |
| --- | --- | --- |
| 锁定依赖 | `uv sync --all-groups --locked` | 通过 — 解析 58、审计 43 |
| 代码规范 | `uv run ruff check .` | 通过 |
| 格式 | `uv run ruff format --check .` | 通过 — 144 个文件 |
| 严格类型 | `uv run mypy src\media_sync` | 通过 — 62 个源码文件 |
| 全量测试与覆盖率 | `uv run pytest --cov=media_sync --cov-report=term` | 通过 — 686 项，152.40 秒；分支感知总覆盖率 80% |
| 调度、并发与 handler 专项 | `uv run pytest tests\unit\test_scheduler_policy.py tests\unit\test_scheduler_handlers.py tests\integration\test_scheduler_repository.py tests\integration\test_scheduler_worker.py tests\integration\test_scheduler_handler_safety.py tests\integration\test_scheduled_offline_pipeline.py tests\integration\test_scheduler_secret_sinks.py -q` | 通过 — 127 项，10.80 秒 |
| 数据库与迁移专项 | `uv run pytest tests\integration\test_database.py tests\integration\test_packaged_migrations.py -q` | 通过 — 25 项，14.10 秒 |
| 重启与密钥落点专项 | `uv run pytest tests\integration\test_scheduled_offline_pipeline.py tests\integration\test_scheduler_secret_sinks.py tests\integration\test_secret_sinks.py -q` | 通过 — 8 项，2.92 秒 |
| CLI 与工作流专项 | `uv run pytest tests\unit\test_cli.py tests\integration\test_cli_workflow.py -q` | 通过 — 61 项，12.14 秒 |
| 构建 | `uv build` | 通过 — 源码包与 wheel |
| 随包迁移 | `uv run pytest tests\integration\test_packaged_migrations.py -q` | 通过 — 6 项，8.31 秒 |
| 文档链接 | `uv run python scripts\check_docs.py` | 通过 — 40 个 Markdown 文件 |
| 锁定上游 | `uv run python scripts\check_upstreams.py` | 通过 — 2 个锁定 checkout |
| 补丁空白 | `git diff --check` | 通过 — 无输出 |
| 最终干净产物哨兵 | 下方可复现保留产物门禁 | 通过 — 40 项；六次精确扫描均零匹配 |
| 运行产物未跟踪 | `git ls-files -- archive exports jobs .media-sync dist` and `git status --short -- archive exports jobs .media-sync dist` | 通过 — 均无输出；全部保留根目录已忽略 |

## 最终保留产物哨兵

最终代码树在 `.media-sync/verification/0006-closeout-clean-sentinel-root` 下生成证据，共 58 个文件、86 个目录、10,664,504 字节，包含 40 项测试产物、40 个 SQLite 数据库、适用时的归档/媒体库输出及捕获的运维输出。完整过程为：

```powershell
$sentinelRoot = Join-Path $PWD '.media-sync\verification\0006-closeout-clean-sentinel-root'
if (Test-Path -LiteralPath $sentinelRoot) { throw "Verification root unexpectedly exists: $sentinelRoot" }
New-Item -ItemType Directory -Path $sentinelRoot | Out-Null
$sentinelPytestRoot = Join-Path $sentinelRoot 'pytest-artifacts'
$sentinelOutput = Join-Path $sentinelRoot 'operator-output.txt'
$sentinelStarted = Get-Date
uv run pytest tests/integration/test_scheduler_worker.py tests/integration/test_scheduler_handler_safety.py tests/integration/test_scheduled_offline_pipeline.py tests/integration/test_scheduler_secret_sinks.py -q --basetemp $sentinelPytestRoot 2>&1 | Tee-Object -FilePath $sentinelOutput
$sentinelPytestExit = $LASTEXITCODE
$sentinelElapsed = (Get-Date) - $sentinelStarted
if ($sentinelPytestExit -ne 0) { throw 'Clean sentinel tests failed' }
$sentinelPatterns = @(
  'SENTINEL-runtime-signed-query-0005',
  'SENTINEL-scheduler-handler-secret-must-not-persist',
  'SENTINEL-hostile-sync-error',
  'SENTINEL-scheduler-raw-exception-secret',
  '?signature=',
  $sentinelRoot
)
foreach ($sentinelPattern in $sentinelPatterns) {
  rg -a -F -- $sentinelPattern $sentinelRoot
  $sentinelScanExit = $LASTEXITCODE
  if ($sentinelScanExit -ne 1) { throw "Sentinel scan matched or failed: $sentinelPattern" }
}
git check-ignore -v -- .media-sync/verification/0006-closeout-clean-sentinel-root
git status --short --untracked-files=all -- .media-sync/verification/0006-closeout-clean-sentinel-root
git ls-files -- .media-sync/verification/0006-closeout-clean-sentinel-root
```

实测结果：

```text
40 passed in 5.92s
pytest_exit=0
elapsed_seconds=7.45
files=58 directories=86 bytes=10664504
scan_exit=1 for all six exact patterns / 六个精确模式均为 scan_exit=1
.gitignore:31:.media-sync/  .media-sync/verification/0006-closeout-clean-sentinel-root
```

对 `rg` 而言，退出码 `1` 表示扫描成功且零匹配；`0` 表示泄漏，`2+` 表示扫描失败。限定目录的 `git status` 与 `git ls-files` 均无输出。因此最终保留树不含任何精确 handler 密钥、恶意错误、签名 query 或绝对根路径模式，也未被 Git 跟踪。

另有两个早期忽略诊断根目录按要求保留而未删除。`.media-sync/verification/0006-final-sentinel-root` 包含 117 项测试、103 个文件、308 个目录与 22,874,763 字节，其中存在负向测试有意写入的哨兵行，因此不用于整树零匹配声明。`.media-sync/verification/0006-final-clean-sentinel-root` 是收尾前的 39 项干净运行，包含 57 个文件、84 个目录与 10,398,264 字节；其六个精确扫描同样返回退出码 1。上方 40 项 closeout 根目录是最终权威证据。

## 必须结论

- 有界 tick 对每个选中的到期订阅最多创建一个 active 周期；fixed-delay 收尾避免停机追赶风暴。
- SQLite writer 串行化及 schedule/lane/lease CAS 使独立本地进程在物化、容量槽、启动截止、half-open 探针、heartbeat、取消与 reclaim 上只有一个胜者。
- 通用 worker 只处理 `sync.subscription`；下载与 Emby Job 仍由执行 0005 服务拥有。
- `waiting_auth` 与 `waiting_user` 在显式 resume 前保持休眠；重试耗尽只终态化一次并只推进一次日程。
- adapter await 不持有 SQLite writer 事务；精确 heartbeat 与同 session ownership guard 阻止旧、已取消或已回收 handler 持久化。
- 原始 handler 异常、畸形结果、恶意错误码与未知/跨订阅 SyncRun ID 在持久化前映射为固定封闭错误码。
- 随附 registry 仅支持 Fake；定时 MediaCrawler 订阅以 `handler_unsupported` 默认拒绝，不启动子进程、不导入、不创建 SyncRun，也不创建运行/下载/导出状态。
- scheduler lane 只验收启动节流，不覆盖每次上游 HTTP 请求；离线重启验收显式调用下载与导出，不存在自动 sync → download → export DAG。

## 线上资格验证与延期实现

| 目标 | 状态 | 原因 |
| --- | --- | --- |
| 七平台二维码、Cookie、保存会话登录、作者同步与定时运行 | `NOT_RUN` | 未使用用户授权账户，也未进行真人交互挑战 |
| 七平台签名 locator 刷新与真实 CDN 获取 | `NOT_RUN` | 未授权 CDN 流量；refresh 仍未实现 |
| Emby/Jellyfin 重扫与播放 | `NOT_RUN` | 未启动或修改服务器 |

MediaCrawler 调度接入、manifest v3 请求延迟绑定、长子进程 heartbeat/cancel、签名 locator 刷新、逐请求上游节流、自动下游 DAG、REST、常驻守护、Docker/生产打包及分布式 HA 属于不可用或延期实现范围，而不是 `NOT_RUN` 结果。
