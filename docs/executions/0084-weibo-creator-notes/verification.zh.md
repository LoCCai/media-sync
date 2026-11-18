[English](verification.md) | **中文**

# 验证：微博创作者笔记耐久交付

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 扫描状态机 | `PASS` | `tests/unit/test_weibo_creator_work.py`（14 项）：游标往返字节精确并拒绝绑定变更；四种停止原因互不混淆；`max_items` 保留同一 `since_id` 并重列同一页；重复回显累计停滞并在有界次数阻塞；头部对账复现边界；覆盖经 JSON 行往返；推断结束永不被报告为完整。 |
| 捕获 shim | `PASS` | `tests/contract/test_weibo_creator_capture.py`（11 项）：只有 `card_type == 9` 卡片成为身份，持久页映射不含 `mblog`、`note-*` 或标题载荷；七种模糊形状被拒绝；`DataFetchError`/假值响应体/缺失 `cards` 记录 `access_restricted` 且无边界；完整页到达 `total_inferred_end`。 |
| 交付迁移 | `PASS` | `tests/integration/test_weibo_creator_notes_delivery.py`（4 项）：封闭回执使 backfill → reconciling → incremental 且载荷暴露 `declared_total`；受限单元以 `weibo_access_restricted` 阻塞且无源末；停滞游标以 `weibo_cursor_stalled` 阻塞；终态失败以固定码阻塞。 |
| 单事务摄取 | `PASS` | 同一集成文件经生产路径驱动 `ingest_weibo_bounded`，页、游标、Run 与 Content 一同提交。 |
| 迁移 | `PASS` | `tests/integration/test_database.py` 证明迁移后的 schema 等于元数据（28 张域表）并可干净降级；`tests/integration/test_packaged_migrations.py` 证明 wheel 携带 `0018_weibo_creator_notes` 并把它报告为 head。 |
| 头修订钉定 | `PASS` | 打包迁移、数据库域表、CLI 预期/已知修订与表计数、离线/调度管线修订断言、CLI 支持包与 API 支持包都推进到 `0018_weibo_creator_notes`。 |
| 管理/桥接接线 | `PASS` | 安装第五个有界契约后，`tests/contract/test_mediacrawler_bridge.py`、`tests/integration/test_mediacrawler_scheduler_handler.py`、`tests/integration/test_pipeline_worker.py` 与 `tests/integration/test_scheduler_repository.py` 通过。 |
| 完整 Python 套件 | `PASS` | `7257 passed, 63 skipped, 108 warnings in 1667.95s`。跳过项为已记录的 Windows/POSIX 符号链接、POSIX 目录与 PostgreSQL URL 分支。 |
| Ruff lint / format | `PASS` | `ruff check src tests` → `All checks passed!`；`ruff format --check src tests` → 全部已格式化。 |
| strict mypy | `PASS` | `mypy --strict src` → `Success: no issues found in 174 source files`。 |
| 文档 / 上游 | `PASS` | `scripts/check_docs.py` → 链接 OK；`scripts/check_upstreams.py` → `Upstreams OK (2 locked checkouts verified)`。 |
| Web 门禁 | `PASS` | `svelte-check` → `0 errors and 0 warnings`；`vitest` → `30 files / 843 tests`；Prettier → 干净。本执行未改动前端。 |
| Docker / Linux 主机 / 真人登录 / 真实请求 | `NOT_RUN` | 未部署、未使用账户、未发平台请求、未取真实字节。 |

## 边界说明

- 算术结束是**声明 total 的推断**，与上游计算方式完全一致。因此 `total_inferred_end` 只开启对账；载荷继续暴露 `declared_total`，任何读者都无法把它误当历史完整的证明。
- 仍在推进 `since_id` 的空过滤页是进展而非结束；只有缺失 `total` 才产生 `empty_page_end`，重复回显被计为停滞而不是被无限静默重发。
- shim 只读取钉定的 `get_notes_by_creator` 与 `get_note_info_by_id`。`cardlistInfo` 中除 `since_id` 与 `total` 之外的更丰富字段有意不持久化。

## 已运行命令

```text
python -m pytest -q
python -m pytest tests/unit/test_weibo_creator_work.py tests/contract/test_weibo_creator_capture.py -q
python -m pytest tests/integration/test_weibo_creator_notes_delivery.py -q
python -m pytest tests/integration/test_packaged_migrations.py tests/integration/test_database.py -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
python scripts/check_upstreams.py
npm --prefix web run check | test | format:check
git diff --check
```
