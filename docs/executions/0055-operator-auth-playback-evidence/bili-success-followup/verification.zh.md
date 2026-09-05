[English](verification.md) | **中文**

# 验证记录

基线：main 在 f9b343c 且干净，冻结计划 b018979，后续 Worker 展示补充 9602246。实际部署提交和镜像身份未独立确认。不向 Git 写入登录账户标识、凭据、完整浏览器快照或私有部署信息。

## 已执行 Python 门禁

- 子代理完整登录专项：`.venv/Scripts/python.exe -m pytest -q tests/unit/test_bilibili_login_confirmation.py tests/contract/test_mediacrawler_login.py tests/unit/test_browser_launch_diagnostics.py`，160 项通过，72.90 秒；含七平台隔离子进程生命周期、合成 profile 重开、更新后 true/false/非布尔/异常/取消及清理。此前重叠子集 46 项通过、45 项未选中、27.40 秒。
- 主代理后端专项：`.venv/Scripts/python.exe -m pytest -q tests/unit/test_login_diagnostics.py tests/unit/test_cli_login.py tests/unit/test_operation_payloads.py tests/integration/test_mediacrawler_login_application.py tests/integration/test_login_session_repository.py --junitxml=artifacts/bili-success-backend.xml`，240 项通过，1 项既有 Starlette/httpx 警告，34.52 秒。
- 主代理控制面专项：`.venv/Scripts/python.exe -m pytest -q tests/unit/test_login_preflight.py tests/unit/test_mediacrawler_login.py tests/unit/test_api_operations.py --junitxml=artifacts/bili-success-controls.xml`，45 项通过，同一既有警告，11.43 秒。复核者单独运行后端预检文件 14 项通过、4.26 秒，不叠加此重叠计数。
- src/scripts/tests 的 Ruff check/format 通过（257 文件），mypy 通过（110 源文件），compileall 通过，两个锁定上游均核验未变。本有界增量未运行全量 Python、Docker 构建、PostgreSQL 或重新打包，不作通过声明。

## Web 门禁

在后续 Worker 展示补充之前，串行 `pnpm format:check`、`pnpm test`、`pnpm check`、`pnpm build` 通过：12 文件/208 项、561 毫秒；Svelte 零错误/警告；静态构建 8.04 秒。账户 helper 专项 3 文件/78 项。独立复核发现的空响应 spinner 风险已修复并加入测试后才通过这些门禁。补充实施后的最终结果待填入下文。本轮未对本地补丁运行合成渲染浏览器，生产浏览器验证的是部署版本，而非尚未发布的 UI 修改。

## 真人结果与残余诊断

生产采集为 FAILED，不是 NOT_RUN 或 PASS：一次明确获授权作者同步，18:53:18–18:57:14，Job 为 failed_terminal 且零内容。已直接检查 Worker 完成状态及失败摘要。用户精确只读 JOIN 确认 schema_invalid Job、关联 Run 仍 running 且无错误码。订阅已暂停，未观察到待处理 Job/活动 Operation，supervisor 由用户停止。未自动重试、下载媒体或操作 Emby/Jellyfin，不能因为持久账户仍已认证便宣布保存会话复用通过。

另一个子代理合成实验使用内存 SQLite，让 handler 先关联 running Run 再等待；向 heartbeat 分别注入 RuntimeError 或带 SQLITE_BUSY 的类型化 SQLAlchemy OperationalError，均产生相同组合：failed_terminal/schema_invalid Job、running/无错误 Run、handler 被取消、零内容、账户仍已认证。这是注入失败路径证据，不是真实 SQLite 锁竞争测试，也不是生产根因证明。目前 heartbeat、错误结果与兜底路径共用 schema_invalid，需要更精确的闭集诊断后才能声明采集故障修复。

补充实施后的最终串行 Web 门禁全部通过：**13 文件/269 项，707 毫秒**，Svelte **零错误/零警告**，格式及静态构建通过（8.68 秒）。补充 helper/operation/登录诊断专项另有 122 项通过、306 毫秒；不叠加重叠计数。未增加完成 toast 机制。两个上游再次核验通过；两份计划检查点 fresh origin fetch 显示本地领先 2、落后 0。

最终文档/链接检查通过 **562 个 Markdown 文件**，差异空白检查通过。原始测试 XML 保留在被忽略的 artifacts 内。粘贴 Cookie 校验/保存、其余平台真人验证、真正有界的 B 站采集、下载和播放仍待推进。

## 发布

实现提交 **4b24d6e86794cb5e96c62cb3094bc9e82baa895a** 与两份冻结计划均已推送 origin/main。fresh fetch 核验本地/远程哈希相同、分歧 0/0、工作区干净；本发布记录属于后续纯文档提交。代理未部署补丁，也未启动由用户停止的 supervisor。三条实施线均获独立复核，有界修复内没有未解决的阻断问题，但另行记录的实际采集故障仍未解决。
