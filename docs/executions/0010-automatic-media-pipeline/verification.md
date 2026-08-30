# Execution 0010 verification / 执行 0010 验证

- Verification state / 验证状态：`PASS` for the complete offline MVP gate / 完整离线 MVP 门禁通过
- Verification date / 验证日期：2026-08-31
- Predecessor / 前置：Execution 0009 commit `98cf387`
- Qualification boundary / 验收边界：offline SQLite/Fake/direct/mock workflow only; authorized platform/CDN/Emby rows remain `NOT_RUN` / 仅离线 SQLite/Fake/direct/mock 工作流；授权平台/CDN/Emby 行保持 `NOT_RUN`

## Recorded checks / 已记录检查

| Scope / 范围 | Command or evidence / 命令或证据 | Result / 结果 |
| --- | --- | --- |
| Combined pipeline/scheduler/CLI gate / Pipeline、scheduler、CLI 合并门禁 | `uv run pytest -q tests/integration/test_pipeline_job_repository.py tests/integration/test_pipeline_runtime.py tests/integration/test_pipeline_worker.py tests/integration/test_subscription_application_pipeline.py tests/integration/test_scheduler_worker.py tests/integration/test_scheduled_offline_pipeline.py tests/unit/test_cli.py` | `PASS` — `154 passed in 15.85s` |
| Atomic enqueue and recovery / 原子入队与恢复 | Included above: normal success, duplicate success and succeeded-run reconciliation create one coordinator; failure/wait/cancel create none / 已包含于上项 | `PASS` |
| Claim hardening / Claim 强化 | Included above: bounded scan; malformed/stale head terminalization; valid row behind it remains claimable / 已包含于上项 | `PASS` |
| Exact scope before side effects / 副作用前精确范围 | Included above: Account/platform drift fails before request factory, downloader or exporter / 已包含于上项 | `PASS` |
| Download/restart/export / 下载、重启与导出 | Included above: 0/1/N selection, retry stop, verified reuse, re-selection and offline Emby publication / 已包含于上项 | `PASS` |
| Runtime composition / Runtime 组合 | Included above: direct locator without MediaCrawler; exact Subscription-bound lazy refresh construction / 已包含于上项 | `PASS (offline)` |
| Network preflight regression / 网络 preflight 回归 | New missing/invalid lock-checkout-Python and launchable-ffprobe nodes, all before child Job/Asset lifecycle mutation / 新增缺失/无效 lock-checkout-Python 与可启动 ffprobe 节点，均位于 child Job/Asset 生命周期变更前 | `PASS` — `5 passed` |
| Runtime + CLI regression / Runtime 与 CLI 回归 | `uv run pytest tests/integration/test_pipeline_runtime.py tests/unit/test_cli.py -q` | `PASS` — `73 passed` |
| Heartbeat/fencing / Heartbeat 与 fencing | Included above: renewal during a blocking async handler, replacement-token fencing and invalid interval matrix / 已包含于上项 | `PASS (focused)` |
| CLI controls / CLI 控制 | Included above: `--scan-limit`, `--heartbeat-interval-seconds`, default-off MediaCrawler enable/license and invalid-combination rejection / 已包含于上项 | `PASS` |
| Whole-tree lint / 整树 lint | `uv run ruff check .` | `PASS` — `All checks passed!` |
| Whole-tree format / 整树格式 | `uv run ruff format --check .` | `PASS` — `185 files already formatted` |
| Strict source typing / 严格源码类型 | `uv run mypy src/media_sync` | `PASS` — `Success: no issues found in 72 source files` |
| Full non-coverage suite before final compatibility repair / 最终兼容修复前完整非覆盖套件 | `uv run pytest -q` | `PARTIAL` — `926 passed, 1 skipped, 1 failed`; the only failure was the historical scheduled-offline Job-set assertion, not a runtime failure / 唯一失败是历史 scheduled-offline Job 集合断言，并非运行时失败 |
| Repaired historical node / 已修复历史节点 | `uv run pytest tests/integration/test_scheduled_offline_pipeline.py::test_scheduled_offline_pipeline_survives_restart_without_duplicate_identities -q` | `PASS` — `1 passed`; it now expects the coordinator to remain `queued` until explicit `pipeline run` / 现预期协调器保持 queued，直到显式 pipeline worker 运行 |
| Final full-suite rerun after repair / 修复后最终完整套件复跑 | `uv run pytest -q` | `PASS` — `930 passed, 1 skipped in 191.06s`; the skip is the Windows-inapplicable POSIX mode-bit case / skip 为 Windows 不适用的 POSIX mode-bit case |
| Pinned upstreams / 锁定上游 | `uv run python scripts/check_upstreams.py` | `PASS` — `Upstreams OK (2 locked checkouts verified).` |
| Build / 构建 | `uv build` | `PASS` — sdist and wheel generated / 已生成 sdist 与 wheel |
| Documentation / 文档 | `uv run python scripts/check_docs.py` | `PASS` — `Documentation links OK (56 Markdown files checked).` |
| Patch whitespace / 补丁空白 | `git diff --check` | `PASS` — exit `0`, no output / 退出码 `0`，无输出 |

The earlier `926 passed, 1 skipped, 1 failed` run is retained above as the regression that found the stale historical assertion; it is not combined with a one-node rerun. The authoritative post-repair full suite is the later independent `930 passed, 1 skipped` invocation.

上方保留较早的 `926 passed, 1 skipped, 1 failed`，它是发现陈旧历史断言的回归证据；不会把它与单节点复跑拼接为全绿。权威的修复后完整套件是随后独立运行的 `930 passed, 1 skipped`。

## Concurrency and cancellation truth / 并发与取消事实

The heartbeat renews exact Job/worker/token ownership, and complete/fail uses the same CAS, so a stale coordinator cannot normally overwrite a successor's Job result. However, the CLI handler is synchronous and is offloaded with `asyncio.to_thread`; cancelling its asyncio wrapper cannot forcibly stop the underlying thread. Lease loss or heartbeat-storage failure may therefore leave old download/export work running while a successor or later bounded Job proceeds. This execution does not qualify cooperative cancellation, forced termination, multi-worker HA or every cancellation micro-window.

Heartbeat 续租精确 Job/worker/token，complete/fail 使用相同 CAS，因此旧协调器通常不能覆盖后继 Job 结果。但 CLI handler 为同步函数并通过 `asyncio.to_thread` 移出事件循环；取消 asyncio 包装任务无法强制停止底层线程。失租或 heartbeat 存储故障后，旧下载/导出工作仍可能运行，同时后继或后续有界 Job 继续推进。本执行不验收协作式取消、强制终止、多 worker HA 或全部取消微窗口。

## Live qualification / 真人资格验证

| Platform / 平台 | Live login / 真人登录 | Creator/detail traffic / 作者/detail 流量 | Signed CDN download / 签名 CDN 下载 | Real Emby/Jellyfin scan/playback / 真实扫描与播放 |
| --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

Offline fixture/fake-child/direct transport evidence never changes this live table. Phone login remains unsupported, and no seven-platform complete-download claim is made.

离线 fixture/fake-child/direct transport 证据绝不改变真人表。手机号登录仍不支持，也不宣称七平台完整下载能力。
