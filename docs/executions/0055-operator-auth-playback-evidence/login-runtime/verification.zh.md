[English](verification.md) | **中文**

# 登录浏览器运行环境验证

- 日期：2026-09-05
- 状态：可用本地门禁通过，实现 `11dbd06` 已发布；部署/真人门槛待完成

基线检查：`git status --short` 为空，HEAD 为 `db6c3c7`，已读取诊断和交付优先级。此前证据仅诊断，不是重建镜像或真人平台验收。后续补记实际命令、失败、修正和测得结果。

## 专项检查与修正

- 环境捕获：`.venv/Scripts/python.exe -m pytest tests/unit/test_mediacrawler_browser_environment.py -q`，10 项通过，1.00 秒。七平台登录、作者规格和真实详情 spawn 均保留缓存，拒绝合成后台/代理/Python/debug/control 值；测试不启动真实爬虫子进程。
- 初次锁定启动策略 50 项通过，1.66 秒。审查指出它只执行真实 launcher 方法体、工厂为合成模型；因此补充 29 项，执行已验证锁定 factory/main 和真实登录/作者/详情接线，含数字 Bilibili aid 详情。组合 79 项通过，2.36 秒；浏览器/网络仍为 fake。
- 根代理最终专项联合命令：`.venv/Scripts/python.exe -m pytest -q tests/contract/test_upstream_browser_policy.py tests/contract/test_browser_policy_wiring.py tests/unit/test_mediacrawler_browser_environment.py tests/unit/test_mediacrawler_browser_preflight.py tests/unit/test_login_browser_smoke_script.py tests/unit/test_login_preflight.py`，134 项通过，4.96 秒。
- 现有登录/详情/会话/调度联合回归 205 项通过，184.35 秒。此前运行因夹具缺工厂/启动方法或引用已移除私有白名单而停止，不算 PASS；补齐夹具，未放宽生产 hook。
- bridge/CLI 联合回归 152 项通过，一项 Windows/POSIX 跳过，101.64 秒。首次扩大运行 12 失败、167 通过、1 跳过，98.43 秒；12 项均为过期非浏览器工厂模型，修正后成功重跑。
- 入口及仅配置联合检查 77 项通过，33.70 秒，使用 Git Bash、fake Xvfb/xdpyinfo 和真实 coreutils timeout。修正了最初夹具 PATH 缺失；真实挂起探针还发现 shell 自身的 `Killed` 提示会穿过内层重定向，已改命令组重定向。断言覆盖提前拒绝、不迁移、清理；不是真实 Linux X server 测试。

## 本地真实空白浏览器冒烟

项目 venv 没有 Playwright。初次隔离 `uv run --no-project --with playwright==1.62.0` 查找确认已有 bundled Chromium，但产生 pending-connection 清理警告；那只是路径发现探针，不算启动成功证据。随后使用项目 Python 3.11.8 和缓存包创建 Git 忽略的隔离运行时：

```powershell
uv venv --python .venv/Scripts/python.exe .media-sync/login-browser-probe-venv
uv pip install --offline --python .media-sync/login-browser-probe-venv/Scripts/python.exe playwright==1.62.0
.venv/Scripts/python.exe scripts/check_login_browser.py --python .media-sync/login-browser-probe-venv/Scripts/python.exe
```

真正的新监督有头持久路径退出码为 0，且仅输出：

```json
{"ok": true, "browser": "bundled-chromium", "mode": "headed-persistent", "version": "151.0.7922.34", "live_qualification": "NOT_RUN"}
```

使用临时 profile，不含平台网址/账户。这证明 Playwright 1.62.0 的 Windows 启动与普通收尾，不是 Linux 镜像或平台认证通过。探针运行时和原始测试产物保持 Git 忽略，记录不保留私人 profile 或凭据。

## 质量与打包

- `.venv/Scripts/python.exe -m ruff check src scripts tests` 通过；整合中的两处 import/空行格式问题已修正。
- `.venv/Scripts/python.exe -m ruff format --check src scripts tests` 通过，250 个文件。
- `.venv/Scripts/python.exe -m mypy src/media_sync` 通过，109 个源码文件。
- `.venv/Scripts/python.exe -m compileall -q src/media_sync scripts/check_login_browser.py` 通过。
- `.venv/Scripts/python.exe scripts/check_docs.py` 通过，528 个 Markdown 文件；`scripts/check_upstreams.py` 两个锁定 checkout 通过。
- 最终 `uv build --offline` 成功：wheel 127 个成员，sdist 862 个成员。wheel 包含两个新运行模块，sdist 包含冒烟脚本和接线测试。精确路径扫描确认不含个人 Compose、`.env`、运行/profile/工具历史目录及原始产物，已跟踪 `artifacts/README.md` 除外。
- 初次扫描模式过宽，误拒绝 `.env.example` 和 `artifacts/README.md`；后续内容扫描还找到未修改的 2026-09-04 安全部署计划中既有局域网示例。保留历史已跟踪示例并明确记账，不冒称所有 IP 均不存在。最终按该精确历史文件例外扫描通过，未发现新增部署 HTTPS 入口或工作站用户路径标记；该历史文件相对冻结基线未改变。
- Web 源码未改变，之前 114 项 Web 测试/构建为历史结果，不冒称本轮重跑。

## 全量回归与发布

根代理全量命令 `.venv/Scripts/python.exe -m pytest -q --junitxml=artifacts/login-runtime-python-full.xml` 已结束：**3264 项通过、22 项跳过、1 项既有警告，679.04 秒（11:19）**。启动时额外 29 项接线测试尚未创建，这些测试在最终 134 项专项联合中单独通过。收集之后没有修改源码行为，后续整合格式与文档修改不构成新一次全量声明。跳过包括 Windows 下 3 项 POSIX 专用检查、未配置真实服务器的 19 项 PostgreSQL 竞态；警告为既有 Starlette/httpx 弃用提示，不把跳过门槛算通过。

计划提交：`204655d`。实现提交：`11dbd06e9fd1e6a3daa8277c7078e9901dff65fb`。`git push origin main` 已将远端 main 从 `e3fe9db` 推进到 `11dbd06`，包含诊断和冻结计划提交。随后 `git fetch origin` 确认 HEAD/origin-main SHA 相同、差异 `0 0`、`git status --short` 为空。本次发布记账属于后续纯文档提交，未自动部署。

## 操作者交接（尚未在服务器执行）

先备份状态，保留已可用的个人 Compose、精确 HTTPS Origin、凭据权限和命名卷。不要用仓库回环示例覆盖现有部署，不运行 `down -v`。在原部署目录依次执行：

```bash
git pull --ff-only
docker-compose build media-sync
docker-compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync serve --check-config
docker-compose up -d --no-deps --force-recreate media-sync
docker-compose exec -T media-sync /app/.venv/bin/python /app/scripts/check_login_browser.py --python /opt/mediacrawler-venv/bin/python
```

每步成功才运行下一步。锁没有变化；仅当预取目录缺失或后续版本改变 lock 时重跑既有上游预取脚本。如果启用了 supervisor profile，也用相同新镜像重建。只反馈固定预检/冒烟结果，不发配置、凭据文件或平台原始日志。之后进入账户页，仅预检一个账户，由操作者扫码；记录真实结果后再尝试其他平台。

当前 Linux 镜像/UID、X11 连接、重启/恢复、二维码显示/扫码、会话复用、订阅/采集/下载和 Emby/Jellyfin 播放仍待验证，不创建真人 PASS。预检覆盖普通成功/失败/超时/取消收尾，不对 POSIX 父进程被强杀承诺完整 login runner 的父死亡保证。预检后运行错误分类和 P1 证据 UI 保持后续待办。

## 后续操作者提供的 Linux 冒烟（2026-09-05）

交接后，操作者提供了仅配置预检、服务重建和容器内空白浏览器检查的成功输出：`configuration: valid`，随后为 `ok: true`、`browser: bundled-chromium`、`mode: headed-persistent`、版本 `151.0.7922.34` 和 `live_qualification: NOT_RUN`。这是操作者提供的真实 Linux 容器空白浏览器启动证据，不是另一轮本地 Windows 测试；前文这一特定服务器冒烟尚未执行的状态由本次结果更新。

粘贴输出没有标识精确 Git SHA/镜像摘要，代理也未独立重跑。完整当前镜像资格、启动/重启/恢复、二维码显示/扫码、会话复用、采集和 Emby/Jellyfin 仍开放。已请操作者刷新账户并先手动重试一个 B 站账户，再推进其他平台。没有自动启动平台登录，也不记录平台 PASS。
