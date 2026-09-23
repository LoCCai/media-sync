[English](verification.md) | **中文**

# 执行 0078 验证

- 状态：编写工作站全部门禁以新数字通过；部署与真人行按 0077 交接仍为操作者项
- 日期：2026-09-23
- 环境：Windows 10 编写工作站、uv + Python（项目 venv）、Web 检查用 Node 22.14、ffmpeg/ffprobe 与两个 `.upstream` checkout 就绪

## 已实现证据

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| Ruff | `uv run ruff check .` | 0 | 全部通过 |
| 格式 | `uv run ruff format --check .` | 0 | 1203 个文件格式正确（门禁前回流了一行桥接代码） |
| 严格 mypy | `uv run mypy --strict src` | 0 | 162 个源文件无问题（含桥接与 settings 扩展） |
| 字节编译 | `uv run python -m compileall -q src/media_sync` | 0 | OK |
| 文档 | `uv run python scripts/check_docs.py` | 0 | `782 Markdown files checked`（速查清单、执行记录、回填索引全部链接通过） |
| 上游锁 | `uv run python scripts/check_upstreams.py` | 0 | `2 locked checkouts verified` |
| Web 格式 | `npx prettier --check .` | 0 | 清洁 |
| Web 类型 | `npx svelte-check --tsconfig ./tsconfig.json` | 0 | 0 错误 0 警告 |
| Web 测试 | `npx vitest run` | 0 | `30 files / 833 tests` 通过（新增：native-qr-relay 5 项、artifact-layers 3 项） |
| 桥接单元测试 | `uv run pytest -q tests/unit/test_webui_log_bridge.py` | 0 | `5 passed`（形状/违禁/级别收敛/绝不抛错 + 真实 `LogStore` 往返） |
| 日志中心回归 | `uv run pytest -q tests/unit/test_cli_log_center.py` | 0 | `3 passed` |
| API 回归 | `uv run pytest -q tests/unit/test_api_server.py` | 0 | `21 passed, 1 warning` |
| Python 完整套件 | `uv run pytest -q` | 0 | `7145 passed, 42 skipped, 108 warnings in 1570.98s`（0078 在 0077 的 7140 上新增 8 项；跳过项均为明确记录的 OS/PostgreSQL/`uv` 资格分支） |

## 操作者行（不变）

精确 revision 的 Docker 构建/运行、迁移 `0015`、API/supervisor 一致性、有界 XHS 金丝雀与全部真人平台行在本工作站保持 `NOT_RUN`——按 0077 交接（现浓缩为 [`handoff-checklist.zh.md`](../../handoff-checklist.zh.md)）在 Linux 主机执行。
