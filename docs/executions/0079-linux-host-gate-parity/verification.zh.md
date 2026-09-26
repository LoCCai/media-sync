[English](verification.md) | **中文**

# 执行 0079 验证

- 状态：全部本地门禁在 Linux 部署主机通过；真人行不变
- 日期：2026-09-26
- 环境：Linux 部署服务器，uv + Python 3.13、Node v22.23.3 与 pnpm 11.19.0，两个 `.upstream` checkout 均验证通过

## 已实现证据

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| Ruff | `uv run ruff check .` | 0 | 全部通过 |
| 格式 | `uv run ruff format --check .` | 0 | 1209 个文件已格式化 |
| 严格 mypy（宿主视角） | `uv run mypy --strict src` | 0 | 161 个源文件无问题 |
| 严格 mypy（win32 视角） | `uv run mypy --platform win32 --strict src` | 0 | 161 个源文件无问题 |
| 字节码 | `uv run python -m compileall -q src/media_sync` | 0 | OK |
| 锁文件 | `uv lock --check` | 0 | 62 个包已解析 |
| 文档 | `uv run python scripts/check_docs.py` | 0 | 788 个 Markdown 文件检查通过 |
| 上游 | `uv run python scripts/check_upstreams.py` | 0 | 2 个锁定 checkout 验证通过 |
| Web 类型 | `pnpm check` | 0 | svelte-check 0 错误 0 警告 |
| Web 测试 | `pnpm test` | 0 | 30 个文件 / 833 项测试通过 |
| Web 构建 | `pnpm build` | 0 | 生产构建成功 |
| Web 格式 | `npx prettier --check .` | 0 | 全部文件符合 |
| Python 完整套件 | `uv run pytest -q` | 0 | 修复后 `7132 passed, 54 skipped`（基线为 `81 failed / 7052 passed`） |

- 回归归因：基线失败集合曾在原始树（stash 源码修复）上重跑；81 个失败复现 80 个，因此仅存在一处回归且已在最终运行前修复。
- 负载抖动披露：最终 26 分钟完整套件运行中，`tests/unit/test_scheduler_supervisor.py::test_repeated_task_cancellation_during_subscription_join_waits_for_exact_attempt` 失败一次；隔离重跑 3/3 在一秒内通过。它是多租户宿主上对负载敏感的取消时序测试，与任何被改文件无关。

## 操作者行（不变）

真人 XHS 登录/CDN 投递、有界金丝雀、驻留 supervisor 周期、真实 PostgreSQL 与可选媒体服务器读取仍为 `NOT_RUN`，按 0077 交接与[`交接速查清单`](../../handoff-checklist.zh.md)受操作者门槛约束。部署主机上的绿色本地门禁只证明确定性离线契约。
