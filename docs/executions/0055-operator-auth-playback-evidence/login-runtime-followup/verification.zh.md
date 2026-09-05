[English](verification.md) | **中文**

# 登录集成后续验证

- 状态：本机可用门禁通过，新 Docker 镜像及真人二维码 NOT_RUN

代码前证据：已读锁定源码及 Docker 阶段；操作者提供 Linux 空白启动成功，浏览器只读直接观察到平台新失败。尚无精确部署 SHA/镜像摘要及实际失败异常，不冒称根因确定或平台 PASS。执行后在此记录命令/结果/修正。

## 实现与证据

操作者随后在运行容器执行不读凭据的 `command -v node` 检查，提供 `NODE_MISSING`。公开精确 PyExecJS 1.5.1 源码确认 `compile()` 会立即选择运行时；无注册运行时的隔离实验在不执行 JS、不启动浏览器的情况下抛 `RuntimeUnavailableError`。这些证据支持缺少运行依赖的失败路径，但并未捕获历史服务器异常本身。

最终 Docker 阶段现安装 `nodejs`、记录版本并保留非 root doctor 构建门禁。隔离 Python doctor 执行固定 `1 + 1` JS 函数，缺少/导入/编译/调用/错误结果会安全返回 `runtime_javascript_unavailable`；保留原有 20 秒超时、隔离解释器、排除凭据环境及输出抑制。不导入上游、不访问平台/profile。

二维码转发现接收有界规范 base64 及明确 PNG/JPEG/WebP base64 data URI，加载前校验实际格式、单边最多 4096、总计 4 Mi 像素与单帧。惰性上游 Pillow 将字符串输入转换为不含原元数据的 PNG，输出最多 2 MiB，编码输入同样最多 2 MiB；既有有界字节输入不变。私有排他临时文件、原子替换及正常失败清理避免发布半张二维码，不新增 URL 抓取、原生查看器或原始日志。

## 验证结果与修正

- 首次 `uv run --offline --no-project --with pyexecjs==1.5.1 ...` 因精确包不在缓存而失败。随后从官方 PyPI 获取成功，未改项目依赖，再离线完成无运行时实验。真实本地 `execjs.compile('function media_sync_probe() { return 1 + 1; }').call('media_sync_probe')` 返回 2（`javascript_probe_ok: True`）。这是本地 JS 证据，不是 Linux 镜像证据。
- `.venv/Scripts/python.exe -m pytest tests/unit/test_mediacrawler_javascript_preflight.py tests/unit/test_login_preflight.py tests/contract/test_mediacrawler_bridge.py -q`：**93 通过、1 项 POSIX 符号链接跳过，82.81s**。此前 16 项中 15 通过、1 个错误枚举身份断言失败，已改为值比较后重跑；Docker 断言是静态接线，不是构建。
- 默认环境 QR 专项 **60 通过、7 跳过**（Pillow 属于上游依赖，不是应用开发依赖）；`uv run --frozen --with pillow==12.3.0 pytest -q -x tests/unit/test_login_qr_relay.py tests/contract/test_upstream_qr_relay.py`：**67 通过，2.15s**，包含真实 PNG/JPEG/WebP 转换。已校验锁定 inline/remote/canvas helper 代码在假页面/HTTP 边界执行，并核查七平台调用点，不使用真人二维码/账户。
- 最终带真实 Pillow 的运行合计 **370 通过、无跳过，72.83s**；相关后端 **355 通过、11 项 PostgreSQL 跳过、一个既有警告，51.64s**；Web **179 通过**且格式/检查/构建通过。完整命令、静态/打包快照及首轮失败见[诊断验证](../login-diagnostics/verification.zh.md)。本有界增量未重跑 Python 全量套件。
- 独立 Docker/doctor 与二维码审查未发现新增阻断问题。普通写入/替换错误会清除临时文件；但进程被强杀仍可能在私有账户根目录留下 `.login-qr.png.*.tmp`，父清理当前只删除最终 QR 与 job 树，不扫描这些临时残留。这是既有强杀限制，不承诺完全清理。

## 操作者交接与待办

保留已可用的私人 Compose、精确 Origin、命名数据卷和凭据权限，先备份状态。GitHub 发布后依次执行 `git pull --ff-only`、`docker-compose build media-sync`、既有仅配置检查和 `docker-compose up -d --no-deps --force-recreate media-sync`，任一步失败即停。最终构建现在要求 JS 可执行，仅重启旧镜像不够；已启用的 supervisor 也从同一新镜像重建。不执行 `down -v`，不覆盖部署配置。

刷新账户页、预检一个账户，再由操作者启动并扫码；记录实际结果后再扩大平台。精确部署 SHA/镜像摘要、新镜像构建/扫码/会话复用、采集及 Emby/Jellyfin 仍待验证。粘贴 Cookie 登录已有目标与[草案](../cookie-login/plan.zh.md)，本增量没有实现。
