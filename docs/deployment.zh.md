[English](deployment.md) | **中文**

# Docker 部署与 Web 后台验证

本指南把 media-sync 作为自托管容器部署（内含锁定版本 MediaCrawler 运行时），并全程通过 Web Console v2 验证扫码登录与订阅下载。由执行 0040/0041 引入、0050 更新，需要装有 Docker（compose v2）的 Linux 主机。

## 1. 构建

```bash
git clone <你的仓库> media-sync && cd media-sync
sh scripts/fetch_mediacrawler.sh   # 必选：宿主机预取锁定上游
cp docker-compose.example.yml docker-compose.yml   # 本地副本已被 git 忽略
docker compose build          # 如需改端口/路径，先编辑你的本地副本
```

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

- Web 控制台：<http://127.0.0.1:8632/>（默认只发布到宿主机回环）。
- 旧版回退控制台：<http://127.0.0.1:8632/legacy>（保留一个迁移周期）。
- REST 文档：<http://127.0.0.1:8632/api/docs>。
- SQLite 状态库、归档、Emby 目录与 MediaCrawler 运行时都在 `media-sync-data` 卷的 `/data` 下。

拉取 0050 或更高版本后，应先重建镜像再重启；只执行 `git pull` 无法替换既有镜像中的静态前端：

```bash
git pull --ff-only
sh scripts/fetch_mediacrawler.sh
docker compose build --no-cache
docker compose up -d
```

控制台与 API **没有鉴权** —— 只发布到可信网络。要在内网开放，请编辑你自己的本地 `docker-compose.yml`（从 example 复制而来），把 `127.0.0.1:8632:8632` 改成 `192.168.x.x:8632:8632`，风险自负；example 模板本身保持原样，`git pull` 更新时不会与你的部署配置冲突。

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

## 3. 控制台扫码登录

1. 打开 <http://127.0.0.1:8632/>。该浏览器首次访问时阅读并一次性确认个人使用/许可证与可信网络提示；确认保存在浏览器 `localStorage`，普通刷新不会再询问，设置页可主动重置。
2. 进入「平台账户」添加账户：选择平台（如 `bili`）、显示名，登录方式选 `扫码 QR`。
3. 点击该账户行的「扫码登录」。Console v2 会自动发送 MediaCrawler 启用与许可证确认字段；后端仍会在启动 child 前执行完整深度预检。
4. 弹窗会轮询显示由容器内 Xvfb 有头登录子进程中继出来的二维码图片，180 秒内用平台 App 扫码。
5. 弹窗显示登录结果；账户行应变为 `authenticated`。

若约 20 秒后二维码仍未出现，查看 `docker compose logs media-sync` —— 常见原因是 checkout SHA 不匹配（构建参数）或挑战已过期（重试登录即可）。

## 4. 订阅与下载

1. 在「创作者订阅」选择账户，填写稳定的创作者 ID（B 站为数字 UID）、显示名与较小的单次上限（如 5）。
2. 点击「添加订阅」，再点「立即运行」使其到期。
3. 点击「运行同步」——首次浏览器确认后，控制台会带上两个必需的 MediaCrawler 门禁字段，后端仍会重新校验——运行创作者抓取子进程并导入内容/资产。
4. 点击「运行下载/导出 pipeline」—— 通过签名 locator 刷新下载媒体、按 SHA-256 归档并发布 Emby/Jellyfin 目录。
5. 在「调度任务」与「后台操作记录」观察结果；「媒体资产」列出已下载/已验证资产；媒体库落在卷内 `/data/library`。

如需无人值守链路，改用常驻监督服务：`docker compose --profile supervisor up -d`。

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
| `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED` | probe/scan 共用服务端门，默认 `false` |

API key 值应通过引用指向的环境变量或 secret 文件注入，不得写入仓库。配置 API 只返回脱敏摘要：不会回显 key、完整 secret reference、Library ID、服务器路径或网络范围。连接器禁止环境代理与重定向，校验全部 DNS 答案并绑定实际连接 IP，同时保留原始 Host/TLS SNI。

先保持 `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED=false` 启动并在「设置」检查摘要；核对 origin、TLS、网络规则数量与 Library 摘要后再打开门并重启。随后进入「媒体库」：

1. 点作者行的「检查媒体树」，分页验证数据库成功发布链授权的 manifest；检查只读，不修复、删除、创建作者锁或泄露宿主路径。
2. 点「测试连接」。后端只调用 `GET /System/Info` 与 `GET /Library/VirtualFolders`，并要求 Library ID 和路径精确唯一匹配。
3. 点「定向刷新」。后端只调用 `POST /Items/{configured-library-id}/Refresh`；`404/405/501` 会关闭失败，绝不回退到全库 `/Library/Refresh`。
4. 在「调度任务 → 持久操作」查看 `media-server-probe` / `media-server-scan`。scan 成功仅表示请求已接受；一旦越过应用层 dispatch gate，超时、断连、取消或未预期的传输/响应失败都会终结为不可重试的 `media_server_scan_acceptance_unknown`。不得自动再次提交刷新；必须先在服务器侧人工核对。

若服务重启时远端 Operation 已丢失 lease，进行中的 probe 与定向 scan 都会收敛为 `interrupted`，因为 0054-A 不持久化远端任务标识。probe 可以人工重试；中断的定向 scan 会显示为不可重试，任何新请求前都必须先在服务器侧核对。

`GET /api/v1/qualifications` 会把本地自动化计数、实现状态与真人资格分开。当前工作区没有真实服务器凭据，已实现的连接 probe、Library 发现与定向刷新接受三行真人状态仍为 `NOT_RUN`。扫描完成轮询与 provider/path 项目查找在另行冻结 0054-B 前保持 `NOT_IMPLEMENTED`；经鉴权的播放证据属于 0055。导出后自动扫描同样为 `NOT_IMPLEMENTED`，但尚无已冻结的后续归属。所有 `NOT_IMPLEMENTED` 能力的 `human_status` 都是 `null`，不得写成真人 `NOT_RUN`、`FAIL` 或 `PASS`。

## 6. 验收清单（如实记录）

| 验收行 | 证据 |
| --- | --- |
| 真人扫码登录（哪个平台/账户） | 控制台结果 + `login-status` 显示 `authenticated` |
| 创作者抓取（哪个创作者、条数） | 调度任务结果 + 资产计数 |
| 真实媒体下载 | 资产行达到 `verified`/`archived`；`/data/archive` 下出现 SHA-256 文件 |
| Emby 目录发布 | `/data/library` 的作者目录列表 |
| Emby/Jellyfin 真实连接与 Library 发现 | `media-server-probe` 成功记录 + 服务器版本；未执行记 `NOT_RUN` |
| 定向刷新被真实服务器接受 | `media-server-scan` 成功记录；不等同扫描完成，未执行记 `NOT_RUN` |
| 扫描完成与 provider/path 项目查找 | 0054-A 为 `NOT_IMPLEMENTED`；0054-B 尚待另行冻结；没有真人状态 |
| 经鉴权的播放证据 | 0054-A 为 `NOT_IMPLEMENTED`；后移至 0055；没有真人状态 |
| 导出后自动扫描 | `NOT_IMPLEMENTED`；尚无已冻结后续归属，也没有真人状态 |

现网证据以实际运行为准；未执行的项一律保持 `NOT_RUN`，遵守项目真实性规则。
