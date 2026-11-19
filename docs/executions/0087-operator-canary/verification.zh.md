[English](verification.md) | **中文**

# 验证：逐平台操作者金丝雀

## 最终结果

本执行只产出文档与资格记录。因此下述验证把"本地可证明"与"不可证明"分开。

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 文档结构 | `PASS` | `scripts/check_docs.py` 报告链接 OK，且 `goal`、`plan`、`progress`、`qualification` 的双语标题结构一致。 |
| 声明的停止原因与代码一致 | `PASS` | 七平台表中命名的每个停止原因都存在于对应模块：`source_end`/`head_boundary`/`item_limit`/`list_limit`/`restarted`（`bilibili_scan.py:20`）、`has_more_false`/`empty_page_stalled`（小红书、抖音）、`no_more_echoed`/`empty_page_end`（快手）、`total_inferred_end`/`empty_page_end`（微博）、`has_more_false`/`empty_page_end`（贴吧）、`is_end`/`empty_page_end`（知乎）。 |
| 声明的迁移与代码树一致 | `PASS` | `0014`–`0020` 均存在于 `src/media_sync/infrastructure/db/migrations/versions/`，元数据头为 `0020_zhihu_creator_answers`，由 `tests/integration/test_packaged_migrations.py` 与 `tests/unit/test_deployment_provenance.py` 断言。 |
| 声明的续跑设置存在 | `PASS` | 七个平台的 `MEDIA_SYNC_*_SCAN_CONTINUATION_DELAY_SECONDS` 字段都存在于 `src/media_sync/config.py`，并被调度服务与管线 worker 同时消费。 |
| 产品行为未变 | `PASS` | 完整 Python 套件仍为绿色且多了一项：`7308 passed, 62 skipped, 108 warnings`。Web 仍为 `30 files / 843 tests`；Ruff、strict mypy 与上游检查保持通过。 |
| 打包 wheel 制品门 | `PASS` | `tests/integration/test_packaged_migrations.py::test_built_wheel_contains_and_runs_packaged_migrations` 现已**真正执行**而不是跳过：真实 `uv build --wheel` 产出一个 wheel，证明该 wheel 携带 `env.py`、`script.py.mako` 与 `0001`–`0020` 全部修订，并且从解包后的 wheel 执行 `upgrade_database` 到达 `0020_zhihu_creator_answers`。为使其在本机可复现，修复了两个测试侧缺陷：必需资源集合漏了 `0018`/`0019`，且两处子进程捕获使用了本地代码页（`gbk`）而非 UTF-8 解码。 |
| 真人金丝雀（7 平台） | `NOT_RUN` | 需要 Linux 主机、真人原生登录、平台请求与 CDN 字节。 |
| 真实媒体字节（7 平台） | `NOT_RUN` | 同一边界。 |
| 零工作重放（7 平台） | `NOT_RUN` | 同一边界。 |
| 重启续跑（7 平台） | `NOT_RUN` | 同一边界。 |

## 本记录刻意不声称的内容

- 不声称任何平台已受支持。`qualification.md` 保持每一行真人工作为 `NOT_RUN`。
- 不声称推断的结束能证明完整历史；每个平台自己的记录已声明推断结束只开启对账。
- 不声称该流程已被执行过一次。

## 已运行命令

```text
python scripts/check_docs.py
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_upstreams.py
npm --prefix web run check | test | format:check
git diff --check
```
