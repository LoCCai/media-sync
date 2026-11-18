[English](verification.md) | **中文**

# 验证：SQLite 暂态凭据残留加固

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 泄漏复现 | `CONFIRMED` | 修复前，`0003` 升级在默认长临时路径上把哨兵留在字节 132972（第 32 页）；同一测试在短 `--basetemp` 下通过。 |
| 机制隔离 | `CONFIRMED` | 同一份升级前副本用带 `secure_delete=ON` 连接监听器的升级执行后不含哨兵；不带该 pragma 则含有。升级后 `VACUUM` 同样能清除，因此残留是空闲页保留。 |
| 连接策略测试 | `PASS` | `tests/integration/test_database.py::test_sqlite_pragmas_and_nested_work_rollback` 现在于既有 `foreign_keys`/`journal_mode`/`busy_timeout` 断言旁断言 `PRAGMA secure_delete == 1`。 |
| `0003` 结果测试 | `PASS` | `tests/integration/test_packaged_migrations.py::test_0003_upgrade_preserves_only_complete_verified_legacy_asset` 在默认长临时路径与此前失败的深层 `--basetemp` 上都通过。 |
| 数据库切片 | `PASS` | `tests/integration/test_database.py`：`26 passed in 11.16s`。 |
| 完整 Python 套件 | `PASS` | `7198 passed, 63 skipped, 108 warnings in 1514.94s`。跳过项为已记录的 Windows/POSIX 符号链接、POSIX 目录与 PostgreSQL URL 分支。 |
| Ruff lint / format | `PASS` | `ruff check src tests` → `All checks passed!`；`ruff format --check src tests` → `438 files already formatted`。 |
| strict mypy | `PASS` | `mypy --strict src` → `Success: no issues found in 169 source files`。 |
| 文档 / 上游 | `PASS` | `scripts/check_docs.py` → `Documentation links OK`；`scripts/check_upstreams.py` → `Upstreams OK (2 locked checkouts verified)`。文档计数在新增四个 0082 文件之前采集，收尾重跑覆盖它们。 |
| Web 门禁 | `PASS` | `svelte-check` → `0 errors and 0 warnings`；`vitest` → `30 files / 843 tests`；本执行未触及前端源码。 |
| 部署 / Linux 主机 | `NOT_RUN` | 未做任何部署。 |
| 既有部署的追溯擦除 | `NOT_RUN` | 需操作者执行 `VACUUM`；明确不在范围内。 |

## 跑门禁时的另一项发现

本工作站第一次完整套件以 `2 failed, 7196 passed` 结束。第二个失败 `test_timeout_and_cancellation_kill_entire_tree[cancel]` 是时序敏感的进程树断言；它在三次连续单测重跑与最终完整套件中都通过。由于未观察到确定性机制，这里记录为抖动，而不是修复。

另有两个 0081 测试文件在提交时未格式化，使本应干净的树上 `ruff format --check` 失败。本次一并格式化，让全仓门禁反映真实状态。

## 已运行命令

```text
python -m pytest -q
python -m pytest tests/integration/test_database.py -q
python -m pytest tests/integration/test_packaged_migrations.py::test_0003_upgrade_preserves_only_complete_verified_legacy_asset -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
python scripts/check_upstreams.py
npm --prefix web run check | test
git diff --check
```

## 操作者须知

清除 0082 之前就已释放的页，需要操作者在写者停止时显式执行：

```bash
docker compose stop media-sync supervisor
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/python media-sync \
  -c "import sqlite3; c=sqlite3.connect('<数据库路径>'); c.execute('VACUUM'); c.close()"
docker compose up -d --no-deps media-sync
```

数据库路径必须先从部署的 `MEDIA_SYNC_DATABASE_URL` 读出，不要照抄示例占位符。
