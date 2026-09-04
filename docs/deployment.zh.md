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

把 `media-sync-data` 卷的 `/data/library` 以只读方式挂给媒体服务器并添加为“剧集”媒体库。NFO、海报与剧集按创作者确定性生成。

## 6. 验收清单（如实记录）

| 验收行 | 证据 |
| --- | --- |
| 真人扫码登录（哪个平台/账户） | 控制台结果 + `login-status` 显示 `authenticated` |
| 创作者抓取（哪个创作者、条数） | 调度任务结果 + 资产计数 |
| 真实媒体下载 | 资产行达到 `verified`/`archived`；`/data/archive` 下出现 SHA-256 文件 |
| Emby 目录发布 | `/data/library` 的作者目录列表 |
| 媒体服务器扫描/播放 | 可选；未执行则记 `NOT_RUN` |

现网证据以实际运行为准；未执行的项一律保持 `NOT_RUN`，遵守项目真实性规则。
