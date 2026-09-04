[English](verification.md) | **中文**

# 执行 0051 验证

- 状态：仅完成变更前基线；实现验证待运行
- 日期：2026-09-04
- 基线：`38e0ebe`

## 已记录基线

| 检查 | 结果 |
| --- | --- |
| Git 同步 | `HEAD == origin/main == 38e0ebeac51931889b5e90181e6974f5539104d2`；只剩既存 `?? .mimosa/` |
| 文档 | `uv run --frozen python scripts/check_docs.py` → 退出 `0`，`PASS`——450 份 Markdown |
| 锁定上游 | `uv run --frozen python scripts/check_upstreams.py` → 退出 `0`，`PASS`——两个 SHA/remote 检查；另手工确认两个 checkout 都干净 |
| Ruff | `uv run --frozen ruff check . --no-cache` → 退出 `0`，`PASS` |
| Ruff format | `uv run --frozen ruff format --check .` → 退出 `0`，`PASS`——628 个文件已格式化 |
| strict mypy | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run --frozen mypy --strict --no-incremental src` → 退出 `0`，`PASS`——87 个源码文件 |
| API/migration/checkout-license 冒烟 | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run --frozen pytest -q -p no:cacheprovider tests/unit/test_api_server.py tests/integration/test_packaged_migrations.py tests/contract/test_mediacrawler_bridge.py -k "api_server or packaged or checkout or license"` → 退出 `0`，`PASS`——32 项通过、62 项取消选择，一个 Starlette/httpx 弃用警告 |
| 前端门 | 基线时 `NOT_RUN`——缺少 `web/node_modules`；冻结安装是实现第一步 |
| Python 完整套件 | 本执行基线时 `NOT_RUN`；Execution 0050 仍是最新 Windows 全量证据 |

实现、Web、打包、完整套件和真人/Docker 结果仍待运行。

## 证据口径

本轮未使用真人账户、平台 API/CDN 或 Emby/Jellyfin 服务器；这些行保持 `NOT_RUN`，本地夹具和浏览器测试只标为离线证据。
