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
| 运行时启动器变更范围 | bridge/manifest、登录/详情构造器、调度 handler、pipeline runtime 与 CLI/API 专项套件 | `PASS`——`48 passed, 2 skipped` 外加 `311 passed`；两个 skip 都是 Windows 上无法执行的 POSIX 符号链接回归 |
| 后续 Python 静态门 | `ruff check .`、`ruff format --check .`、strict `mypy` | `PASS`——624 个文件已格式化、87 个类型化源文件 |
| Docker 构建/运行 | 操作者 Linux 主机，镜像来自 `4c6d0bf` | `PARTIAL`——构建/启动和直接 Chromium 启动通过；应用 doctor 暴露下述运行时启动器缺陷 |

最终完整套件已包含网络边界响应补全和本机完整 uv/ffmpeg/ffprobe 工具链，因此打包与生产媒体集成检查都真实执行，没有变成环境 skip。

## 操作者 Linux 证据与启动器修复

- 首个真实 Console v2 镜像构建成功，`docker compose up -d` 启动成功。
- `/opt/BUILD-MANIFEST.txt` 报告 Chromium `151.0.7922.34`、Node `v24.20.0`、pnpm `11.19.0` 与前端锁摘要 `dc9a47134060f185a3942bac5262b0ca55e0457a4dcddade81803e069b9bf3a0`。直接通过 `/opt/mediacrawler-venv/bin/python` 启动 Playwright Chromium 返回相同版本。
- 应用 doctor 在上游 SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` 下通过确认、锁文件、checkout 路径、仓库根、必需文件、规范许可证摘要、锁定提交、tracked blob 与干净工作树，随后失败于 `runtime_invalid / runtime_imports_missing`；真人资格仍为 `NOT_RUN`。
- 根因：应用把正常的 POSIX venv 符号链接 `/opt/mediacrawler-venv/bin/python` 解析为基础解释器，绕过了 venv 的 site-packages。修复会在 probe/manifest/runner 每个边界保留末级 launcher 符号链接，同时仍规范化其父目录。一个 POSIX 专属回归证明 import probe、browser probe、命令与 manifest 往返身份，另一个回归覆盖调度 handler。
- Dockerfile 现在会在构建期以非特权 `mediasync` 用户执行同一个 doctor。修复后镜像尚未在 Linux 重建，因此暂不宣称 doctor/Chromium 深度预检全绿。

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

暂不宣称修复版启动器镜像、容器内 doctor/深度预检全绿、重启/备份演练、真人账户登录、采集、CDN 下载或 Emby/Jellyfin 扫描/播放。首个镜像构建/启动和直接 Chromium 启动只按上面的部分操作者证据认领；修复版无缓存重建通过前，阶段 B 仍阻塞。
