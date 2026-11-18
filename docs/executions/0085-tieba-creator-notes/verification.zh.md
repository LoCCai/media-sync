[English](verification.md) | **中文**

# 验证：贴吧创作者主题耐久交付

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 扫描状态机 | `PASS` | `tests/unit/test_tieba_creator_work.py`（12 项）：`tb-work-v1:` 游标字节精确往返并拒绝绑定变更；四种停止原因互不混淆；`max_items` 保留同一页码并重列同一页；重复身份元组累计停滞并在有界次数阻塞；头部对账复现边界；覆盖经 JSON 行往返；页码与 thread id 均有界。 |
| 捕获 shim | `PASS` | `tests/contract/test_tieba_creator_capture.py`（10 项）：只有 `thread_info.tid`/`id` 身份留存，持久页映射不含 `thread_info` 或标题；六种模糊形状被拒；空列表作为有效页接受；`DataFetchError` 记录 `access_restricted` 且无边界；完整页到达 `has_more_false`。 |
| 交付迁移 | `PASS` | `tests/integration/test_tieba_creator_notes_delivery.py`（3 项）：封闭回执使 backfill → reconciling → incremental 并记录 `last_page_number == 1`；受限单元以 `tieba_access_restricted` 阻塞且无源末；终态失败以固定码阻塞。 |
| 单事务摄取 | `PASS` | 同一集成文件经生产路径驱动 `ingest_tieba_bounded`，页、游标、Run 与 Content 一同提交。 |
| 迁移 | `PASS` | `tests/integration/test_database.py` 证明迁移后的 schema 等于元数据（29 张域表）并可干净降级；`tests/integration/test_packaged_migrations.py` 证明 wheel 携带 `0019_tieba_creator_notes` 并把它报告为 head。 |
| 头修订钉定 | `PASS` | 打包迁移、数据库域表、CLI 预期/已知修订与表计数（29）、离线/调度管线修订断言、CLI 支持包与 API 支持包都推进到 `0019_tieba_creator_notes`。 |
| 管理/桥接接线 | `PASS` | 安装第六个有界契约后，`tests/contract/test_mediacrawler_bridge.py`、`tests/integration/test_mediacrawler_scheduler_handler.py`、`tests/integration/test_pipeline_worker.py` 与 `tests/integration/test_scheduler_repository.py` 通过。 |
| 完整 Python 套件 | `PASS` | `7281 passed, 63 skipped, 108 warnings in 1525.68s`。跳过项为已记录的 Windows/POSIX 符号链接、POSIX 目录与 PostgreSQL URL 分支。 |
| Ruff lint / format | `PASS` | `ruff check src tests` → `All checks passed!`；`ruff format --check src tests` → 全部已格式化。 |
| strict mypy | `PASS` | `mypy --strict src` → `Success: no issues found in 178 source files`。 |
| 文档 / 上游 | `PASS` | `scripts/check_docs.py` → 链接 OK（846 篇）；`scripts/check_upstreams.py` → `Upstreams OK (2 locked checkouts verified)`。 |
| Web 门禁 | `PASS` | `svelte-check` → `0 errors and 0 warnings`；`vitest` → `30 files / 843 tests`；Prettier → 干净。本执行未改动前端。 |
| Docker / Linux 主机 / 真人登录 / 真实请求 | `NOT_RUN` | 未部署、未使用账户、未发平台请求、未取真实字节。 |

## 一处门禁观察

该树首次完整运行以 `1 failed, 7281 passed` 结束。失败项 `test_log_center_api.py::test_old_operation_has_explicit_missing_stage_evidence_and_bounded_controls` 在整文件隔离重跑中通过（`30 passed`），因此记录为对顺序或时序敏感的测试，而不是本执行引入的缺陷。未发现机制，因此未改动。

## 边界说明

- `has_more_false` 是**服务端声明**的结束，连同页见证保留，但它仍只开启对账；只有稳定的头部重列才推进到增量。
- 由于页码总是递增，持续返回同一页的服务端对游标本身不可见。因此耐久层比较页身份元组，并在有界次数的零进展单元后以 `tieba_page_stalled` 阻塞。
- 业务 `error_code != 0`、畸形响应体、`DataFetchError`/`IPBlockError` 或传输失败都是 `access_restricted`，绝不是源末。

## 已运行命令

```text
python -m pytest -q
python -m pytest tests/unit/test_tieba_creator_work.py tests/contract/test_tieba_creator_capture.py -q
python -m pytest tests/integration/test_tieba_creator_notes_delivery.py -q
python -m pytest tests/integration/test_packaged_migrations.py tests/integration/test_database.py -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
python scripts/check_upstreams.py
npm --prefix web run check | test | format:check
git diff --check
```
