[English](verification.md) | **中文**

# 验证

实现 revision：`9c81c4b`（`feat(bili): complete durable backfill and incremental delivery`）。计划基线：`3fa5139`。

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| B 站交付专项回归 | `PASS` | 已记录的两组专项分别为 `26 tests in 49.90s` 与 `147 tests in 4.70s`。覆盖 67 条投稿跨多个不超过 30 条的单元、漂移后的 68 条来源、源末尾/头部对账、重试积压部分成功、重启/事务栅栏、精确凭单/公开投影、单条新增投稿真实下载/归档/NFO 及字节不变的零工作。 |
| 登录截止时间修正 | `PASS` | 无 frame 且 child 仍存活的精确用例为 `1 test in 2.05s`；完整登录契约随后为 `68 tests in 81.78s`。单独 EOF 不再绕过父进程截止时间。 |
| Python 完整套件 | `PASS` | 修正后最终运行：`7048 passed, 41 skipped, 108 warnings in 1667.43s (0:27:47)`。skip 为平台/PostgreSQL 资格分支及套件内 `uv` PATH 检查；下方独立制品构建使用配置的 `uv` 绝对路径。warning 为既有 Starlette TestClient 与 Python 3.12+ SQLite adapter 弃用提示。 |
| 已修正的完整运行失败 | `FIXED` | 登录/schema 修正后首个允许跑完的结果为 `7037 passed, 41 skipped, 11 failed`：十项不可变预览失败共用 Windows 路径/句柄 ctime 差异，另一项快手深层 JSON 暴露 decoder 相关接受行为。独立复跑均可重现。修复后 archive preview 为 `109 tests`，相关 API/控制台联合为 `13 tests`，快手 Cookie 登录为 `117 tests`，并通过上方完整套件。 |
| media-sync Web 完整套件 | `PASS` | `26 files / 802 tests` 通过。封闭解析覆盖旧 receipt、来源 Run receipt 及保守 B 站进度回退。 |
| Svelte 与生产 Web 构建 | `PASS` | `svelte-check` 为 0 errors / 0 warnings；Vite 转换 4,086 个 server、4,095 个 client module 并完成静态构建。 |
| 前端格式 | `PASS` | 全仓 Prettier 检查通过。 |
| Python lint/格式/类型 | `PASS` | Ruff lint 通过；Ruff format 报告 400 个文件均已格式化；strict mypy 对 155 个源码文件无问题。登录修正另行重跑了 Ruff 与 strict mypy。 |
| 锁定上游 | `PASS` | `scripts/check_upstreams.py` 验证两个锁定 checkout。MediaCrawler 继续固定为 `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`，未修改上游源码。 |
| Python 制品 | `PASS` | wheel 与 sdist 重新构建成功；两者都包含 `0014_bili_delivery_baseline.py` 与 `bili_delivery_progress.py`。 |
| 文档链接/空白 | `PASS` | 加入双语执行记录后，`scripts/check_docs.py` 检查 746 个 Markdown 文件；最终 `git diff --check` 通过。 |
| Docker/Linux 部署 | `NOT_RUN` | 本次没有在目标 Linux 主机构建或部署镜像。 |
| 真人 B 站登录、profile 认领与 UID `252671524` | `NOT_RUN` | 本地验证没有使用真人账户/会话，也没有发起平台请求。 |
| 真人 CDN 字节、宿主归档/媒体库目录与 NFO | `NOT_RUN` | 受控 fixture 字节只验证代码路径；没有检查真人 CDN 响应或宿主路径。 |
| 后续真人增量周期 | `NOT_RUN` | 离线 67/68 条及单条新增 fixture 不代表真人平台后续周期。 |
| supervisor restart | `NOT_RUN` | 没有启动、停止或恢复已部署 supervisor。 |

## 执行命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/contract/test_mediacrawler_login.py::test_parent_bounds_a_no_frame_child_by_deadline_and_joins_it -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/contract/test_mediacrawler_login.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/integration/test_database.py::test_alembic_upgrade_matches_metadata_and_downgrades -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_archive_preview.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_api_explorer.py tests/unit/test_console_smoke_fixture.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_kuaishou_cookie_login.py -q --tb=short

pnpm --dir web test
pnpm --dir web run check
pnpm --dir web run build
pnpm --dir web run format:check

.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy --strict src/media_sync
.\.venv\Scripts\python.exe scripts/check_upstreams.py
.\.venv\Scripts\python.exe scripts/check_docs.py
git diff --check
C:\Users\sueli\.local\bin\uv.exe build --out-dir <temporary-directory>
```

## 资格结论

确定性本地主链已通过精确有界发现、交付凭单、下载/归档、按完整 Content 发布、源末尾对账与增量调度验证。这不是 B 站真人或 Linux 部署资格。下一份权威证据必须来自目标主机重建及明确授权的有界金丝雀。
