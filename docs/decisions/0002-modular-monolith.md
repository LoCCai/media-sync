**English** | [中文](0002-modular-monolith.zh.md)

# ADR-0002: Python modular monolith with adapter and durable-job boundaries

- Status: Accepted
- Date: 2026-08-30

## Context

The requested scope spans browser login, seven heterogeneous platforms, scheduling, stateful downloads and filesystem export. Starting with distributed services would multiply deployment and failure modes, while directly extending either upstream would inherit a restrictive license or a Bilibili-only Rust architecture.

## Decision

Use a Python 3.11+ modular monolith with strict domain/application/infrastructure boundaries. Use a durable SQLite job model from the beginning. Treat every crawler implementation, including MediaCrawler, as a capability-reporting adapter. Keep Emby rendering and asset download independent of adapters.

## Consequences

- One executable and database remain easy to install, test and back up.
- SQLite requires a deliberate single-writer/short-transaction policy.
- Clear ports enable deterministic fake adapters and progressive native adapters.
- Browser-heavy work remains out-of-process for isolation and license clarity.
- A future PostgreSQL/worker split is possible without changing public use cases.
