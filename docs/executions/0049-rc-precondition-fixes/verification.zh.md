[English](verification.md) | **中文**

# 执行 0049 验证

- 状态：离线修复在本工作站通过全部门禁；容器运行时验证仍归阶段 B
- 日期：2026-09-03
- 前驱：执行 0048 收尾 `0eb3f895b02137cbfe231c705ba34aa1ce86a9f4`
- 计划提交：`dcba270`

## 基线（任何 0049 变更之前）

| 检查 | 结果 |
| --- | --- |
| 拉取后静态冒烟（ruff、文档链接、upstream、新单元文件） | `PASS`（拉取时记录） |
| 0048 的编写工作站完整套件数字 | `33 failed, 2031 passed, 1 skipped`；复跑 `35 failed`（抖动的子进程密封测试） |

## 实现证据

| 范围 | 结果 |
| --- | --- |
| 容器 checkout 路径 | `PASS`（静态）——checkout 现克隆到 `/app/.upstream/MediaCrawler` 且保留 `.git`，与校验器的锁相对解析和 git 身份要求一致 |
| Playwright 共享路径 | `PASS`（静态）——安装前即设 `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`，运行用户拥有缓存，构建清单记录以 `mediasync` 真实 `chromium.launch()`；容器内启动本身归阶段 B |
| 操作语义 | `PASS`——受阻下载以 `failed`/`locator_refresh_unsupported` 收尾；手工标记 verified 但无归档以 `failed`/`asset_download_state_invalid` 收尾（无假绿）；完成型执行器以应用捕获设置驱动 `succeeded` |
| 设置捕获 | `PASS`——全部后台线程与登录状态路径使用 `create_api_app()` 设置；生命周期测试断言线程的 state 目录等于工厂的 |
| 文档完整性 | `PASS`——两份日志文档各 156 行、单 H1、单切换器；强化后的检查器（重复 H1/H2、游离切换器、中英标题结构、排除代码块）在全部 424 文件上通过 |
| 回执原因码 | `PASS`——完成失败现在在脱敏消息中携带固定枚举后缀（既有完成失败套件保持绿色佐证） |
| 可复现性指引 | `PASS`——compose 透传 `BASE_IMAGE`；部署文档记录 digest 钉版构建与 doctor/Chromium 预检门 |

## 测试与质量门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| API 服务套件 | `uv run pytest -q tests/unit/test_api_server.py` | `PASS — 7 passed` |
| 0048 抖动文件稳定性复跑 | `uv run pytest -q tests/integration/test_mediacrawler_security_matrix.py tests/contract/test_mediacrawler_supervision.py` | `PASS — 28 passed, 1 skipped in 41.07s` |
| 完整套件（junit 工件） | `uv run pytest -q --junitxml=artifacts/pytest-windows-0049.xml` | `PASS — 2066 passed, 1 skipped in 472.81s`；工件摘要 `tests=2067 failures=0 errors=0 skipped=1` |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | `PASS — all checks; 604 files formatted` |
| Strict mypy | `uv run mypy --strict src` | `PASS — no issues in 87 source files` |
| Compileall 与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | `PASS — 编译通过；构建 wheel 与源码分发包` |
| 文档与上游锁定 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | `PASS — 424 Markdown 文件；2 个锁定干净 checkout` |
| Git/上游审计 | 显式 status 与跟踪路径扫描 | `PASS — 仅预期变更；跟踪 runtime/upstream/dist 0；两个上游 dirty 计数 0` |

## 工作站失败清单诚实说明

0048 在本站记录 `33 failed, 2031 passed`、复跑 `35 failed`。本执行的完整运行 **2066/2067 全过、零失败**（+2 为新增生命周期测试），且对先前失败文件的定向复跑亦通过——证实分歧在本编写工作站**非确定**（与评审的 AV/文件系统竞争假设一致），既非确定性产品缺陷，也不是本执行「修复」了它们。绿色 junit 工件（`artifacts/pytest-windows-0049.xml`）记录的是一次绿色运行而非失败清单；逐测试的 Linux diff 仍是阶段 B 的权威，状态页在抖动裁定前把 Windows 原生运行保持为 Experimental。

## 不宣称

不宣称任何 Docker 构建/运行、容器内 doctor 预检、以运行用户启动 Chromium、重启持久性或备份恢复演练（本站无 Docker；全部归阶段 B）。不宣称任何真人验收行。
