[English](verification.md) | **中文**

# 安全后台验证记录

- 日期：2026-09-05
- 状态：本地源码与浏览器组合门禁通过

## 基线与已执行检查

已发布基线：`2e1949fc85eaa83973dc54c2c7f13f3c4334817e`，该边界新 fetch 分歧 `0 0`、工作区干净。八份冻结计划先提交为 `714c849`。此前 Python 2999 / Web 69 / 文档 508 / wheel 125 / sdist 824 是历史，不是本增量结果。

| 检查 | 命令或过程 | 实际结果 |
| --- | --- | --- |
| 预检/CLI | `uv run --frozen pytest -q tests/unit/test_serve_check_config.py tests/unit/test_container_entrypoint.py tests/unit/test_operator_auth_cli.py` | 76 通过，23.53s；此前更大选择集 202 通过、一个警告，26.03s |
| 最终 shell 细化 | `uv run --frozen pytest -q tests/unit/test_container_entrypoint.py` | 23 通过，6.37s；真实 shell/CLI 覆盖带前缀 check-only/无效 serve 对新旧数据库 |
| 后台入口/认证/API | `uv run --frozen pytest -q tests/unit/test_operator_console_entry.py tests/unit/test_operator_auth.py tests/unit/test_operator_auth_api.py tests/unit/test_api_server.py` | 132 通过、一个警告，11.57s |
| Python 全量 | `uv run --frozen pytest -q` | 3155 通过，22 跳过，一个既有警告，670.16s（0:11:10） |
| 最终夹具回归 | `uv run --frozen pytest -q tests/unit/test_console_smoke_fixture.py` | 4 通过，1.76s，无跳过；在全量后运行，含新增两项不可变预览用例；生产 Python 未改 |
| 最终 Web | 在 `web/` 串行 `pnpm format:check`、`pnpm test`、`pnpm check`、`pnpm build` | 9 文件 / 114 测试；格式通过，类型 0 错误 / 0 警告，静态构建通过；最新 auth/client 定向 44 通过 |
| Python 静态 | `uv run --frozen ruff check .`；`uv run --frozen ruff format --check .`；`uv run --frozen mypy src/media_sync`；`uv run --frozen python -m compileall -q src tests` | 通过；格式 758 文件，严格 mypy 107 源文件；最终夹具另行 Ruff/format 通过 |
| 上游 | `uv run --frozen python scripts/check_upstreams.py` | 两个锁定 checkout 验证通过 |
| Shell 语法 | 经 Git Bash 执行 `sh -n docker/entrypoint.sh` | 通过；只证明 shell 分发/顺序，不是 Linux 镜像资格 |

警告为既有 Starlette/httpx TestClient 弃用提示。22 跳过为三项 Windows/POSIX 差异、11 项 operation PostgreSQL、八项 playback-evidence PostgreSQL 竞态。之后四项夹具检查独立记录，未执行所谓全量 3157 通过。

## 真实后端 + 已构建浏览器

构建 Web 后运行 `uv run --frozen python tests/unit/_console_smoke_fixture.py --root <空绝对临时目录> --video`，使用常规受认证 CLI 启动。所有 MEDIA_SYNC 输入隔离到夹具，显式指定夹具 SQLite URL、一次性后台凭据和 600 秒 TTL，使用回环端口 8765/8766。无认证绕过、真实平台账户、外部媒体；本记录不保存凭据、Cookie、CSRF、原始二维码及夹具路径。

| 检查 | 实际观察与边界 |
| --- | --- |
| 匿名入口 | `/accounts?ignored=fixture` 跳转 `/?return_to=%2Faccounts`，丢弃任意查询，只挂载登录；新 Origin 的 `/assets` 同样到达登录 |
| 登录/CSRF | 一次性后台登录后 session 挂载私有页；真实账户表单创建“Browser CSRF fixture”并显示两个账户，没有授予平台认证 |
| 刷新/目录 | 已认证刷新保持访问；异步认证挂载后资产/内容页各加载两条合成记录 |
| 精确登录图片 | 合成 LoginSession 图片通过同源 Cookie 加载为 160 × 90；不是可扫描平台二维码，不证明真实轮询/扫码登录 |
| 归档媒体 | 图片解码 160 × 90；MP4 加载解码 readyState 4、error null、160 × 90、时长 2 秒，目视检查画面；未启动播放，不是真实平台/Emby/Jellyfin 播放证据 |
| SSE | Jobs 显示连接、游标 0；无订阅本地 tick 返回零任务，未启动平台任务 |
| 自然过期 | 较早 600 秒会话退回仅登录组件树，显示明确过期提示 |
| 退出/其他标签页 | 确认退出卸载私有 UI，另一 Jobs 标签页在会话失效后也返回登录 |
| 首次引导 | 新 Origin 仅在登录后提示；仅浏览不接受许可证，另一同源标签页再次提示，证明没有持久接受 |

这些是合成数据应用接线检查，不是七平台资格。迟到响应、损坏/卡住的 401 正文、禁止重放写操作、退出不确定、QR/SSE 取消竞态由状态机/client 测试覆盖，并非都在浏览器复现。

## 尝试与审查发现

- 首次 Web 检查发现七个 mock 签名错误，最终 0/0 前修正。浏览器发现 Jobs 文案不更新、资产/内容未首次加载；显式响应式依赖与挂载/导航守卫修复，新增回归。
- 审查发现 Click 的 `-- serve` 能绕过 shell 预检；精确前缀规范化及真实 shell→CLI 回归证明无效配置不迁移新旧数据库。
- 夹具审查发现环境 `MEDIA_SYNC_DATABASE_URL` 覆盖预期隔离；显式数据库与外部 sentinel 回归修复；原手动夹具当时无环境数据库 URL。最初导入布局/格式问题已修正。
- 一次修复前全量约 2% 主动中止，不计通过；完成的 3155 全量在入口和数据库隔离修复之后。
- 最初视频直接导航被浏览器阻止，随后图片/视频内联暴露可写夹具被既有不可变归档门禁拒绝；仅将生成夹具 blob 设只读后，真实 ArchivePreviewService 回归和最终浏览器解码通过，生产安全未改。
- 第二本地服务曾误用不支持的 `python -m media_sync`，退出且未启动；常规 console 入口成功。
- 独立前端审查发现当前代次 401 依赖正文解析；改为立即撤销权限、不阻塞取消正文，损坏/卡住正文回归通过，同时旧代次不能锁定新登录。已审认证通道未发现其他可执行 P0/P1/P2。

## 外部排除项与发布

Docker CLI 不可用；`MEDIA_SYNC_TEST_POSTGRESQL_URL` 未设置。当前 Docker/Compose、实际 Linux UID/秘密权限、新装/升级/重启/恢复、真实 PostgreSQL 均为 NOT_RUN。未执行真实平台/CDN/媒体服务器扫描/播放，资格行保持 NOT_RUN。本地结果不是 GitHub Actions 证据。

最终 `uv run --frozen python scripts/check_docs.py` 通过 516 份 Markdown；`git diff --check` 通过，父级/子级所有冻结 goal/plan 差异为空。新系统临时目录运行 `uv build --out-dir <绝对临时目录>` 通过：wheel 125 条目、sdist 842 条目；预期包中均含必要生产文件、容器入口、新 Web 源码和夹具测试。路径/内容扫描未发现私有/运行数据、实际 .env/数据库/私钥、编译构建产物、工作站路径或临时口令。首次检查误纳入 uv 生成的 .gitignore，限定 wheel/tar.gz 后同一批包检查通过，未重新构建。默认 wheel/sdist 不含编译后 Web bundle；源码用户需构建，Docker 使用独立 Web 构建阶段。

本次创建的四个浏览器标签页已关闭。收尾时两个测试服务进程句柄已不存在，新监听检查确认回环端口 8765、8766 均无监听，未重启服务。首次远端核对遇到 TLS unexpected-EOF；使用 `git -c http.version=HTTP/1.1 fetch --prune origin` 保持正常 TLS 校验重试成功，未强制推送或弱化 TLS。

包含本记录的实现提交标识源码；显式暂存已审路径并排除本地状态，将计划/实现一同推送，核对新远端分歧和干净工作区。不代表父目标或总体目标完成。
