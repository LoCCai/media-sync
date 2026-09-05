[English](deployment.md) | **中文**

# Docker 部署与后端鉴权检查点

本指南使用内含锁定 MediaCrawler 运行时的自托管容器部署 media-sync。它由执行 0040/0041 首次建立、由 0050 更新，要求 Linux 主机与 Docker Compose v2。当前执行 0055 检查点已经实现后端单操作者鉴权边界，但 Console v2 与 `/legacy` 尚未接入登录、内存 CSRF、退出或过期流程。容器可以启动，也可以验证公开 health/readiness 探针；目前不得宣称 Web 管理、扫码登录或媒体服务器控制流程可用。

## 1. 构建

```bash
git clone <你的仓库> media-sync && cd media-sync
sh scripts/fetch_mediacrawler.sh   # 必选：宿主机预取锁定上游
cp docker-compose.example.yml docker-compose.yml   # 本地副本已被 git 忽略
export MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE=/绝对/私有路径/operator-credential.txt
docker compose build          # 如需改端口/路径，先编辑你的本地副本
```

运行任何 Compose 命令前，先在仓库外创建上述 UTF-8 文件并设为 `0600`。文件只包含专用操作者凭据（末尾 CR/LF 会被剥离）：16–1024 个 UTF-8 字节、不含控制字符，并至少含四种不同字符。不得复用平台 Cookie 或媒体服务器 key。`MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE` 必须是绝对路径，并在每次重启时持续可用。

示例 Compose 会把宿主机文件挂载成 Docker secret `/run/secrets/operator_credential`，设置 `MEDIA_SYNC_SECRET_FILE_DIR=/run/secrets`，并只向应用提供类型化引用 `file:operator_credential`；同时设置精确浏览器 origin `http://127.0.0.1:8632`。凭据值不会提交到 Git、复制进镜像或写入 SQLite。

构建现在会在独立 Node/pnpm 阶段编译 SvelteKit 5 控制台，只把静态产物复制进 Python 应用；最终运行镜像不包含 Node.js、pnpm 或 `node_modules`。构建清单会记录其构建期版本与前端锁文件摘要。

第 0 步（`fetch_mediacrawler.sh`）按 `upstreams.lock.json` 的精确提交把 MediaCrawler 克隆到 git 忽略的 `.mediacrawler-local/`；构建会 COPY 并校验其 SHA，因此**构建容器自身不再访问 github.com**（容器网络到不了 GitHub 的大陆主机，改在宿主机这一步设置 `BUILD_HTTPS_PROXY=...`）。`git pull` 变更锁定提交后需重跑该脚本。

示例 compose 默认传入中国大陆镜像构建参数：`APT_MIRROR=mirrors.aliyun.com`、`PYPI_INDEX=https://mirrors.aliyun.com/pypi/simple/`、`NPM_REGISTRY=https://registry.npmmirror.com`、`PLAYWRIGHT_DOWNLOAD_HOST=https://registry.npmmirror.com/-/binary/playwright`。`PYPI_INDEX` 只作用于 pip 步骤——uv 始终对 pypi.org 校验提交的锁，慢时配合 `BUILD_HTTPS_PROXY`。境外构建删除这四个镜像 `args:` 即回退官方 Debian/PyPI/npm/Playwright 源。

RC 构建请用 digest 钉版基底镜像以保证可复现：

```bash
docker buildx imagetools inspect python:3.13-slim-bookworm   # 复制摘要
export BASE_IMAGE=python:3.13-slim-bookworm@sha256:<digest>
docker compose build --no-cache
```

compose 模板会把 `BASE_IMAGE` 作为 build arg 透传，构建清单记录解析后的值。

最终镜像阶段还会以非特权 `mediasync` 用户执行 `media-sync mediacrawler doctor --accept-license --json`。checkout 不匹配或 MediaCrawler Python 缺少导入现在会直接让构建失败，不再产出直到登录时才失败的镜像。Chromium 启动仍是独立的运行时/深度预检门。

镜像包含两层：

| 层 | 位置 | 用途 |
| --- | --- | --- |
| media-sync 应用 venv | `/app/.venv` | 服务本体、CLI、REST API 与内嵌 Console v2 静态资源 |
| 锁定 MediaCrawler checkout | `/app/.upstream/MediaCrawler`（锁文件相对解析的精确路径，保留 `.git`）+ 独立 venv `/opt/mediacrawler-venv`，Playwright/Chromium 位于 `/opt/ms-playwright` | 按锁文件精确 SHA 运行的许可证门禁登录/抓取子进程；既有校验器检查 git 仓库、提交与干净工作树 |

`ffmpeg/ffprobe`、`Xvfb`、中文字体与健康检查均已内置。构建时会按锁定 SHA 克隆 MediaCrawler 供你自己非商业使用；不得发布或再分发该镜像。

## 2. 启动服务

```bash
docker compose up -d
```

- 公开根壳：<http://127.0.0.1:8632/>（默认只发布到宿主机回环）。当前 bundle 没有操作者登录壳，因此尚不能操作受保护 API。
- `/legacy` 与 `/api/docs` 是受保护路由，需要已建立的浏览器 session；当前已检入客户端还不能建立该 session。
- `GET`/`HEAD /api/v1/health` 与 `/api/v1/ready` 为容器探针有意保持公开；深度就绪及全部业务路由都要求鉴权。
- SQLite 状态库、归档、Emby 目录与 MediaCrawler 运行时都在 `media-sync-data` 卷的 `/data` 下。

拉取 0050 或更高版本后，应先重建镜像再重启；只执行 `git pull` 无法替换既有镜像中的静态前端：

```bash
git pull --ff-only
sh scripts/fetch_mediacrawler.sh
docker compose build --no-cache
docker compose up -d
```

`media-sync serve` 会在调用 Uvicorn 前解析必需凭据与 origin 策略。容器内部绑定 `0.0.0.0:8632`，Compose 只把它发布为宿主机 `127.0.0.1:8632`，因此显式回环浏览器 origin 可以使用 HTTP。每个请求仍须通过精确原始 `Host` 门禁，转发 Host/proto header 不受信任。

不得只把端口映射改成内网地址就暴露示例。每个非回环浏览器 origin 都必须作为精确 HTTPS origin 写入 `MEDIA_SYNC_OPERATOR_ALLOWED_ORIGINS`，由经过审查且保留允许 `Host` 的反向代理终止 TLS；禁止通配 origin。应用不信任 forwarding header，也不支持公网、多用户、RBAC、SSO 或 MFA 部署。

### 2.1 容器内 checkout 预检（阶段 B 门）

健康与就绪只证明进程和数据库。登录之前，先校验内嵌 MediaCrawler checkout
与运行时工具链：

```bash
docker compose exec media-sync   /app/.venv/bin/media-sync mediacrawler doctor --accept-license --json
```

并证明 Chromium 能以运行用户真正启动（而不只是路径存在）：

```bash
docker compose exec media-sync   /opt/mediacrawler-venv/bin/python -c   'from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True); print(b.version); b.close()'
```

两项都必须通过，阶段 B 才进入扫码登录。另外，构建清单必须记录真实的
Chromium 启动（构建期启动失败只会打印 `launch-failed` 而**不会**让镜像构建
失败，因此要显式检查）：

```bash
docker compose exec media-sync grep -E '^(chromium|node|pnpm|web_lock_sha256):' /opt/BUILD-MANIFEST.txt
# Chromium 必须输出真实版本——不得是 "chromium: launch-failed"。
# Node、pnpm 与 web_lock_sha256 用于证明进入镜像的前端构建身份。
```

控制台「诊断」中的「运行深度预检」会重复执行运行时检查，并显示
checkout 的逐项状态、稳定 `detail_code`、实际 Chromium 版本和构建清单版本。
许可证确认后若仍显示 `checkout_invalid / tracked_blob_mismatch` 等错误码，
先修复镜像中的锁定 checkout，再尝试扫码；预检失败时扫码和启用型 worker 会保持禁用。

旧镜像若显示 `license_digest_mismatch`，说明仍带有 0050 之前的资格摘要。请拉取本版本、重新预取并无缓存重建镜像。当前校验器比较规范化 LF 后的内容身份（兼容 Git 的 LF/CRLF checkout 形式），同时仍要求 tracked blob、锁定提交与干净工作树全部精确通过。

首个 `4c6d0bf` 镜像若显示 `runtime_invalid / runtime_imports_missing`，根因是正常的 venv launcher 符号链接被解引用成基础 Python。请拉取启动器修复并无缓存重建。保持 `MEDIA_SYNC_MEDIACRAWLER_PYTHON_EXECUTABLE=/opt/mediacrawler-venv/bin/python`，不要替换为解引用后的基础解释器路径。

## 3. 当前检查点的 Web 与扫码登录状态

后端现已提供严格的操作者 login/session/logout 契约、HttpOnly `SameSite=Strict` 进程内 Cookie，以及对 Cookie 鉴权不安全请求的 CSRF 强制。登录成功会轮换唯一 session；重启、退出、过期或凭据变化都会使其失效。非浏览器自动化可以另配独立解析的 Bearer 凭据，但它不能替代 0055 后续规划的浏览器专属确认权限。

Console v2 当前会在建立 session 前请求受保护 API，也不会为 mutation 附加仅存内存的 CSRF 值；`/legacy` 同样如此。因此此前的控制台扫码步骤暂停：收到公开根 HTML 或 healthcheck 变绿都不能证明控制台可用。请继续使用 CLI；已有订阅的常驻处理可使用 supervisor。只有 Web 登录/CSRF 检查点完成独立验证收尾后，才能恢复浏览器扫码资格验证。

## 4. 订阅与下载

订阅、调度、下载、归档及 Emby/Jellyfin 发布后端保持可用。当前检查点应使用既有 CLI 管理，而不是尚未完成鉴权集成的 Web 客户端。已有配置的无人值守链路可用 `docker compose --profile supervisor up -d` 启动常驻 supervisor；它不运行 `serve`，也不会获得操作者凭据。最终媒体库仍落在 `/data/library`。

## 5. 将媒体库接入 Emby/Jellyfin

把 `media-sync-data` 卷的 `/data/library` 以只读方式挂给媒体服务器并添加为“剧集”媒体库。NFO、海报与剧集按创作者确定性生成。若媒体服务器需要看到宿主机 bind mount，按 compose 注释把同一个 `/srv/media-sync/data` 挂到 media-sync；`MEDIA_SYNC_MEDIA_SERVER_LIBRARY_PATH` 必须填写 **Emby/Jellyfin API 返回的那一侧绝对路径**，不能填写浏览器路径或任意替代路径。

阶段 0054-A 支持一个不可变、环境变量托管的连接。把以下完整配置加到你本地 `docker-compose.yml` 的 `media-sync.environment`；六个选择器必须全部存在或全部省略：

| 环境变量 | 含义 |
| --- | --- |
| `MEDIA_SYNC_MEDIA_SERVER_PROVIDER` | `emby` 或 `jellyfin` |
| `MEDIA_SYNC_MEDIA_SERVER_BASE_URL` | 只有 scheme/host/port 的规范 HTTP(S) origin；不能带路径、userinfo、query 或 fragment |
| `MEDIA_SYNC_MEDIA_SERVER_LIBRARY_ID` | 固定 Virtual Folder 的 `ItemId` |
| `MEDIA_SYNC_MEDIA_SERVER_API_KEY_SECRET_REF` | `env:`、受限相对 `file:` 或 `keyring:` 引用；不是 key 值 |
| `MEDIA_SYNC_MEDIA_SERVER_LIBRARY_PATH` | 该 Virtual Folder 的精确服务器侧绝对路径 |
| `MEDIA_SYNC_MEDIA_SERVER_ALLOWED_CIDRS` | 显式允许的 IP/CIDR 列表；DNS 返回的每个地址都必须落在其中 |
| `MEDIA_SYNC_MEDIA_SERVER_VERIFY_TLS` | 默认 `true`；生产环境保持开启 |
| `MEDIA_SYNC_MEDIA_SERVER_TIMEOUT_SECONDS` | 0.1–60 秒，默认 10 |
| `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED` | 所有媒体服务器网络动作的共用服务端门，包括 probe、两种 scan 模式与作者 lookup；默认 `false` |

API key 值应通过引用指向的环境变量或 secret 文件注入，不得写入仓库。配置 API 只返回脱敏摘要：不会回显 key、完整 secret reference、Library ID、服务器路径或网络范围。连接器禁止环境代理与重定向，校验全部 DNS 答案并绑定实际连接 IP，同时保留原始 Host/TLS SNI。

先保持 `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED=false`。通过经过审查的鉴权客户端核对配置 origin、TLS 姿态、网络规则数量与 Library 摘要后，再打开门并重启。以下后端行为已经实现，但原 Console v2 控件要等 Web 鉴权集成后才能使用：

1. 受管树检查会分页验证数据库成功发布链授权的 manifest；它只读，不修复、删除、创建作者锁或泄露宿主路径。
2. 连接探测只调用 `GET /System/Info` 与 `GET /Library/VirtualFolders`，并要求 Library ID 和路径精确唯一匹配。
3. 项目检查会对精确受管 provider/path 身份执行完整且有界的只读查找。`not_found` 或唯一 `matched` 都只是一次观察，不证明刷新完成或媒体可播放。
4. 严格 legacy `{}` 刷新只调用 `POST /Items/{configured-library-id}/Refresh`；`404/405/501` 会关闭失败，绝不回退到全库 `/Library/Refresh`。Operation 成功只证明收到可信 2xx 接受。
5. 作者刷新并核验在当前且完整的媒体树检查授予动作后，只接受精确 `{"author_id":"<uuid>"}`。作者模式先要求完整 absent baseline；精确项目已经存在时不会发送 POST，并返回 `media_server_scan_observation_precondition_failed`。成功需要一次刷新被接受，随后间隔两次观察到同一唯一项目；仍不证明 provider task completion 或可播放。
6. 持久 `media-server-probe` / `media-server-scan` Operation 会区分 accepted、observed、acceptance unknown 与 completion unknown。进入 transport 后无法确认接受时以不可重试的 `media_server_scan_acceptance_unknown` 收尾；已经可信接受但无法证明观察时以不可重试的 `media_server_scan_completion_unknown` 收尾，并保留 accepted checkpoint。两种歧义都不得自动重试。

服务重启时，处于 `preparing` 或 `baselining` 的作者观察属于 dispatch 前中断；`dispatching` 收敛为 acceptance unknown；`accepted` 或 `polling` 收敛为 completion unknown 并保留 accepted checkpoint；只有有效持久 `observed` checkpoint 才能收敛为成功。Legacy targetless scan 保持 0054-A 的保守恢复。Probe 可人工重试；scan 歧义则必须先在服务器侧检查，才能考虑新请求。

`GET /api/v1/qualifications` schema v2 会把本地自动化计数、实现状态与真人资格分开。当前工作区没有真实服务器凭据，已实现的连接 probe、Library 发现、定向刷新接受、项目查找与刷新后项目观察真人状态都仍为 `NOT_RUN`。`provider_task_completion` 为 `NOT_IMPLEMENTED`，原因是 `provider_api_unsupported`；经鉴权播放证据与导出后自动扫描也为 `NOT_IMPLEMENTED`。所有未实现能力的 `human_status` 都是 `null`，不得写成真人 `NOT_RUN`、`FAIL` 或 `PASS`。

## 6. 验收清单（如实记录）

| 验收行 | 证据 |
| --- | --- |
| 真人扫码登录（哪个平台/账户） | 当前检查点保持 `NOT_RUN`；Web 鉴权交付后才记录鉴权控制台结果及 `login-status` |
| 创作者抓取（哪个创作者、条数） | 调度任务结果 + 资产计数 |
| 真实媒体下载 | 资产行达到 `verified`/`archived`；`/data/archive` 下出现 SHA-256 文件 |
| Emby 目录发布 | `/data/library` 的作者目录列表 |
| Emby/Jellyfin 真实连接与 Library 发现 | `media-server-probe` 成功记录 + 服务器版本；未执行记 `NOT_RUN` |
| 定向刷新被真实服务器接受 | `media-server-scan` 成功记录；不等同扫描完成，未执行记 `NOT_RUN` |
| 真实服务器精确 provider/path 项目查找 | 0054-B 已实现；以一次完整 lookup 快照为证；未执行记 `NOT_RUN` |
| 真实服务器刷新后项目观察 | 0054-B 已实现；absent baseline + 一次 accepted POST + 同一唯一项目连续观察两次；未执行记 `NOT_RUN` |
| Provider task completion | `NOT_IMPLEMENTED`（`provider_api_unsupported`）；没有真人状态 |
| 经鉴权的播放证据 | `NOT_IMPLEMENTED`；后端操作者鉴权本身不等于播放证据；没有真人状态 |
| 导出后自动扫描 | `NOT_IMPLEMENTED`；尚无已冻结后续归属，也没有真人状态 |

现网证据以实际运行为准；未执行的项一律保持 `NOT_RUN`，遵守项目真实性规则。
