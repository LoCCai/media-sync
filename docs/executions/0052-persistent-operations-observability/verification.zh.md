[English](verification.md) | **中文**

# 执行 0052 验证

- 状态：仅完成变更前基线；实现验证待运行
- 日期：2026-09-04
- 基线：`d64b97b`

## 已记录基线

| 检查 | 结果 |
| --- | --- |
| Git 同步 | `HEAD == origin/main == GitHub main == d64b97bcec96e182d64685bea951281559a96743`；仅保留既存 `?? .mimosa/` |
| 前驱完整套件 | 执行 0051 已记录 `2135 passed, 3 skipped`；三项 skip 均为 Windows 不适用的 POSIX venv/权限用例 |
| 当前关键回归 | `uv run --frozen pytest -q -p no:cacheprovider tests/unit/test_mediacrawler_capabilities.py tests/unit/test_workbench.py tests/unit/test_login_preflight.py tests/unit/test_api_workbench.py tests/unit/test_api_server.py tests/unit/test_cli.py tests/contract/test_mediacrawler_login.py` → `PASS` — 186 passed，另有一项 Starlette/httpx 弃用 warning |
| 文档 | `uv run --frozen python scripts/check_docs.py` → `PASS` — 新增八份 0052 记录前共检查 458 个 Markdown 文件 |
| 锁定上游 | `uv run --frozen python scripts/check_upstreams.py` → `PASS` — 2 个锁定 checkout |
| 仓库空白 | 新增 0052 记录前 `git diff --check` → `PASS` |

实现、migration、SSE、取消、Web、打包与完整套件结果均待运行。

## 证据口径

本基线未使用真人账户、平台 API/CDN、下载的作者媒体或 Emby/Jellyfin 服务。全部此类行继续在 Execution 0047 下保持 `NOT_RUN`。
