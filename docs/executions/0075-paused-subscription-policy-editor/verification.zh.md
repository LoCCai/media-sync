[English](verification.md) | **中文**

# 验证

实现 revision：`aec3eac`（`feat(policy): add paused subscription policy editor`）。计划基线：`32d1a3e`。

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 策略/API/CLI/鉴权专项回归 | `PASS` | `40 passed, 2 skipped, 1 warning in 16.89s`。两项跳过是显式可选的真实 PostgreSQL writer 竞态和活动 operation NOWAIT 检查，因为未配置 `MEDIA_SYNC_TEST_POSTGRESQL_URL`。 |
| Python 完整套件 | `PASS` | `7067 passed, 43 skipped, 108 warnings in 1638.69s (0:27:18)`。既有跳过包括 OS 特定和未配置 PostgreSQL 的资格分支，以及套件内 `uv` PATH 检查；制品构建另用已配置的 `uv` 绝对路径完成。warning 仍为既有 Starlette/httpx 与 Python 3.12+ SQLite adapter 弃用提示。 |
| media-sync Web 完整套件 | `PASS` | 最终前端源码通过 `27 files / 818 tests`。 |
| Svelte 与 Web 生产构建 | `PASS` | `svelte-check` 为 0 errors、0 warnings；Vite 转换 4,087 个服务端和 4,096 个客户端模块并写出静态构建。 |
| 前端格式 | `PASS` | Web 全仓 Prettier 检查通过。 |
| 桌面/移动渲染交互 | `PASS` | 本会话没有 Browser 插件，因此使用 bundled Playwright 1.62.1 与本机 Chrome 检查 `http://127.0.0.1:8765/subscriptions`。页面身份/标题、非空内容和无框架错误层均通过；B 站与 XHS 保存后仍为 `paused`，XHS 响应没有 `bili_scope`。桌面 1440×900 与移动 390×844 截图覆盖保存前后；控制台警告/错误、页面异常和失败请求均为 0。没有真人平台请求。 |
| Python lint/format/type/compile | `PASS` | Ruff lint 通过；修正一处纯格式空行后，Ruff format 报告 406 个文件已格式化；strict mypy 通过 156 个源码文件；`src`、`tests`、`scripts` compileall 通过。 |
| 锁文件与上游 | `PASS` | `uv lock --check` 保持 62 个包不变；`scripts/check_upstreams.py` 验证两个锁定 checkout。MediaCrawler 仍锁定在 `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`。 |
| Python 制品 | `PASS` | 新建 774,650 字节 wheel（180 个成员）及 3,116,025 字节 sdist（1,284 个成员）成功；两者都包含 `subscription_policy_update.py`，成员列表不含 QA 路径、截图、数据库或环境文件。 |
| 文档链接/空白 | `PASS` | 最终双语收尾通过文档检查器和 `git diff --check`；准确文档数由收尾提交记录。 |
| Docker/Linux 部署及真人服务 | `NOT_RUN` | 未操作镜像/容器、真人平台/CDN、宿主归档/媒体库/NFO、媒体服务器或 supervisor。 |

## 执行命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/integration/test_subscription_policy_update.py tests/unit/test_api_subscription_policy.py tests/unit/test_cli.py::test_subscription_policy_cli_updates_only_a_paused_current_mediacrawler_subscription tests/unit/test_operator_auth_api.py -q --tb=short

pnpm --dir web run format:check
pnpm --dir web test
pnpm --dir web run check
pnpm --dir web run build

.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m ruff format --check src tests scripts
.\.venv\Scripts\python.exe -m mypy --strict src/media_sync
.\.venv\Scripts\python.exe -m compileall -q src tests scripts
& 'C:\Users\sueli\.local\bin\uv.exe' lock --check
.\.venv\Scripts\python.exe scripts/check_upstreams.py
.\.venv\Scripts\python.exe scripts/check_docs.py
git diff --check
& 'C:\Users\sueli\.local\bin\uv.exe' build --out-dir <temporary-directory>
```

## 资格结论

本地策略修改接缝已对封闭校验、乐观并发、暂停/空闲所有权、精确保留、固定脱敏控制面及 B 站/XHS 渲染交互取得资格。通用编辑器已接入全部 MediaCrawler 平台，但这不代表它们的来源分页、真人采集或交付已通过。真实 PostgreSQL 及全部部署/真人行继续明确为 `NOT_RUN`。
