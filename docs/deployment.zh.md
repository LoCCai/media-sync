[English](deployment.md) | **中文**

# Docker 部署与安全控制台检查点

本指南使用内含锁定 MediaCrawler 运行时的自托管容器部署 media-sync，要求 Linux 主机与 Docker Compose v2。当前 0055 安全控制台与启动预检已实现，本地离线与合成浏览器门禁已通过；准确状态见[验证](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)。后端鉴权、Web session／内存 CSRF、退出／过期与二维码／SSE 已接线，`/legacy` 仅提供受保护迁移提示；无 v2 构建时根页仅提示构建／CLI。当前 Linux 镜像、运行用户权限与平台／媒体服务器真人流程仍为 NOT_RUN，不能用旧 0050 镜像 PASS 或公开 health 成功替代。

## 内容归属冲突（0061）

`content_ownership_conflict`表示新观察内容身份与数据库已有作者归属冲突。拒绝写入，不移动原内容或修改其元数据/资产；同作者仍可更新。该Job终止，不自动重试、不累计到账户熔断；未来正常订阅调度另计，需要停止新周期时请暂停订阅。保留数据库/文件和精确Job安全报告，再检查所选作者及来源。不要为了消除错误删除媒体、更换Cookie或手工改数据库归属。

CLI无法确认耐久失败状态时，可能报告`status=unknown`、`error_code=ingestion_state_unconfirmed`、`observed_error_code=content_ownership_conflict`。这要求再次尝试前先检查精确Run及服务/存储健康，不是确认终止失败或允许重试。无需新schema迁移或配置。本增量不实现B站动态附件、不部署镜像、不授权真人重试、不恢复supervisor。最终门禁及未验证范围见[0061验证](executions/0061-bili-dynamic-authority/verification.zh.md)。

## 微博作者资料（0060）

选择已认证的微博保存会话或Cookie账户后，输入规范数字作者UID，完成输入（失焦/回车）会自动查询一次。先检查一次登录config，再请求一次精确作者资料，不请求帖子/评论/下载。昵称来自平台观察，本地备注可选，来源主页固定https://weibo.com/u/UID；刷新不会重命名已有作者/归档/导出路径。查询无需Emby/Jellyfin连接或全历史确认；另行执行的微博采集策略仍须全历史确认。

头像为可选同源PNG，隔离限量下载解码，HTTPS CDN规则绑定资料平台。窄新浪crop/尺寸路径及可选profile_image_url回退是合成设计合同，不是已经证明的真人URL形状；未知/带签名/重定向/不支持图片不获取，昵称和旧头像仍保留。其他五平台自动资料继续待完成。本轮无新依赖或数据库迁移。见[0060验证](executions/0060-weibo-creator-profile/verification.zh.md)，部署/真人验证须单独进行，不自动恢复supervisor。

## B站有界订阅（0059）

新B站调度采集和dry-run采用可续抓的普通投稿单元，不再要求旧的无限历史勾选。每轮最多校验min(max_items,30)条详情、最多两次作者列表尝试；浏览器/认证初始化和最多两次WBI签名密钥读取另计。头部更新与历史扫描交替，私有检查点跨成功轮次保留未完成身份。旧cursor从不假定覆盖的新状态开始，损坏或错配的新版本cursor安全拒绝，不静默重置。

订阅详情区分本轮推进、列表变化后重新检查和源末尾观察，均不声明作者全部历史或动态附件已采完。小max_items**不是下载上限**，流水线可能处理该订阅此前待办资产。单独授权的纯采集金丝雀须继续保持supervisor停止；源码发布不等于授权部署、重试或后台下载。没有新数据库迁移或依赖，仍须配套保护状态数据库和凭据。离线证据和真人排除范围见[0059验证](executions/0059-bili-bounded-capture/verification.zh.md)。

## 粘贴 Cookie 登录（0058）

账户页现提供 B 站、小红书、微博、知乎的明确 **粘贴 → 远程本人认证校验 → 私密保存** 流程。只粘贴浏览器请求中的 Cookie 头值，不含 `Cookie:` 前缀、Set-Cookie 属性或 JSON 导出；不要把凭据发到聊天或附进支持报告。最多16 KiB、128个唯一键值对，保留值内等号和合法外层引号。抖音、快手、贴吧仍缺少可靠远程身份验证器，明确标记不可用，不会凭本地 Cookie 标记判定已认证。

继续使用精确 HTTPS Origin、后台会话和 CSRF 保护；验证前须由操作者明确确认上游许可证。失败保留账户原凭据。结果未知或进程中断时，先查看当前账户和精确 Operation，再决定是否明确重新提交；关闭弹窗不等于取消服务端工作。校验不会采集内容或启动下载。

成功候选保存为 `managed:UUID` 引用的不可变私密文件，位于 `MEDIA_SYNC_STATE_DIR/credentials`（镜像默认 `/data/state/credentials`），**不写入**只读 `/run/secrets`。运行用户必须拥有该私密目录并可创建/读取；Linux目录/文件权限为0700/0600，Windows使用受保护DACL。应在受保护存储中配套备份状态数据库和完整credentials目录；不得提交、暴露或放进诊断包。旧版本和可能未引用版本有意保留，暂不提供自动清理。只恢复数据库、不恢复其引用文件会导致登录复用失败。现有明确配置的file/env/keyring引用仍受支持。

B站Cookie账户可在订阅流程单独查询作者昵称/头像。后续Cookie采集/详情子进程使用全新非持久浏览器上下文和完整输入，不会误用旧保存会话。这些是源码/离线验证能力，不是真实平台验收。本增量不部署生产、不恢复supervisor，也不以断言“修复”历史零内容采集，更不代表七平台采集/归档/播放通过。见[0058验证](executions/0058-cookie-login/verification.zh.md)。

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

构建在独立 Node/pnpm 阶段编译 SvelteKit 5 控制台，只把静态产物复制进 Python 应用；最终运行镜像不包含 pnpm 和前端 `node_modules`，但包含锁定爬虫 JavaScript 签名所需的独立 Debian Node.js 运行时。构建清单记录构建期版本、前端锁文件摘要和 `javascript_runtime`。

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

启动或升级前，先确认凭据文件对**最终镜像的运行用户**可读。Dockerfile 使用 UID 1000；普通 rootful Linux 映射下，root 所有的 `0600` 源文件对此用户不可读，应只调整该文件的所有者或受限读取权限来匹配实际运行身份。Rootless／user namespace 映射须按主机检查。不能假设文件型 Compose secret 会重映射 uid/gid/mode，不得改成所有人可读或递归变更所有权。

构建后，可使用以下仅配置预检绕过普通 entrypoint；它按最终镜像运行身份读取并验证配置，不输出凭据：

```bash
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync serve --check-config
```

这是尚未在当前 Windows 工作站执行的 Docker 示例（无 Docker），不是 Linux UID／挂载权限通过声明。`serve --check-config` 与正常 serve 共用 settings、凭据、origin 和 bind 语法验证，支持相同 host/port 覆盖；成功只输出固定安全状态，不构造 app／数据库、不创建目录、不解析 DNS、不绑定端口或迁移。它不证明端口可用、完整运行就绪或最终镜像已合格；真实挂载可读性仍须在部署主机执行。当前 entrypoint 已对 `serve`（包括 `-- serve`）在 Xvfb／`db init` 前预检，显式 `--check-config`／`--help` 不迁移。正常启动通过预检后仍会迁移，因此升级前仍须兼容备份，当前镜像启动／重启／恢复继续待验证。

```bash
docker compose up -d
```

- 公开根登录入口：<http://127.0.0.1:8632/>（仅宿主回环）。成功 login 后还须完成 session/CSRF 初始化才挂载私有页面；8 个精确 SPA HTML 深链接会把未登录导航 303 到该入口。
- `/legacy` 为受保护的迁移提示，`/api/docs` 也继续受保护；二者均不重新开放匿名业务访问。
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

### 2.2 检查真实扫码浏览器启动方式

本次登录运行环境修复让登录、作者和详情子进程共用批准的浏览器环境，包含 `PLAYWRIGHT_BROWSERS_PATH`。七平台常规上游启动显式使用已安装的 Playwright Chromium；五个平台的 `channel="chrome"` 在内存适配，不修改锁定 checkout。此策略无需另外安装系统 Google Chrome；平台网络和风控兼容仍须真人验收。

镜像新增 `xdpyinfo`，数据库初始化前等待 Xvfb 真实连接成功。`xvfb_probe_unavailable`、`xvfb_start_failed` 或 `xvfb_ready_timeout` 会在迁移前以非零状态停止启动。保留后台配置预检和受限凭据，不通过改 Origin 或把浏览器复制到用户目录来修复。

重建镜像并重新创建服务后，按默认运行 UID 执行这个不接触凭据的检查：

```bash
docker compose exec -T media-sync /app/.venv/bin/python /app/scripts/check_login_browser.py --python /opt/mediacrawler-venv/bin/python
```

成功返回 `ok: true`、`mode: headed-persistent`、数字浏览器版本及 `live_qualification: NOT_RUN`。检查以临时 profile 启动空白持久浏览器，不访问平台、不读取账户 profile，返回前关闭浏览器进程树。普通失败/超时有监督；POSIX 父进程被强杀不在预检清理保证范围内。账户登录预检已使用相同有头检查，通用深度 readiness 仍是无头。空白浏览器成功和公开 readiness 都不证明二维码已显示或账户已认证。

既有部署须保留个人 Compose/HTTPS Origin、secret 挂载及命名卷。升级前备份状态，再依次执行 `git pull --ff-only`、`docker compose build media-sync`、上面的仅配置预检、`docker compose up -d --no-deps --force-recreate media-sync`。不要执行 `down -v`，仅 restart 无法加载这次源码/镜像变更。如启用了可选 supervisor，也要从同一新镜像重建该服务。实际证据及待跑真人门槛见[修复验证与交接](executions/0055-operator-auth-playback-evidence/login-runtime/verification.zh.md)。

### 2.3 JavaScript 启动依赖与可操作失败提示

上游入口会在浏览器启动前导入调用 PyExecJS 的 helper，因此空白 Chromium PASS 不代表完整登录运行时就绪。最终镜像现安装 Debian Node.js，并在清单记录 `javascript_runtime`。Python doctor（登录预检与构建末尾非 root 门禁也会调用）实际执行固定 JavaScript 算术探针；缺少/损坏执行环境会安全返回 `runtime_javascript_unavailable`。仅更新 Python 源码或重启旧镜像无法安装此依赖，须保留现有私人 Compose 重新构建并重建容器。

二维码转发现接收上游 base64 字符串与允许的 PNG/JPEG/WebP base64 data URI，并规范化成有界 PNG，不抓取 URL 或打开图片查看器。不支持/畸形/超限输入静默拒绝，既有字节输入保持有界原样兼容。正常转发失败会删除私有临时文件；强杀子进程仍可能在私有账户目录留下二维码临时文件，因此不承诺完整强杀清理。

账户页把唯一关联的最近登录结果与预检分开显示。即使图片传递报错或悬挂，只要观察到 Operation 终态就停止等待二维码。`operation_login_browser_launch_failed` 标识实际启动边界；旧 `operation_login_failed` 仍是未知，不猜测网络/Cookie 原因。畸形、歧义或互相矛盾的持久诊断不投影。见[本轮验证](executions/0055-operator-auth-playback-evidence/login-diagnostics/verification.zh.md)与[运行后续验证](executions/0055-operator-auth-playback-evidence/login-runtime-followup/verification.zh.md)。粘贴 Cookie 校验/保存 UI 已列入后续需求，本检查点尚不可用；不要把 Cookie 发到聊天。

## 3. 当前检查点的 Web 与扫码登录状态

后端现已提供严格的操作者 login/session/logout 契约、HttpOnly `SameSite=Strict` 进程内 Cookie，以及对 Cookie 鉴权不安全请求的 CSRF 强制。登录成功会轮换唯一 session；重启、退出、过期或凭据变化都会使其失效。非浏览器自动化可以另配独立解析的 Bearer 凭据，但它不能替代 0055 后续规划的浏览器专属确认权限。

Console v2 现已实现串行 login/session/logout、仅内存 CSRF、私有页面门、过期／401 重置与 QR／SSE 会话接线；这些功能已通过[本地合成浏览器验证](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)，视频仅加载／解码、未点击播放，不构成平台／媒体服务器真人资格。登录 200 本身不授予私有页面权限，仍须 session 初始化成功；延迟旧响应不能恢复旧会话，不自动重放写请求。引导允许“稍后”仅浏览，不接受 MediaCrawler 许可证或启动爬虫。CLI／常驻 supervisor 继续可用；获授权真人金丝雀不以 P1 播放确认 UI 为前置。

## 4. 订阅与下载

订阅、调度、下载、归档与 Emby/Jellyfin 发布后端继续可用。Web 管理会话接线已实现并通过[本地合成浏览器验证](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)；CLI 可继续用于已授权流程。已有配置的无人值守链路可通过 `docker compose --profile supervisor up -d` 启动常驻 supervisor；它不运行 serve，也不接收操作者凭据。最终媒体库位于 `/data/library`。

## 5. 将媒体库接入 Emby/Jellyfin

### 先使用本地目录：无需连接服务器

下载、归档和导出兼容文件，不要求 Emby/Jellyfin 地址、API Key、连接探测或播放确认。本地导出仍要求归档资产已校验，并保留既有文件归属、完整性与发布检查。只需要目录时，将可选媒体服务器配置字段全部省略即可。

把 `media-sync-data` 卷的 `/data/library` 以只读方式挂给媒体服务器，添加为“剧集”媒体库，然后在 Emby/Jellyfin 自身发起媒体库扫描。NFO、海报与剧集按创作者确定性生成。若媒体服务器需要看到宿主机 bind mount，按 compose 注释把同一个 `/srv/media-sync/data` 挂到 media-sync。共享文件必须允许媒体服务器进程读取；media-sync 导出成功本身不证明服务器侧路径映射、扫描或播放已经成功。

后续新增文件后，可在 Emby/Jellyfin 再次扫描，或按该服务器支持的方式自行配置定时／实时扫描；不能假定自动扫描已开启。media-sync 不会在导出完成后自动请求服务器刷新。没有 API 联动或远程播放资格，也可以使用导出目录与本地发布记录。

### 可选 API 联动：方便探测、主动刷新与核验

只有希望从 media-sync 发起连接探测、明确请求刷新、检查服务器项目或记录播放证据时，才需配置此项。这些是独立的可选操作，不负责解锁本地导出，也不会自动开启扫描。阶段 0054-A 支持一个不可变、环境变量托管的连接。把以下完整配置加到你本地 `docker-compose.yml` 的 `media-sync.environment`；六个选择器必须全部存在或全部省略，不完整配置仍会报错。

仅对于这项可选联动，`MEDIA_SYNC_MEDIA_SERVER_LIBRARY_PATH` 必须填写 **Emby/Jellyfin API 返回的那一侧绝对路径**，不能填写浏览器路径或任意替代路径。

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
| `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED` | 所有媒体服务器网络动作的共用服务端门，包括 probe、两种 scan 模式、作者 lookup 与播放确认重校验；默认 `false` |

API key 值应通过引用指向的环境变量或 secret 文件注入，不得写入仓库。配置 API 只返回脱敏摘要：不会回显 key、完整 secret reference、Library ID、服务器路径或网络范围。连接器禁止环境代理与重定向，校验全部 DNS 答案并绑定实际连接 IP，同时保留原始 Host/TLS SNI。

先保持 `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED=false`。通过经过审查的鉴权客户端核对配置 origin、TLS 姿态、网络规则数量与 Library 摘要后，再打开门并重启。以下后端行为已实现；Console v2 鉴权接线已通过本地合成浏览器验证，而新增播放确认 UI 不属于当前 P0 切片：

1. 受管树检查会分页验证数据库成功发布链授权的 manifest；它只读，不修复、删除、创建作者锁或泄露宿主路径。
2. 连接探测只调用 `GET /System/Info` 与 `GET /Library/VirtualFolders`，并要求 Library ID 和路径精确唯一匹配。
3. 项目检查会对精确受管 provider/path 身份执行完整且有界的只读查找。`not_found` 或唯一 `matched` 都只是一次观察，不证明刷新完成或媒体可播放。
4. 严格 legacy `{}` 刷新只调用 `POST /Items/{configured-library-id}/Refresh`；`404/405/501` 会关闭失败，绝不回退到全库 `/Library/Refresh`。Operation 成功只证明收到可信 2xx 接受。
5. 作者刷新并核验在当前且完整的媒体树检查授予动作后，只接受精确 `{"author_id":"<uuid>"}`。作者模式先要求完整 absent baseline；精确项目已经存在时不会发送 POST，并返回 `media_server_scan_observation_precondition_failed`。成功需要一次刷新被接受，随后间隔两次观察到同一唯一项目；仍不证明 provider task completion 或可播放。
6. 持久 `media-server-probe` / `media-server-scan` Operation 会区分 accepted、observed、acceptance unknown 与 completion unknown。进入 transport 后无法确认接受时以不可重试的 `media_server_scan_acceptance_unknown` 收尾；已经可信接受但无法证明观察时以不可重试的 `media_server_scan_completion_unknown` 收尾，并保留 accepted checkpoint。两种歧义都不得自动重试。
7. 播放确认使用 `POST /api/v1/media-server/playback-evidence`。它不是自动化 endpoint：必须具有已登录浏览器 session、精确 Origin 与 CSRF，并在进入 handler 前拒绝 Bearer-only 或 Cookie/Authorization 混用。严格正文只含规范 `author_id` 与 matched lookup 返回的不透明 `observation_fingerprint`；`Idempotency-Key`、selector、路径、远端 ID、timestamp 与说明文本均被拒绝。服务端先执行 resolve → 一次完整唯一 lookup → resolve，再打开短 create-or-replay 事务，且不返回 fingerprint 或内部上下文摘要。播放确认 UI 仍待 P1 实现，该后端契约尚未成为现成控制台交互，也不阻塞 CLI 真人金丝雀。
8. 经 Cookie 或 Bearer 鉴权的客户端可读取 `GET /api/v1/media-server/playback-evidence/by-author/{author_id}?limit=20`。只接受规范作者 UUID 和一个可选 limit（1–50）；一次稳定完整的新 lookup 完成后才只读查询 current/history。当前证据单独返回，历史截断显式报告。远端不确定使当前权威不可用、历史未知，不能误标过期或 PASS。

服务重启时，处于 `preparing` 或 `baselining` 的作者观察属于 dispatch 前中断；`dispatching` 收敛为 acceptance unknown；`accepted` 或 `polling` 收敛为 completion unknown 并保留 accepted checkpoint；只有有效持久 `observed` checkpoint 才能收敛为成功。Legacy targetless scan 保持 0054-A 的保守恢复。Probe 可人工重试；scan 歧义则必须先在服务器侧检查，才能考虑新请求。

`GET /api/v1/qualifications` 现为 schema v3，只接受一个可选规范 `author_id`；未指定时播放 scope 为 `not_requested`，不查询证据或远端。Playback 已 IMPLEMENTED，无精确当前确认则为 NOT_RUN。指定作者时 PASS 要求当前持久真人确认，并显式限定到该作者。既有自动化计数／Operation 结果不授予真人 PASS。工作区全部真人行保持 NOT_RUN。Provider task completion 仍 NOT_IMPLEMENTED（`provider_api_unsupported`），自动扫描仍 NOT_IMPLEMENTED，二者真人状态为空。

## 6. 验收清单（如实记录）

| 验收行 | 证据 |
| --- | --- |
| 真人扫码登录（哪个平台／账户） | 仍为 `NOT_RUN`；仅在获授权平台实测后记录精确提交、CLI 或已验证 Web 流程与 `login-status`，合成二维码不构成真人登录 |
| 创作者抓取（哪个创作者、条数） | 调度任务结果 + 资产计数 |
| 真实媒体下载 | 资产行达到 `verified`/`archived`；`/data/archive` 下出现 SHA-256 文件 |
| Emby 目录发布 | `/data/library` 的作者目录列表 |
| Emby/Jellyfin 真实连接与 Library 发现 | `media-server-probe` 成功记录 + 服务器版本；未执行记 `NOT_RUN` |
| 定向刷新被真实服务器接受 | `media-server-scan` 成功记录；不等同扫描完成，未执行记 `NOT_RUN` |
| 真实服务器精确 provider/path 项目查找 | 0054-B 已实现；以一次完整 lookup 快照为证；未执行记 `NOT_RUN` |
| 真实服务器刷新后项目观察 | 0054-B 已实现；absent baseline + 一次 accepted POST + 同一唯一项目连续观察两次；未执行记 `NOT_RUN` |
| Provider task completion | `NOT_IMPLEMENTED`（`provider_api_unsupported`）；没有真人状态 |
| 仅浏览器播放确认后端/API | 已实现并通过离线验证；未向真实 Emby/Jellyfin 提交真人播放，因此不授予现网状态 |
| 播放证据 current/stale/unknown 投影与资格 | Schema v3 中已 IMPLEMENTED；无选定作者的精确当前证据则为 NOT_RUN。Web 确认 UI 与真人播放资格仍待完成 |
| 导出后自动扫描 | `NOT_IMPLEMENTED`；尚无已冻结后续归属，也没有真人状态 |

现网证据以实际运行为准；未执行的项一律保持 `NOT_RUN`，遵守项目真实性规则。
