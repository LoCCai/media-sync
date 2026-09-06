[English](verification.md) | [**中文**](verification.zh.md)

# 验证记录

状态：提交 `ea64938` 的专项离线证据、Python 完整 unit 套件、media-sync Web 完整套件 782 项、锁定上游真实 React 源码临时构建及加固后生产依赖审计均通过。完整 Docker 镜像／运行时及在线部署为 `NOT_RUN`；全依赖审计仍保留 8 个仅构建期开发依赖发现，因此 0072 尚未取得部署资格。

## 状态矩阵

| 门禁 | 状态 | 精确证据／边界 |
| --- | --- | --- |
| Python 集成／鉴权专项 | `PASS` | 最终 7 文件联合结果为 `142 passed, 1 warning in 29.19s`；其不重叠分量为 13 项 WebUI manager 文件和 129 项许可证／鉴权／配置选择。warning 是既有 Starlette `TestClient`／httpx 弃用提示。覆盖默认关闭许可证门、环境 token 精确解析、固定解释器／checkout 与确定性环境检查、同源／CORP 与静默轮询、受管根／进程树／关闭、有界脱敏日志、64-KiB 私密 Cookie 交接与清理、浏览器 child 环境／policy、二维码 relay、固定不可用行为、挂载 HTTP 鉴权／CSRF、精确 WebSocket Host／Origin／session 规则及登录返回。 |
| media-sync Web 专项 | `PASS` | Vitest 1 个文件、`26 passed`，包括精确 `/crawler/` 登录返回路径。这不是完整 Web 套件，也没有执行上游 React 应用。 |
| media-sync Web 检查与生产构建 | `PASS` | `svelte-check` 为 0 error、0 warning；media-sync Vite 生产构建完成；相关文件 Prettier 检查通过。 |
| Python 专项静态检查 | `PASS` | Ruff 报告 `All checks passed!`；Ruff format 报告 13 个文件已格式化；严格 mypy 对 6 个源码文件报告无问题。 |
| 文档链接 | `PASS` | `scripts/check_docs.py` 报告 `Documentation links OK (730 Markdown files checked).` |
| 工作树空白检查 | `PASS` | 文档变更完成后 `git diff --check` 以 0 退出且无输出。 |
| 完整 Python 套件 | `PASS` | `tests/unit -q --tb=short` 以 `4633 passed, 3 skipped, 1 warning in 547.80s` 完成（墙钟 552.725 秒）。3 项跳过均为 Windows／POSIX 文件系统或 DACL 差异；warning 是既有 Starlette `TestClient`／httpx 弃用提示。执行开始时相同实现位于 `dcd3881` 工作树，结束时该实现已不改内容地提交为 `ea64938`；提交外只剩文档。 |
| 完整 Web 测试套件 | `PASS` | `pnpm --dir web test` 在当前 0072 工作树上 782 项全部通过。上述 26 项仍是登录返回路径专项选择。 |
| 补丁后的锁定上游 React 构建 | `PASS` | 最新临时副本依次执行安全补丁、复制 lock 重生成、干净安装、生产审计、集成补丁及 TypeScript／Vite 构建，转换 1,836 个 module。生成 index 含 `/crawler/assets/` 与 `/crawler/static/vite.svg`；bundle 含 `/crawler/api`、操作者 CSRF、`/crawler/api/ws/logs` 及二维码 endpoint。 |
| 当前 Docker 镜像／运行时 | `NOT_RUN` | Dockerfile 阶段已实现，但本工作站没有 Docker，未构建或运行完整镜像。独立 React 构建不属于 Docker 证据。 |
| 当前在线部署 | `NOT_RUN` | 未检查或改变任何运行中部署，因此镜像身份、`/crawler/` 可达性、持久性、浏览器行为及运行时归属均未验证。 |
| 加固后生产依赖审计 | `PASS` | 构建副本安全补丁选择 `axios@1.18.0`、`follow-redirects@1.16.0` 与 `form-data@4.0.6`；复制 lock 重生成并执行 `npm ci` 后，`npm audit --omit=dev --audit-level=low` 报告 `found 0 vulnerabilities`。版本化上游 checkout／lock 保持原样。 |
| 全构建依赖审计 | `FAIL`／仅开发依赖残余 | 加固副本的全依赖审计报告 8 个包条目：6 high、2 low、0 moderate、0 critical，分别为 `@babel/core`、`browserslist`、`nanoid`、`picomatch`、`postcss`、`postcss-selector-parser`、`rollup`、`vite`。它们全部是开发／构建依赖，对应 package 不会复制进最终运行镜像；但编译期间仍有供应链暴露，因此不把非零结果描述成全审计 PASS。 |
| 未加固锁定上游审计基线 | 历史发现 | 构建副本安全补丁前，在未修改 checkout 上运行 `npm audit --json` 报告 11 个包条目：8 high、1 moderate、2 low、0 critical。该发现继续保留，不会静默改写；只有生成的生产 bundle 通过上述 3 个精确构建副本 override 消除了生产链条目。 |
| 合成二维码 relay 合约 | Python 专项内 `PASS` | 合成栅格字节证明有界规范化、child 运行期间受管文件可见、清理、响应大小／年龄检查、`no-store`、`nosniff` 与摘要 header；这只属于实现证据。 |
| 真人浏览器扫码／平台登录 | `NOT_RUN` | 没有扫描二维码，也没有尝试真实平台登录或保存会话复用；合成测试不能赋予扫码／登录就绪资格。 |
| 控制台输出 → Subscription／历史／定时增量／摄取／NFO | 本批 `NOT_IMPLEMENTED` | 根与职责边界已经冻结，但未连接自动完成态摄取或持久调度／发布链。 |
| 真人七平台采集／下载／CDN 资格 | `NOT_RUN` | 七个平台均未执行真实账户、作者、内容、媒体字节、CDN 行为、历史完整性、增量性或下载检查。 |
| 真实 Emby/Jellyfin 服务器扫描／播放 | `NOT_RUN`／可选 | 没有要求或使用服务器。media-sync 继续负责本地文件夹／NFO，但本批没有把控制台摄取接到该边界。 |

## 已执行命令

Python 专项：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/unit/test_mediacrawler_webui.py `
  tests/unit/test_api_mediacrawler_webui.py `
  tests/unit/test_mediacrawler_webui_license_gate.py `
  tests/unit/test_operator_auth_websocket.py `
  tests/unit/test_operator_auth_api.py `
  tests/unit/test_serve_check_config.py `
  tests/unit/test_config.py -q
```

Python 完整 unit 套件：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q --tb=short
```

Web 完整／专项及 media-sync Web 静态／构建检查：

```powershell
pnpm --dir web test
pnpm --dir web exec vitest run src/lib/stores/operator-auth.test.ts
pnpm --dir web run check
pnpm --dir web run build
pnpm --dir web exec prettier --check src/lib/components/AppShell.svelte src/lib/stores/operator-auth.ts src/lib/stores/operator-auth.test.ts
```

Python 专项静态检查（两个 Ruff 命令都使用下列相同的 13 个源码／测试路径）：

```powershell
.\.venv\Scripts\python.exe -m ruff check src/media_sync/config.py src/media_sync/interfaces/api.py src/media_sync/security/operator_auth.py src/media_sync/integrations/mediacrawler/license_gate.py src/media_sync/integrations/mediacrawler/webui.py src/media_sync/integrations/mediacrawler/webui_child.py tests/unit/test_operator_auth_api.py tests/unit/test_operator_auth_websocket.py tests/unit/test_api_mediacrawler_webui.py tests/unit/test_mediacrawler_webui.py tests/unit/test_mediacrawler_webui_license_gate.py tests/unit/test_serve_check_config.py tests/unit/test_config.py
.\.venv\Scripts\python.exe -m ruff format --check src/media_sync/config.py src/media_sync/interfaces/api.py src/media_sync/security/operator_auth.py src/media_sync/integrations/mediacrawler/license_gate.py src/media_sync/integrations/mediacrawler/webui.py src/media_sync/integrations/mediacrawler/webui_child.py tests/unit/test_operator_auth_api.py tests/unit/test_operator_auth_websocket.py tests/unit/test_api_mediacrawler_webui.py tests/unit/test_mediacrawler_webui.py tests/unit/test_mediacrawler_webui_license_gate.py tests/unit/test_serve_check_config.py tests/unit/test_config.py
.\.venv\Scripts\python.exe -m mypy --strict src/media_sync/config.py src/media_sync/integrations/mediacrawler/license_gate.py src/media_sync/integrations/mediacrawler/webui.py src/media_sync/integrations/mediacrawler/webui_child.py src/media_sync/interfaces/api.py src/media_sync/security/operator_auth.py
```

锁定上游 React 构建（在全新复制的临时 WebUI 根执行；两个 patch script 也复制到该目录，生成结果写入相邻 `artifacts/api/webui`，不写锁定 checkout）：

```powershell
node mediacrawler-webui-security-patch.mjs
npm install --package-lock-only --ignore-scripts
npm ci
npm audit --omit=dev --audit-level=low
node mediacrawler-webui-patch.mjs
npm run build -- --base=/crawler/
```

全依赖审计、文档及最终空白检查：

```powershell
Push-Location .mediacrawler-local/webui
npm audit --json
Pop-Location
# 在加固后临时副本中运行同一命令，报告剩余 8 个开发／构建条目。
.\.venv\Scripts\python.exe scripts/check_docs.py
git diff --check
```

生产审计通过；全审计的非零开发依赖结果及原始 11 条发现都继续保留，不会被归一化消失。没有声称运行任何 Docker、部署、平台、CDN 或媒体服务器命令。
