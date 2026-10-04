[English](verification.md) | **中文**

# 验证：快手创作者作品耐久交付（0081）

计划基线：本目录中冻结的计划（提交 `47ea22e`）。实现由三岗工作流（后端工程师、前端美化工程师、bug 测试员）产出，主会话复核。

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 快手扫描状态单元测试 | `PASS` | `tests/unit/test_kuaishou_creator_work.py`。规范 `ks-work-v1:` 游标往返、`max_items` 截断下的页尾重列、`no_more_echoed` / `empty_page_end` 分码且服务端回显优先、`access_restricted` ≠ 源末、停滞回显阻塞态、绑定变更拒绝。 |
| 捕获 shim 契约测试 | `PASS` | `tests/contract/test_kuaishou_creator_capture.py`。页解析隐私、歧义进度拒绝、以带签名交换逐字重放夹具封印 coverage（无离线签名）、列表受限阻塞且无源末、详情失败隔离、无签名 GraphQL 详情契约。 |
| 摄取/迁移/交付集成 | `PASS` | `tests/integration/test_kuaishou_creator_work_ingestion.py`（单事务页/游标/Run/内容，受限零提交，未证明记录拒绝）、`test_kuaishou_creator_work_migration.py`（空升级、元数据一致、护栏下线；`PARENT=0016_douyin_creator_work`、`HEAD=0017_kuaishou_creator_work`）、`test_kuaishou_creator_work_delivery.py`（backfill → 结束证据 → 对账 → 增量、受限阻塞、终端失败）。 |
| 头修订钉定回归更新 | `PASS` | `test_packaged_migrations`（wheel 携带 0015/0016/0017）、`test_cli`、`test_support_bundle`、`test_api_support_bundle`、`test_offline_media_pipeline`、`test_scheduled_offline_pipeline`、`test_deployment_provenance`（允许名单）、`test_database.py` 域表、`test_api_server.py` continuations。 |
| 完整 Python 套件 | `PASS` | 工作流测试员阶段在最终树上 `uv run pytest -q` 退出 0；收集 7261 项测试。 |
| 静态门禁 | `PASS` | compileall、`ruff check src tests`、严格 mypy（`Success: no issues found`）——运行内一轮修复后关闭时全绿。 |
| Web 门禁 | `PASS` | `npm --prefix web run check`（svelte-check）退出 0、`vitest run` 退出 0、`format:check` 退出 0——均在裸名 spawn 失败修复后由工作流以 `cmd /c npm` 执行。 |
| 三岗流程 | `PASS` | 后端工程师（三个实现单元带快门禁）、前端美化工程师（抖音面板 + 可复用映射）、bug 测试员（门禁输出的独立归因；路由后零发现）。 |
| 文档门禁 | `PASS` | 新增双语文件后 `scripts/check_docs.py` OK。 |
| Docker 镜像 / Linux 门禁 | `NOT_RUN` | 0077 交接下的操作员侧工作；不主张任何部署。 |
| 真人快手登录、真人创作者金丝雀、驻留进程重启 | `NOT_RUN` | 未使用任何平台凭据或真人爬虫。 |
| Web 生产构建（`vite build`） | `NOT_RUN` | 本运行未执行；部署重建时覆盖。 |

## 修复记录

第一次工作流运行在测试员阶段死于 `world.run("npm", …)`——Windows 上 npm 解析为 `npm.cmd`，裸名进程生成失败。修订运行复用了第一次运行写入的全部内容（后端三单元与前端面板早已落盘），仅以 `cmd /c npm` 形式重跑验证/修复尾部。裸名调用没有第二次机会。

## 已运行命令

```text
uv run pytest -q                      # 工作流内，最终树，退出 0
uv run pytest --collect-only -q       # 收集 7261 项
uv run python -m compileall -q src
uv run ruff check src tests
uv run mypy --strict src
cmd /c npm --prefix web run check | test | format:check
uv run python scripts/check_docs.py
git diff --check
```

## 给评审者的设计说明

- **为什么两个源末码。** 上游要么在服务端回显 `no_more` 时终止，要么在自己的空页覆盖时终止（client.py:434、436、440-442）。合并两者会隐藏关闭 feed 的路径；分开保留既为对账保住更强的服务端证实证据，也接受客户端推断的结束为上游终止态。
- **为什么必须有页尾重列。** 快手列表端点不接受 count 参数，耐久层无法像抖音"每页 18"契约那样把单元钳制到已知页大小。截断服务端页再按其回显推进将永久跳过页尾；契约因此以相同请求重列直至整页耗尽。
- **为什么有停滞回显防护。** 上游从不比较回显 `pcursor` 与请求 `pcursor`；持续以相同游标回显非空页的服务端会让历史泳道永远空转。耐久层统计此类停滞单元，超过有界次数后以 `kuaishou_cursor_stalled` 阻塞。
