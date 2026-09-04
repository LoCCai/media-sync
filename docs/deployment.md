**English** | [中文](deployment.zh.md)

# Docker deployment and web-console verification

This guide deploys media-sync as a self-hosted container with the pinned MediaCrawler runtime, then verifies QR login and subscription downloading entirely through Web Console v2. It was introduced by executions 0040/0041, updated by 0050, and expects a Linux host with Docker (compose v2).

## 1. Build

```bash
git clone <your-fork> media-sync && cd media-sync
sh scripts/fetch_mediacrawler.sh   # MANDATORY host-side prefetch of the locked upstream
cp docker-compose.example.yml docker-compose.yml   # your live copy is git-ignored
docker compose build          # edit your copy first if you need different ports/paths
```

The build now compiles the SvelteKit 5 console in a dedicated Node/pnpm stage and copies only its static output into the Python application. Node.js, pnpm and `node_modules` are not present in the final runtime image. The build manifest records their build-time versions and the frontend lock-file digest.

Step 0 (`fetch_mediacrawler.sh`) clones the exact MediaCrawler commit from `upstreams.lock.json` into the git-ignored `.mediacrawler-local/` directory; the build COPYs and SHA-verifies it, so **the build container itself never touches github.com** (mainland hosts whose container network cannot reach GitHub set `BUILD_HTTPS_PROXY=...` for this host-side clone instead). Re-run the script after `git pull` changes the locked commit.

The example compose passes mainland-China mirror build args by default: `APT_MIRROR=mirrors.aliyun.com`, `PYPI_INDEX=https://mirrors.aliyun.com/pypi/simple/`, `NPM_REGISTRY=https://registry.npmmirror.com` and `PLAYWRIGHT_DOWNLOAD_HOST=https://registry.npmmirror.com/-/binary/playwright`. `PYPI_INDEX` applies to pip steps only — uv validates the committed lock against pypi.org, so keep `BUILD_HTTPS_PROXY` handy when that is slow. Building outside mainland China? Delete the four mirror `args:` lines to fall back to official Debian/PyPI/npm/Playwright sources.

For RC builds, pin the base image by digest so the build is reproducible:

```bash
docker buildx imagetools inspect python:3.13-slim-bookworm   # copy the digest
export BASE_IMAGE=python:3.13-slim-bookworm@sha256:<digest>
docker compose build --no-cache
```

The compose template passes `BASE_IMAGE` through as a build arg and the build
manifest records the resolved value.

The final image stage also runs `media-sync mediacrawler doctor --accept-license --json` as the unprivileged `mediasync` user. A checkout mismatch or missing MediaCrawler Python import now fails the build instead of producing an image that can only fail later at login time. Chromium launch remains a separate runtime/deep-preflight gate.

The image contains two layers:

| Layer | Location | Purpose |
| --- | --- | --- |
| media-sync app venv | `/app/.venv` | The service, CLI, REST API and embedded Console v2 static bundle |
| Pinned MediaCrawler checkout | `/app/.upstream/MediaCrawler` (the exact lock-relative path, `.git` kept) + its own venv at `/opt/mediacrawler-venv` with Playwright/Chromium in `/opt/ms-playwright` | License-gated login/crawl children at the exact SHA recorded in `upstreams.lock.json`; the existing verifier checks the git repository, commit and clean tree |

`ffmpeg/ffprobe`, `Xvfb`, CJK fonts and a healthcheck are baked in. Building clones MediaCrawler at the locked SHA for your own non-commercial use; do not publish or redistribute the image.

## 2. Start the service

```bash
docker compose up -d
```

- Web console: <http://127.0.0.1:8632/> (published to host loopback only).
- Legacy rollback console: <http://127.0.0.1:8632/legacy> (kept for one migration cycle).
- REST docs: <http://127.0.0.1:8632/api/docs>.
- SQLite state, archive, Emby tree and MediaCrawler runtime live in the `media-sync-data` volume under `/data`.

After pulling an 0050-or-later revision, rebuild the image before restarting; `git pull` alone cannot replace the static bundle inside an existing image:

```bash
git pull --ff-only
sh scripts/fetch_mediacrawler.sh
docker compose build --no-cache
docker compose up -d
```

The console and API carry **no authentication** — publish the port to trusted networks only. To expose on your LAN, edit YOUR local `docker-compose.yml` (copied from the example) and change `127.0.0.1:8632:8632` to `192.168.x.x:8632:8632` at your own risk; the example template stays untouched so `git pull` never conflicts with your deployment configuration.

### 2.1 Preflight the in-container checkout (phase-B gate)

Health and readiness only prove the process and database. Before any login,
verify the embedded MediaCrawler checkout and the runtime toolchain:

```bash
docker compose exec media-sync   /app/.venv/bin/media-sync mediacrawler doctor --accept-license --json
```

And prove Chromium actually launches as the runtime user (not just that a path
exists):

```bash
docker compose exec media-sync   /opt/mediacrawler-venv/bin/python -c   'from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True); print(b.version); b.close()'
```

Both must pass before phase-B proceeds to QR login. Additionally, the build
manifest must record a real Chromium launch (a build-time launch failure only
prints `launch-failed` and does NOT fail the image build, so check it
explicitly):

```bash
docker compose exec media-sync grep -E '^(chromium|node|pnpm|web_lock_sha256):' /opt/BUILD-MANIFEST.txt
# Chromium must be a real version — it must NOT be "chromium: launch-failed".
# Node, pnpm and web_lock_sha256 prove which frontend build entered the image.
```

The console's 诊断 → 运行深度预检 repeats the runtime checks and shows
each checkout check, a stable `detail_code`, the actual Chromium version, and the
build-manifest version. After license acknowledgement, if it still reports a
code such as `checkout_invalid / tracked_blob_mismatch`, repair the locked
checkout in the image before trying QR login; failed preflight keeps QR login and
MediaCrawler-enabled workers disabled.

`license_digest_mismatch` on an older image means it still contains the pre-0050 qualification digest. Pull this revision, rerun the prefetch, and rebuild the image without cache. The current verifier compares the canonical LF content identity (accepting Git's LF/CRLF checkout forms) while still requiring the exact tracked blob, locked commit and clean worktree.

`runtime_invalid / runtime_imports_missing` on the first `4c6d0bf` image was caused by dereferencing the normal venv launcher symlink to the base Python. Pull the launcher repair and rebuild without cache. Keep `MEDIA_SYNC_MEDIACRAWLER_PYTHON_EXECUTABLE=/opt/mediacrawler-venv/bin/python`; do not replace it with the resolved base interpreter path.

## 3. QR login through the console

1. Open <http://127.0.0.1:8632/>. On the first visit in this browser, read and accept the personal-use/license and trusted-network notice once. The acknowledgement is stored in browser `localStorage`; ordinary refreshes do not ask again. Settings can reset it deliberately.
2. Open 平台账户 and add an account: pick the platform (e.g. `bili`), a display name and login method `扫码 QR`.
3. Click 扫码登录 on the account row. Console v2 automatically sends the MediaCrawler enable and license acknowledgement fields; the backend still runs the complete deep preflight before starting the child.
4. The dialog polls the QR image relayed from the headed login child running on the container's Xvfb display; scan it with the platform app within 180 seconds.
5. The dialog shows the login outcome; the account row should switch to `authenticated`.

If the QR does not appear within ~20 seconds, check `docker compose logs media-sync` — the most common causes are a missing checkout SHA mismatch (build arg) or an expired challenge (retry the login).

## 4. Subscribe and download

1. In 创作者订阅 pick the account, enter a stable creator ID (for Bilibili: the numeric UID), a display name and a small 单次上限 (e.g. 5).
2. Click 添加订阅, then 立即运行 to make it due.
3. Click 运行同步 — after the one-time browser acknowledgement, the console supplies both required MediaCrawler gate fields and the backend revalidates them — to run the creator crawl child and ingest content/assets.
4. Click 运行下载/导出 pipeline — this downloads media through the signed-locator refresh, archives under SHA-256 and publishes the Emby/Jellyfin tree.
5. Watch 调度任务 and 后台操作记录 for outcomes; 媒体资产 lists downloaded/verified assets; the library lands in the volume at `/data/library`.

For an unattended chain, enable the resident supervisor service instead of clicking: `docker compose --profile supervisor up -d`.

## 5. Point Emby/Jellyfin at the library

Mount or share the `media-sync-data` volume's `/data/library` path read-only to your media server and add it as a TV library. NFO, posters and episodes are deterministic per creator. If the media server needs a host bind mount, follow the compose comment and mount the same `/srv/media-sync/data` into media-sync. `MEDIA_SYNC_MEDIA_SERVER_LIBRARY_PATH` must be the **server-side absolute path returned by the Emby/Jellyfin API**, not a browser path or an interchangeable local path.

Stage 0054-A supports one immutable, environment-owned connection. Add the complete configuration below to `media-sync.environment` in your local `docker-compose.yml`; the six selectors must be either all present or all absent:

| Environment variable | Meaning |
| --- | --- |
| `MEDIA_SYNC_MEDIA_SERVER_PROVIDER` | `emby` or `jellyfin` |
| `MEDIA_SYNC_MEDIA_SERVER_BASE_URL` | Canonical HTTP(S) origin containing only scheme/host/port; no path, userinfo, query or fragment |
| `MEDIA_SYNC_MEDIA_SERVER_LIBRARY_ID` | The fixed Virtual Folder `ItemId` |
| `MEDIA_SYNC_MEDIA_SERVER_API_KEY_SECRET_REF` | An `env:`, confined relative `file:`, or `keyring:` reference, not the key value |
| `MEDIA_SYNC_MEDIA_SERVER_LIBRARY_PATH` | The exact server-side absolute path for that Virtual Folder |
| `MEDIA_SYNC_MEDIA_SERVER_ALLOWED_CIDRS` | Explicit IP/CIDR allowlist; every DNS answer must belong to it |
| `MEDIA_SYNC_MEDIA_SERVER_VERIFY_TLS` | Defaults to `true`; keep it enabled in production |
| `MEDIA_SYNC_MEDIA_SERVER_TIMEOUT_SECONDS` | 0.1–60 seconds; default 10 |
| `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED` | Shared server-side gate for probe/scan; defaults to `false` |

Inject the API-key value through the environment variable or secret file named by the reference; never commit it. The configuration API returns a hand-built redacted summary and never echoes the key, full secret reference, Library ID, server path, or network ranges. The connector disables environment proxies and redirects, validates every DNS answer and pins the actual connection IP while retaining the original Host/TLS SNI.

Start with `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED=false` and inspect the summary in Settings. After checking the origin, TLS posture, network-rule count and Library digest, open the gate and restart. Then use Library:

1. Select 检查媒体树 for an author to verify pages of the manifest authorized by the successful database publication chain. Inspection is read-only: it does not repair, delete, create an author lock, or expose a host path.
2. Select 测试连接. The backend calls only `GET /System/Info` and `GET /Library/VirtualFolders`, requiring an exact unique Library ID and path match.
3. Select 定向刷新. The backend calls only `POST /Items/{configured-library-id}/Refresh`; `404/405/501` fail closed and never fall back to global `/Library/Refresh`.
4. Inspect `media-server-probe` / `media-server-scan` under 调度任务 → 持久操作. Scan success means request accepted only. Once the application dispatch gate has been crossed, a timeout, disconnect, cancellation, or unexpected transport/response failure becomes terminal, non-retryable `media_server_scan_acceptance_unknown`; never submit another refresh automatically—check the server manually first.

If the service restarts after a remote Operation lost its lease, both an in-flight probe and an in-flight targeted scan are reconciled to `interrupted` because 0054-A persists no remote task identity. A probe may be retried manually; an interrupted targeted scan is exposed as non-retryable and requires server-side inspection before any new request.

`GET /api/v1/qualifications` separates local automated counts, implementation status and human qualification. This workspace has no real server credentials, so the implemented connection probe, Library discovery and targeted-refresh acceptance rows remain human `NOT_RUN`. Scan-completion polling and provider/path item lookup are `NOT_IMPLEMENTED` until a separately frozen 0054-B; authenticated playback evidence is 0055 work. Automatic post-export scanning is also `NOT_IMPLEMENTED` but has no frozen follow-up assignment. Every `NOT_IMPLEMENTED` capability has `human_status: null`—it must not be reported as human `NOT_RUN`, `FAIL` or `PASS`.

## 6. Verification checklist (record honestly)

| Row | Evidence |
| --- | --- |
| Real QR login (which platform/account) | console outcome + `login-status` showing `authenticated` |
| Creator crawl (which creator, item count) | scheduler job result + asset counts |
| Real media download | asset rows reaching `verified`/`archived`; SHA-256 files under `/data/archive` |
| Emby tree published | `/data/library` author directory listing |
| Real Emby/Jellyfin connection and Library discovery | successful `media-server-probe` record + server version; `NOT_RUN` if not exercised |
| Targeted refresh accepted by a real server | successful `media-server-scan` record; not scan completion; `NOT_RUN` if not exercised |
| Scan completion and provider/path item lookup | `NOT_IMPLEMENTED` in 0054-A; 0054-B remains to be frozen separately; no human status |
| Authenticated playback evidence | `NOT_IMPLEMENTED` in 0054-A; deferred to 0055; no human status |
| Automatic post-export scan | `NOT_IMPLEMENTED`; no frozen follow-up assignment and no human status |

Live evidence is limited to what actually ran; anything not exercised stays `NOT_RUN` per the project's truth rules.
