[English](verification.md) | **中文**

# 执行 0010 验证

- 验证状态：完整离线 MVP 门禁通过
- 验证日期：2026-08-31
- 前置：Execution 0009 commit `98cf387`
- 验收边界：仅离线 SQLite/Fake/direct/mock 工作流；授权平台/CDN/Emby 行保持 `NOT_RUN`

## 已记录检查

| 范围 | 命令或证据 | 结果 |
| --- | --- | --- |
| Pipeline、scheduler、CLI 合并门禁 | `uv run pytest -q tests/integration/test_pipeline_job_repository.py tests/integration/test_pipeline_runtime.py tests/integration/test_pipeline_worker.py tests/integration/test_subscription_application_pipeline.py tests/integration/test_scheduler_worker.py tests/integration/test_scheduled_offline_pipeline.py tests/unit/test_cli.py` | `PASS` — `154 passed in 15.85s` |
| 原子入队与恢复 | 已包含于上项 | `PASS` |
| Claim 强化 | 已包含于上项 | `PASS` |
| 副作用前精确范围 | 已包含于上项 | `PASS` |
| 下载、重启与导出 | 已包含于上项 | `PASS` |
| Runtime 组合 | 已包含于上项 | `PASS (offline)` |
| 网络 preflight 回归 | 新增缺失/无效 lock-checkout-Python 与可启动 ffprobe 节点，均位于 child Job/Asset 生命周期变更前 | `PASS` — `5 passed` |
| Runtime 与 CLI 回归 | `uv run pytest tests/integration/test_pipeline_runtime.py tests/unit/test_cli.py -q` | `PASS` — `73 passed` |
| Heartbeat 与 fencing | 已包含于上项 | `PASS (focused)` |
| CLI 控制 | 已包含于上项 | `PASS` |
| 整树 lint | `uv run ruff check .` | `PASS` — `All checks passed!` |
| 整树格式 | `uv run ruff format --check .` | `PASS` — `185 files already formatted` |
| 严格源码类型 | `uv run mypy src/media_sync` | `PASS` — `Success: no issues found in 72 source files` |
| 最终兼容修复前完整非覆盖套件 | `uv run pytest -q` | 唯一失败是历史 scheduled-offline Job 集合断言，并非运行时失败 |
| 已修复历史节点 | `uv run pytest tests/integration/test_scheduled_offline_pipeline.py::test_scheduled_offline_pipeline_survives_restart_without_duplicate_identities -q` | 现预期协调器保持 queued，直到显式 pipeline worker 运行 |
| 修复后最终完整套件复跑 | `uv run pytest -q` | skip 为 Windows 不适用的 POSIX mode-bit case |
| 锁定上游 | `uv run python scripts/check_upstreams.py` | `PASS` — `Upstreams OK (2 locked checkouts verified).` |
| 构建 | `uv build` | 已生成 sdist 与 wheel |
| 文档 | `uv run python scripts/check_docs.py` | `PASS` — `Documentation links OK (56 Markdown files checked).` |
| 补丁空白 | `git diff --check` | 退出码 `0`，无输出 |

上方保留较早的 `926 passed, 1 skipped, 1 failed`，它是发现陈旧历史断言的回归证据；不会把它与单节点复跑拼接为全绿。权威的修复后完整套件是随后独立运行的 `930 passed, 1 skipped`。

## 并发与取消事实

Heartbeat 续租精确 Job/worker/token，complete/fail 使用相同 CAS，因此旧协调器通常不能覆盖后继 Job 结果。但 CLI handler 为同步函数并通过 `asyncio.to_thread` 移出事件循环；取消 asyncio 包装任务无法强制停止底层线程。失租或 heartbeat 存储故障后，旧下载/导出工作仍可能运行，同时后继或后续有界 Job 继续推进。本执行不验收协作式取消、强制终止、多 worker HA 或全部取消微窗口。

## 真人资格验证

| 平台 | 真人登录 | 作者/detail 流量 | 签名 CDN 下载 | 真实扫描与播放 |
| --- | --- | --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

离线 fixture/fake-child/direct transport 证据绝不改变真人表。手机号登录仍不支持，也不宣称七平台完整下载能力。
