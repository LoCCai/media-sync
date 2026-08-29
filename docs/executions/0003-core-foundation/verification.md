# Execution 0003 verification / 执行 0003 验证

- Verification date / 验证日期：2026-08-30
- Network/account policy / 网络与账户策略：automated tests only; no live platform calls / 仅自动测试，不调用真人平台。

## Final quality gate / 最终质量门禁

| Check / 检查 | Command / 命令 | Status / 状态 |
| --- | --- | --- |
| Locked dependencies / 锁定依赖 | `uv sync --all-groups --locked` | PASS — 44 resolved, 43 audited / 通过 |
| Lint / 代码规范 | `uv run ruff check .` | PASS / 通过 |
| Format / 格式 | `uv run ruff format --check .` | PASS — 69 files / 通过 |
| Strict types / 严格类型 | `uv run mypy src/media_sync` | PASS — 26 source files / 通过 |
| Tests / 测试 | `uv run pytest` | PASS — 83 tests in 6.29s / 通过 |
| Coverage / 覆盖率 | `uv run pytest --cov=media_sync --cov-report=term` | PASS — 83 tests, 86% total / 通过 |
| Package build / 包构建 | `uv build` | PASS — sdist and wheel / 通过 |
| Packaged migrations / 随包迁移 | `tests/integration/test_packaged_migrations.py` in pytest / pytest 中执行该文件 | PASS — source and unpacked-wheel upgrade / 通过源码与解包 wheel 升级 |
| SQLite repositories / SQLite 仓储 | `tests/integration/test_database.py` in pytest / pytest 中执行该文件 | PASS — 12 integration cases / 通过 12 个集成用例 |
| Sync persistence / 同步持久化 | `tests/integration/test_sync_pipeline.py` in pytest / pytest 中执行该文件 | PASS — two-pass idempotency and rollback / 通过双轮幂等与回滚 |
| CLI workflow / CLI 工作流 | `tests/integration/test_cli_workflow.py` in pytest / pytest 中执行该文件 | PASS — init→account→subscription→two syncs / 通过完整流程 |
| CLI discovery / CLI 发现 | `uv run media-sync --help` | PASS — db/account/subscription/sync commands listed / 通过 |
| Database inspection / 数据库检查 | isolated `media-sync db status --json` in CLI tests / CLI 测试中的隔离状态检查 | PASS — current revision and 10/10 tables; missing DB exits 1 without creating it / 通过 |
| Doctor / 环境诊断 | `uv run media-sync doctor --json` | PASS — Python 3.11.8, tools detected, no database URL / 通过 |
| Documentation / 文档 | `uv run python scripts/check_docs.py` | PASS — 28 Markdown files / 通过 |
| Upstream locks / 上游锁定 | `uv run python scripts/check_upstreams.py` | PASS — 2 pinned checkouts / 通过 |
| Patch whitespace / 补丁空白 | `git diff --check` | PASS / 通过 |

## Behavioral evidence / 行为证据

- The SQLite integration suite checks foreign keys, uniqueness, platform/content/asset/job vocabularies, migration/metadata parity, concurrent upsert identity, monotonic watermarks, run-state CAS, event order, exclusive claims, lease expiry and fencing.
- The synchronization integration suite performs two Fake runs through the real SQLAlchemy adapter and finishes with exactly 1 author, 4 contents, 4 assets, 2 runs and 10 ordered run events. Per-run discovered/asset counters equal the application result.
- A failure injected on the second content write proves that an outer transaction abort removes every author/content/asset/run/event write from that failed attempt.
- The wheel test imports `media_sync` from an unpacked built wheel—not the source tree—and upgrades an empty SQLite database to revision `0001_core`.
- CLI tests verify unsupported phone login, malformed enums, raw Cookie-like credential input, subscription conflicts and injected domain errors fail without persisting or printing sentinel secrets.

- SQLite 集成套件验证外键、唯一性、平台/内容/资产/任务词汇、迁移与 ORM 一致性、并发 upsert 身份一致、单调水位、运行状态 CAS、事件顺序、排他领取、租约过期和 fencing。
- 同步集成套件通过真实 SQLAlchemy 适配器执行两轮 Fake 同步，最终精确得到 1 位作者、4 条内容、4 个资产、2 次运行和 10 条有序事件；每轮发现/资产计数与应用结果一致。
- 在第二条内容写入时注入失败，证明外层事务中止会移除该失败尝试的全部作者/内容/资产/运行/事件写入。
- wheel 测试从解包后的构建产物而非源码树导入 `media_sync`，并把空 SQLite 数据库升级到 `0001_core`。
- CLI 测试验证手机号登录、非法枚举、疑似原始 Cookie 的凭据输入、订阅冲突和注入领域错误都会安全失败，且不会持久化或打印哨兵密钥。

## Live qualification / 线上资格验证

| Platform / 平台 | Login / 登录 | Creator scan / 作者扫描 | Media / 媒体 | Status / 状态 |
| --- | --- | --- | --- | --- |
| `xhs` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `dy` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `ks` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `bili` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `wb` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `tieba` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `zhihu` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |

No credentials, browser profiles, platform endpoints or live media were used. Automated Fake/fixture results do not change this matrix. / 未使用凭据、浏览器配置、平台端点或真实媒体；Fake/夹具自动化结果不会改变该矩阵。
