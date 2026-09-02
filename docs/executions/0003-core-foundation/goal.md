**English** | [中文](goal.zh.md)

# Execution 0003 goal

Deliver the first installable, network-free vertical slice: package configuration, framework-independent domain contracts, SQLite/Alembic persistence, a durable job state model, a deterministic fake platform, and basic CLI operations.

## Acceptance

- `uv sync` produces a locked development environment.
- Alembic upgrades an empty SQLite database to the current schema.
- Platform/account/author/subscription/content/asset/run/job/export uniqueness and relationships are enforced.
- Invalid domain transitions fail; expired job leases can be reclaimed.
- Replaying the same fake creator page does not duplicate authors or content.
- CLI initializes and inspects an isolated test database.
- Ruff, mypy and pytest pass, with exact evidence saved here.
