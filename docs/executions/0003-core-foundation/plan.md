# Execution 0003 plan / 执行 0003 计划

1. Add `pyproject.toml`, environment settings and package metadata. / 添加项目配置、环境设置和包元数据。
2. Implement framework-free domain enums, snapshots, transition rules and adapter ports. / 实现框架无关领域枚举、快照、状态转换和适配端口。
3. Define SQLAlchemy models and an initial Alembic migration. / 定义 SQLAlchemy 模型和初始 Alembic 迁移。
4. Implement transactional repositories, atomic upserts and durable job leasing. / 实现事务仓库、原子 upsert 和持久任务租约。
5. Build a deterministic Fake adapter and the first sync application service. / 构建确定性 Fake 适配器和首个同步应用服务。
6. Add database/account/subscription/run CLI commands. / 添加数据库、账户、订阅、运行 CLI 命令。
7. Lock dependencies; run lint, type, unit, integration and CLI smoke checks. / 锁定依赖并运行 lint、类型、单元、集成及 CLI 冒烟验证。
8. Record results and create a bilingual local commit. / 记录结果并创建中英双语本地提交。

## Rollback and safety / 回退与安全

All tests use temporary directories and isolated SQLite files. No real account, crawler, browser, network service or user runtime directory is touched. / 所有测试使用临时目录和隔离 SQLite；不接触真人账户、爬虫、浏览器、网络服务或用户运行目录。
