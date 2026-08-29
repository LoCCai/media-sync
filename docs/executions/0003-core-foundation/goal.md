# Execution 0003 goal / 执行 0003 目标

Deliver the first installable, network-free vertical slice: package configuration, framework-independent domain contracts, SQLite/Alembic persistence, a durable job state model, a deterministic fake platform, and basic CLI operations.

交付首个可安装、无需网络的垂直切片：项目配置、框架无关领域契约、SQLite/Alembic 持久化、持久任务状态模型、确定性 Fake 平台和基础 CLI。

## Acceptance / 验收

- `uv sync` produces a locked development environment.
- Alembic upgrades an empty SQLite database to the current schema.
- Platform/account/author/subscription/content/asset/run/job/export uniqueness and relationships are enforced.
- Invalid domain transitions fail; expired job leases can be reclaimed.
- Replaying the same fake creator page does not duplicate authors or content.
- CLI initializes and inspects an isolated test database.
- Ruff, mypy and pytest pass, with exact evidence saved here.

- `uv sync` 生成锁定的开发环境。
- Alembic 可把空 SQLite 数据库升级到当前模型。
- 平台、账户、作者、订阅、内容、资产、运行、任务、导出的唯一性与关系受约束。
- 非法领域状态转换失败；过期任务租约可重新领取。
- 重放同一 Fake 作者页面不产生重复作者或内容。
- CLI 可初始化和检查隔离测试数据库。
- Ruff、mypy、pytest 全部通过，并在此保存准确证据。
