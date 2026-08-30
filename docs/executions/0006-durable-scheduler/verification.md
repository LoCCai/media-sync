# Execution 0006 verification / 执行 0006 验证

- Status / 状态：NOT_RUN — plan commit only / 未执行 — 仅计划提交
- Network policy / 网络策略：offline mocks and generated artifacts only / 仅离线 mock 与生成产物

## Planned evidence / 计划证据

| Scope / 范围 | Planned evidence / 计划证据 | Status / 状态 |
| --- | --- | --- |
| Retry/circuit policy / 退避与 circuit 策略 | Pure unit suite with injected RNG/clock / 注入 RNG/时钟的纯单元测试 | `NOT_RUN` |
| Atomic materialization / 原子物化 | Independent SQLite concurrent tick tests / 独立 SQLite 并发 tick 测试 | `NOT_RUN` |
| Lane claim and fairness / lane 领取与公平性 | Global/platform/account/start-interval/half-open barriers / 全局、平台、账户、启动间隔、half-open barrier | `NOT_RUN` |
| 0005 isolation / 0005 隔离 | Sync reclaim leaves download/export recovery Jobs byte-identical / sync reclaim 保持下载/导出恢复 Job 逐字节不变 | `NOT_RUN` |
| Fake handler / Fake handler | Scheduled lifecycle, retry/wait classification and transaction boundaries / 调度生命周期、重试/等待分类及事务边界 | `NOT_RUN` |
| Restart pipeline / 重启流水线 | Subscribe → tick → sync → download → export → reconstruct → rerun | `NOT_RUN` |
| Secret sinks / 密钥落点 | SQLite/runtime/archive/export/operator retained-artifact byte scan / 保留产物字节扫描 | `NOT_RUN` |
| Migration / 迁移 | Empty/real-0003/source/wheel upgrade and downgrade preservation | `NOT_RUN` |

## Planned final quality gates / 计划最终质量门禁

Exact counts, timings and coverage will be recorded only after the stable implementation tree runs these gates.

只有稳定实现树实际运行后，才记录准确数量、耗时与覆盖率。

```powershell
uv sync --all-groups --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy src/media_sync
uv run pytest --cov=media_sync --cov-report=term
uv run pytest tests/unit/test_scheduler_policy.py tests/integration/test_scheduler_repository.py tests/integration/test_scheduler_worker.py -q
uv run pytest tests/integration/test_scheduler_worker.py tests/unit/test_cli.py -q
uv run pytest tests/integration/test_scheduled_offline_pipeline.py tests/integration/test_scheduler_secret_sinks.py -q
uv build
uv run pytest tests/integration/test_packaged_migrations.py -q
uv run python scripts/check_docs.py
uv run python scripts/check_upstreams.py
git diff --check
git ls-files -- archive exports jobs .media-sync dist
git status --short -- archive exports jobs .media-sync dist
```

Test filenames may be refined during implementation, but the final document must replace this planned list with commands that were actually run. Mock success must never promote live qualification rows.

测试文件名可在实现时细化，但最终文档必须用实际运行的命令替换本计划列表。mock 成功永远不得提升真人资格行。
