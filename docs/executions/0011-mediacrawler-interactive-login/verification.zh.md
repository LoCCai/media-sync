[English](verification.md) | **中文**

# 执行 0011 验证

- 验证状态：离线实现与自动验证范围为 `PASS`，并已记录在本地提交 `8bb16f6`；全部真人行保持 `NOT_RUN`
- 验证日期：2026-08-31
- 前置：Execution 0010 commit `f2e5899`
- 验收边界：先验收离线仓储/fake-child/CLI/调度协议；全部真人账户行保持 `NOT_RUN`

## 当前已有专项证据

| 范围 | 命令或证据 | 结果 |
| --- | --- | --- |
| 仓储状态机 | `uv run pytest -q tests/integration/test_login_session_repository.py` | `PASS` — `32 passed in 6.55s` |
| 应用编排 | `uv run pytest -q tests/integration/test_mediacrawler_login_application.py` | `PASS` — `33 passed in 6.64s` |
| 仓储、应用与登录模型组合 | `uv run pytest -q tests/integration/test_login_session_repository.py tests/integration/test_mediacrawler_login_application.py tests/unit/test_mediacrawler_login.py` | `PASS` — `83 passed in 13.13s` |
| 七平台仅登录协议及进程超时、取消、join | `uv run pytest tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py -q` | `PASS` — `42 passed in 23.57s` |
| 仅登录 lint | `uv run ruff check src/media_sync/integrations/mediacrawler/login.py src/media_sync/integrations/mediacrawler/login_runner.py src/media_sync/integrations/mediacrawler/__init__.py tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py` | `PASS` — `All checks passed!` |
| 仅登录格式 | `uv run ruff format --check src/media_sync/integrations/mediacrawler/login.py src/media_sync/integrations/mediacrawler/login_runner.py src/media_sync/integrations/mediacrawler/__init__.py tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py` | `PASS` — `5 files already formatted` |
| 仅登录类型 | `uv run mypy src/media_sync/integrations/mediacrawler/login.py src/media_sync/integrations/mediacrawler/login_runner.py` | 两个源码文件无问题 |
| 仅登录包导出 | `uv run python -c "from media_sync.integrations.mediacrawler import LOGIN_ONLY_CRAWLER_TYPE, LOGIN_RUNNER_SCHEMA_VERSION, MediaCrawlerLoginMode, MediaCrawlerLoginProcessRunner, MediaCrawlerLoginRequest, MediaCrawlerLoginResult, MediaCrawlerLoginRunner, MediaCrawlerLoginStatus, SavedSessionQrFallbackBlocked, fence_saved_session_qr_fallback; print(LOGIN_ONLY_CRAWLER_TYPE, LOGIN_RUNNER_SCHEMA_VERSION, MediaCrawlerLoginMode.INTERACTIVE_QR.value)"` | 导入成功 |
| 应用 lint、格式与类型 | 针对 `authentication.py`、应用导出及应用集成测试运行专项检查 | Ruff 通过、三个文件格式正确、mypy 无问题 |
| saved-session forward/detail/调度审计 | `uv run pytest -q tests/unit/test_mediacrawler_saved_session.py` | `PASS` — `25 passed in 0.97s` |
| saved-session 审计 lint/格式 | `.venv\Scripts\ruff.exe check tests/unit/test_mediacrawler_saved_session.py`<br>`.venv\Scripts\ruff.exe format --check tests/unit/test_mediacrawler_saved_session.py` | `PASS` — `All checks passed!`; `1 file already formatted` |
| saved-session 集成类型 | `.venv\Scripts\mypy.exe src/media_sync/integrations/mediacrawler/policies.py src/media_sync/integrations/mediacrawler/runner.py src/media_sync/integrations/mediacrawler/detail_runner.py src/media_sync/scheduler/mediacrawler_handler.py src/media_sync/application/mediacrawler_download.py` | `PASS` — `Success: no issues found in 5 source files` |
| CLI 默认关闭、状态投影与脱敏 | `uv run pytest -q tests/unit/test_cli_login.py tests/unit/test_cli.py --disable-warnings --maxfail=1` | `PASS` — `77 passed in 13.36s` |
| 登录与 saved-session 交接/关闭失败合并回归 | `.venv\Scripts\python.exe -m pytest -q tests/integration/test_login_session_repository.py tests/integration/test_mediacrawler_login_application.py tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py tests/unit/test_cli_login.py tests/unit/test_cli.py tests/unit/test_mediacrawler_saved_session.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_mediacrawler_scheduler_handler.py` | `PASS` — `274 passed in 70.73s` |
| 既有 Job 的 QR 到 saved-session 闭环 | `uv run pytest -q tests/integration/test_mediacrawler_scheduler_handler.py::test_qr_login_handoff_resumes_existing_job_as_saved_session` | `PASS` — `1 passed in 0.82s` |

## 完整收尾门禁

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| 完整套件 | `uv run pytest -q` | `PASS` — `1080 passed, 1 skipped in 226.92s`; skip: `tests/contract/test_mediacrawler_supervision.py:556: POSIX mode bits are not the Windows ACL boundary` |
| 全项目 lint | `uv run ruff check .` | `PASS` — `All checks passed!` |
| 全项目格式 | `uv run ruff format --check .` | `PASS` — `198 files already formatted` |
| 全项目类型 | `uv run mypy src/media_sync` | `PASS` — `Success: no issues found in 75 source files` |
| 文档 | `uv run python scripts/check_docs.py` | `PASS` — `Documentation links OK (60 Markdown files checked).` |
| 锁定上游 | `uv run python scripts/check_upstreams.py` | 已验证两个锁定 checkout |
| 构建 | `uv build` | sdist 与 wheel 构建成功 |
| 最终密钥哨兵与保留产物审计 | 最终只读审计 | 禁止跟踪项与高置信密钥均为零，仅三个 `.test` 虚构 URL |
| 当前补丁空白 | `git diff --check` | 无输出 |

专项与完整自动门禁证明本地状态迁移、固定父子协议、有界正常父进程清理、CLI 投影、saved-session 关闭失败行为及 fake/离线七标识契约。未运行覆盖率。这些结果不证明真人二维码可渲染、不证明任何真人账户可认证、不证明平台变更后 saved session 仍有效，也不证明作者/CDN/媒体服务器流量可用。离线实现范围已完成，下方全部真人行继续保持 `NOT_RUN`。

## 已知边界

- child frame 是本地封闭结果的权威依据，不能被 `SystemExit(0)` 替代，但它不是所有远端原因的精确诊断；尤其上游 `pong() == false` 路径在到达 QR 回退 fence 前可能包含网络异常歧义。
- 派生 saved-session profile 缺失使用专用 unavailable 错误并映射为 `auth_expired`；普通 bridge 配置错误保持 `configuration_invalid`。
- 初始 QR 账户与精确 `saved_session/expired` 账户可进入显式登录；重认证启动时原子变为 `qr/authenticating`，仅成功时回到 `saved_session/authenticated`，非成功保持可重试 QR 状态。
- 正常超时、取消与 Ctrl+C 会在父进程存活时终结持久状态并 join child tree。SIGKILL 等父进程硬终止无法执行该清理；stale LoginSession 自动回收/parent-liveness 留到下一执行。

## 真人资格验证

| 平台 | 真人二维码登录 | 保存会话定时复用 |
| --- | --- | --- |
| `xhs` | `NOT_RUN` | `NOT_RUN` |
| `dy` | `NOT_RUN` | `NOT_RUN` |
| `ks` | `NOT_RUN` | `NOT_RUN` |
| `bili` | `NOT_RUN` | `NOT_RUN` |
| `wb` | `NOT_RUN` | `NOT_RUN` |
| `tieba` | `NOT_RUN` | `NOT_RUN` |
| `zhihu` | `NOT_RUN` | `NOT_RUN` |

离线 fake-child 证据绝不能改变此表。
