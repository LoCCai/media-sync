[English](verification.md) | **中文**

# 执行 0040 验证

- 状态：静态门在编写工作站通过；API 测试与完整套件在 Linux 部署主机运行
- 日期：2026-09-03

## 已实现证据

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 严格 mypy | `uv run mypy --strict src` | 0 | `no issues found in 87 source files`（含 `api.py`） |
| Ruff 与格式 | `uv run ruff check src/ tests/ scripts/`; `uv run ruff format --check src/ tests/ scripts/` | 0 | `All checks passed!`；`178 files already formatted` |
| 字节编译 | `uv run python -m compileall -q src/media_sync` | 0 | OK |
| 文档链接 | `uv run python scripts/check_docs.py` | 0 | `342 Markdown files checked` |
| 含 API 测试的收集 | `uv run pytest --collect-only -q tests/unit/test_api_server.py …` | 0 | `385 tests collected in 2.22s` |
| CLI 面 | `uv run media-sync --help` | 0 | `serve` 命令已列出；uv 0.12.9 + Python 3.13.15 |

## 移交 Linux 部署主机

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| API 契约测试 | `uv run pytest -q tests/unit/test_api_server.py` | 本工作站 `NOT_RUN` |
| 完整套件 | `uv run pytest -q` | 本工作站 `NOT_RUN` |
| 真机 `serve` + 控制台 + QR 中继 | `docker compose up` + 浏览器 | 属执行 0041 部署清单 |

本执行不声明任何真人登录/抓取/下载行。
