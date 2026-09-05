[English](verification.md) | **中文**

# 登录诊断验证

- 状态：本机可用门禁通过，当前合并修复尚未部署

基线为清洁 `f61a3c4`，诊断冻结计划 `488ce20`，追加运行/二维码计划 `7268352`。此前全量测试属于历史，本轮不冒称重跑完整套件。

## Python 验证与修正

最终后端命令：

```powershell
.venv/Scripts/python.exe -m pytest -q tests/unit/test_login_diagnostics.py tests/unit/test_api_operations.py tests/unit/test_api_server.py tests/unit/test_operator_auth_api.py tests/unit/test_cli_login.py tests/unit/test_operation_payloads.py tests/integration/test_operation_repository.py tests/integration/test_operation_coordinator.py tests/integration/test_operation_postgresql_races.py tests/integration/test_mediacrawler_login_application.py tests/integration/test_login_session_repository.py --junitxml=artifacts/login-diagnostics-backend-regression.xml
```

结果：**355 passed、11 skipped、一个既有 Starlette/httpx 警告，51.64s**。11 项均因缺少真实 PostgreSQL 服务跳过。首轮旧测试为 318 通过、11 跳过、1 失败，47.16s：旧 CLI 精确输出断言未包含新增 `diagnostic: null`，已更新断言，并非生产异常。投影审查补充拒绝额外 execution 类型、矛盾完成组合、非法原始 JSON、陈旧/最新身份及安全通用恢复测试。

最终合并运行命令：

```powershell
uv run --frozen --with pillow==12.3.0 pytest -q tests/unit/test_browser_launch_diagnostics.py tests/unit/test_mediacrawler_login.py tests/contract/test_upstream_browser_policy.py tests/contract/test_browser_policy_wiring.py tests/contract/test_mediacrawler_login.py tests/unit/test_login_qr_relay.py tests/contract/test_upstream_qr_relay.py tests/unit/test_mediacrawler_javascript_preflight.py tests/unit/test_mediacrawler_browser_environment.py tests/unit/test_mediacrawler_browser_preflight.py tests/unit/test_login_preflight.py tests/unit/test_login_browser_smoke_script.py --junitxml=artifacts/login-diagnostics-runtime-regression.xml
```

结果：**370 passed、无跳过，72.83s**，包含真实 Pillow 图片规范化。锁定 helper/入口测试里的平台/浏览器边界为合成，不是真实认证。此前主代理入口接线 36 项通过，生命周期/策略合计 204 项通过（23.29s），隔离登录契约 53 项通过（71.15s），独立 doctor/bridge 合计 93 通过、1 项 Windows/POSIX 跳过（82.81s）。这些重叠运行不能相加冒称全量测试数。

## Web 与静态门禁

在 `web` 顺序执行 `pnpm test`、`pnpm check`、`pnpm format:check`、`pnpm build`。最终 **11 文件/179 测试通过，493ms**；Svelte 零错误/警告，格式和生产静态构建通过（Vite 6.38s）。早期检查发现可空摘要与不完整测试夹具类型错误，均已修复。覆盖五种终态、图片失败/悬挂、旧/当前 Operation/会话竞态、延迟响应/关闭、旧诊断和固定不反射文案。本轮没有合成渲染浏览器夹具测试；生产浏览器仅只读确认旧部署失败，不是本地 Web 补丁验证。

`.venv/Scripts/python.exe -m ruff check src scripts tests`、`ruff format --check src scripts tests`（256 文件）、`mypy src/media_sync`（110 源文件）和 `compileall -q src/media_sync scripts/check_login_browser.py` 均通过。中途 helper 格式问题和新增 JS 测试的枚举身份断言已修正，首轮失败不算 PASS。

## 打包与文档快照

独立系统临时输出目录中的 `uv build --offline` 产出 128 项 wheel、888 项 sdist，包含当前实现文件。构建早于最终文档/Cookie 草案编辑，是代码打包快照，不是最终文档归档；默认包不含编译 Web，由 Docker 另行构建。没有夹带私人 Compose、实际 `.env`、凭据、profile、数据库、日志或工具/运行目录。七个似私网 IP 候选路径逐项核实为既有 CIDR/示例/测试，相对 `f61a3c4` 均未修改，历史精确 LAN 计划 blob 也一致；未使用私网地址全局豁免。

文档/上游及最终 Git 发布将在收尾记录；本地原始测试 XML 保持在忽略的 `artifacts` 内。

## 待跑门槛

独立运行/投影/Web/二维码审查未发现本轮未解决阻断问题。既有强杀可能残留 QR 临时文件的限制见[运行后续](../login-runtime-followup/verification.zh.md)。Docker 构建/当前合并镜像、真人扫码/会话复用、采集和 Emby/Jellyfin 均待验证；操作者此前 Linux 空白浏览器 PASS 与后来的 `NODE_MISSING` 是分离观察，不构成平台 PASS。Cookie 登录尚未实现，仅记录[草案](../cookie-login/plan.zh.md)。
