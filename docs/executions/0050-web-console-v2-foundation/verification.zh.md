[English](verification.md) | **中文**

# 执行 0050 验证

- 状态：本轮前端/API/资格门全绿；Windows 完整套件复现既有进程密封不稳定
- 日期：2026-09-04
- 基线：`6d68768`
- 本地原始 junit：`artifacts/pytest-windows-0050.xml`（Git 忽略；脱敏摘要如下）

## 自动门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 前端格式 | `pnpm format:check` | `PASS` |
| Svelte/TypeScript | `pnpm check` | `PASS`——0 错误、0 警告 |
| 前端单元测试 | `pnpm test` | `PASS`——2 项 |
| 静态生产包 | `pnpm build` | `PASS`——adapter-static 写入 `web/build` |
| API 套件 | `python -m pytest -q tests/unit/test_api_server.py` | `PASS`——9 项；包含显式干净 clone SPA 夹具、路由回退、immutable 缓存、安全响应头、内容与媒体库契约 |
| Checkout/许可证专项 | `python -m pytest -q tests/contract/test_mediacrawler_bridge.py -k "checkout or license"` | `PASS`——16 项，61 项取消选择 |
| Python 静态/打包门 | `ruff check`、`ruff format --check`、strict `mypy`、`compileall`、文档、上游锁、`uv build` | `PASS`——624 个文件已格式化、87 个类型化源文件、446 份 Markdown、2 个干净锁定 checkout、sdist + wheel 构建成功 |
| 打包迁移 | `uv run pytest -q tests/integration/test_packaged_migrations.py` | `PASS`——7 项 |
| Python 完整套件 | uv + ffmpeg/ffprobe 均在 `PATH` 时执行 `uv run pytest -q --junitxml=artifacts/pytest-windows-0050.xml` | 502.82 秒内 `2038 passed, 33 failed, 1 skipped`；失败在下文分类，不隐藏 |
| Docker 构建/运行 | 操作者 Linux 主机 | 本工作站对本版本 `NOT_RUN` |

最终完整套件已包含网络边界响应补全和本机完整 uv/ffmpeg/ffprobe 工具链，因此打包与生产媒体集成检查都真实执行，没有变成环境 skip。

## 浏览器与风格证据

- 内置浏览器访问 `http://127.0.0.1:8765`：九个路由均返回预期标题和有效 DOM；无框架错误层；控制台 warning/error 为 0。
- 最终诊断路由 QA 捕获并修复了一个确认状态恢复时序竞态：返回用户曾可能卡在「检查中…」而没有发起预检请求。修复后，全新内置标签页与独立 Playwright/Chrome 均显示 `runtime_unconfigured`、「本机安全」和 `127.0.0.1:8765`；请求返回 200，浏览器 warning/error 仍为 0。修复后截图为 `console-diagnostics-desktop.png`。
- 交互：设置 → 重置首次确认 → 出现 onboarding 弹窗 → 确认 → 刷新设置。刷新后弹窗数量为 0，状态显示「已确认」。
- 账户页显示两个夹具账户与扫码操作，不再出现旧的两个重复勾选。
- 既有 Playwright 截图覆盖 1440×900 桌面与 390×844 手机；最终生产构建后又以内置浏览器检查当前渲染路由。
- 直接用 `view_image` 对照 `bili-sync-reference.jpg` 与 `console-dashboard-desktop.png`，并单独检查手机图。核对清单覆盖侧栏层级、紧凑顶栏、真白配色、边框/阴影重量、表格/面板密度、图标处理、运维文案与响应式折叠。对用户要求的「类似 bili-sync」方向没有可修复的重大偏差。
- 首屏只包含 media-sync 运维标签；Bili Sync 无关的存储/CPU 图表与 Bilibili 单平台文案有意不复制。这是领域适配，不是还原缺陷。

## 完整套件如实说明

junit 摘要为 `tests=2072 failures=33 errors=0 skipped=1`。失败按文件分组为 `test_mediacrawler_bridge` 19 项、`test_mediacrawler_scheduler_handler` 10 项，login、supervision、CLI ingest 与 security matrix 各 1 项。它们属于执行 0048/0049 已记录的同一组 Windows 原生 completion-receipt/进程非确定问题（0048 曾出现 33/35 项失败，0049 后来出现一次全绿）：大多数以 `unsafe_path` 安全关闭，其余 child timing/命令竞态级联到同一集成路径。没有一项触及 0050 前端、API 投影或 LICENSE 资格改动；其专项套件全绿。Linux 阶段 B 仍是权威，且没有为强行让 Windows 变绿而削弱任何安全检查。

## 不宣称

不宣称 0050 Docker 镜像构建、容器内静态包检查、`mediacrawler doctor`、运行用户 Chromium 启动、重启/备份演练、真人账户登录、采集、CDN 下载或 Emby/Jellyfin 扫描/播放。它们仍归操作者阶段 B/0047 证据。
