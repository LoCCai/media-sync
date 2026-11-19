[English](verification.md) | **中文**

# 验证：知乎创作者回答耐久交付

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 扫描状态机 | `PASS` | `tests/unit/test_zhihu_creator_work.py`（13 项）：`zh-work-v1:` 游标字节精确往返并拒绝绑定变更；四种停止原因互不混淆；较小 `max_items` 只请求并消耗自己的 `limit`；未完成页保留同一 offset；重复身份元组累计位移并以 `zhihu_window_shifted` 阻塞；头部对账通过 `unchanged` 回答复现边界；覆盖经 JSON 行往返；失败详情不掩盖无关回答；offset 与 content id 均有界。 |
| 捕获 shim | `PASS` | `tests/contract/test_zhihu_creator_capture.py`（9 项）：只有回答 id 留存，持久页映射不含正文或 `content_text`；六种模糊形状被拒；`DataFetchError` 记录 `access_restricted` 且无边界；完整页到达 `is_end`。 |
| 交付迁移 | `PASS` | `tests/integration/test_zhihu_creator_answers_delivery.py`（3 项）：封闭回执使 backfill → reconciling → incremental 并记录 `last_offset == 0`；受限单元以 `zhihu_access_restricted` 阻塞且无源末；终态失败以固定码阻塞。 |
| 单事务摄取 | `PASS` | 同一集成文件经生产路径驱动 `ingest_zhihu_bounded`，页、游标、Run 与 Content 一同提交。 |
| 迁移 | `PASS` | `tests/integration/test_database.py` 证明迁移后的 schema 等于元数据（30 张域表）并可干净降级；`tests/integration/test_packaged_migrations.py` 证明 wheel 携带 `0020_zhihu_creator_answers` 并把它报告为 head。 |
| 头修订钉定 | `PASS` | 打包迁移、数据库域表、CLI 预期/已知修订与表计数（30）、离线/调度管线修订断言、CLI 支持包与 API 支持包都推进到 `0020_zhihu_creator_answers`。 |
| 桥接/handler 接线 | `PASS` | 安装第七个有界契约后，`tests/contract/test_mediacrawler_bridge.py`、`tests/integration/test_mediacrawler_scheduler_handler.py`、`tests/integration/test_pipeline_worker.py` 与 `tests/integration/test_scheduler_repository.py` 通过。 |
| 完整 Python 套件 | `PASS` | `7307 passed, 63 skipped, 108 warnings in 1833.35s`。跳过项为已记录的 Windows/POSIX 符号链接、POSIX 目录与 PostgreSQL URL 分支。 |
| Ruff lint / format | `PASS` | `ruff check src tests` → `All checks passed!`；`ruff format --check src tests` → 全部已格式化。 |
| strict mypy | `PASS` | `mypy --strict src` → `Success: no issues found in 182 source files`。 |
| 文档 / 上游 | `PASS` | `scripts/check_docs.py` → 链接 OK；`scripts/check_upstreams.py` → `Upstreams OK (2 locked checkouts verified)`。 |
| Web 门禁 | `PASS` | `svelte-check` → `0 errors and 0 warnings`；`vitest` → `30 files / 843 tests`；Prettier → 干净。本执行未改动前端。 |
| Docker / Linux 主机 / 真人登录 / 真实请求 | `NOT_RUN` | 未部署、未使用账户、未发平台请求、未取真实字节。 |

## 边界说明

- `paging.is_end` 是**服务端声明**的结束，连同页见证保留，但它只开启对账；只有稳定的头部重列才推进到增量。
- 整数 offset 是 page*limit 的乘积，因此一次插入或删除会位移窗口，而每个响应看起来仍然有效。因此耐久层比较页身份元组；非空交集会重放同一 offset，并在有界次数的位移单元后以 `zhihu_window_shifted` 阻塞。
- 假值或畸形响应体、`DataFetchError`/`IPBlockError` 或传输失败都是 `access_restricted`，绝不是源末。

## 已运行命令

```text
python -m pytest -q
python -m pytest tests/unit/test_zhihu_creator_work.py tests/contract/test_zhihu_creator_capture.py -q
python -m pytest tests/integration/test_zhihu_creator_answers_delivery.py -q
python -m pytest tests/integration/test_packaged_migrations.py tests/integration/test_database.py -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
python scripts/check_upstreams.py
npm --prefix web run check | test | format:check
git diff --check
```
