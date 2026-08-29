# ADR-0002: Python modular monolith with adapter and durable-job boundaries

# ADR-0002：采用带适配器与持久任务边界的 Python 模块化单体

- Status / 状态：Accepted / 已接受
- Date / 日期：2026-08-30

## Context / 背景

The requested scope spans browser login, seven heterogeneous platforms, scheduling, stateful downloads and filesystem export. Starting with distributed services would multiply deployment and failure modes, while directly extending either upstream would inherit a restrictive license or a Bilibili-only Rust architecture.

需求横跨浏览器登录、七种异构平台、调度、有状态下载和文件系统导出。直接从分布式服务起步会放大部署与故障面；直接扩展任一上游则会继承受限许可证，或被限制在仅 B 站的 Rust 架构中。

## Decision / 决策

Use a Python 3.11+ modular monolith with strict domain/application/infrastructure boundaries. Use a durable SQLite job model from the beginning. Treat every crawler implementation, including MediaCrawler, as a capability-reporting adapter. Keep Emby rendering and asset download independent of adapters.

采用 Python 3.11+ 模块化单体，并严格划分领域、应用和基础设施层；从一开始就使用 SQLite 持久任务模型；把包括 MediaCrawler 在内的每个爬虫实现都视为能够报告能力的适配器；Emby 渲染与资产下载独立于适配器。

## Consequences / 影响

- One executable and database remain easy to install, test and back up.
- SQLite requires a deliberate single-writer/short-transaction policy.
- Clear ports enable deterministic fake adapters and progressive native adapters.
- Browser-heavy work remains out-of-process for isolation and license clarity.
- A future PostgreSQL/worker split is possible without changing public use cases.
