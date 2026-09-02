**English** | [中文](plan.zh.md)

# Execution 0003 plan

1. Add `pyproject.toml`, environment settings and package metadata.
2. Implement framework-free domain enums, snapshots, transition rules and adapter ports.
3. Define SQLAlchemy models and an initial Alembic migration.
4. Implement transactional repositories, atomic upserts and durable job leasing.
5. Build a deterministic Fake adapter and the first sync application service.
6. Add database/account/subscription/run CLI commands.
7. Lock dependencies; run lint, type, unit, integration and CLI smoke checks.
8. Record results and create a bilingual local commit.

## Rollback and safety

All tests use temporary directories and isolated SQLite files. No real account, crawler, browser, network service or user runtime directory is touched.
