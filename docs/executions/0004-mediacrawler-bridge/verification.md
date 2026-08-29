# Execution 0004 verification / 执行 0004 验证

- Verification date / 验证日期：Pending / 待完成
- Network/account policy / 网络与账户策略：offline fixtures and fake subprocesses only / 仅离线夹具与假子进程。

## Pending checks / 待执行验证

| Check / 检查 | Command / 命令 | Status / 状态 |
| --- | --- | --- |
| Dependency lock / 依赖锁 | `uv sync --all-groups --locked` | Pending / 待执行 |
| Lint and format / 规范与格式 | `uv run ruff check .` and format check / 及格式检查 | Pending / 待执行 |
| Strict types / 严格类型 | `uv run mypy src/media_sync` | Pending / 待执行 |
| Offline tests / 离线测试 | `uv run pytest` | Pending / 待执行 |
| Bridge contracts / 桥接契约 | seven-platform dry-run and fake-child integration / 七平台 dry-run 与假子进程集成 | Pending / 待执行 |
| Secret sinks / 密钥落点 | sentinel scan across CLI, logs, SQLite and manifests / 对 CLI、日志、SQLite、manifest 的哨兵扫描 | Pending / 待执行 |
| Incrementality / 增量 | late same-timestamp item, backfill/new-head and stale-checkpoint tests / 同时间戳晚到、回填中新头部与旧检查点测试 | Pending / 待执行 |
| Package / 包 | `uv build` | Pending / 待执行 |
| Docs/upstreams/diff / 文档、上游与差异 | repository verification scripts and `git diff --check` / 仓库验证脚本 | Pending / 待执行 |

## Live qualification / 线上资格验证

All seven platforms remain `NOT_RUN` for login, creator collection and media retrieval. / 七个平台的登录、作者采集和媒体获取全部保持 `NOT_RUN`。
