**English** | [中文](deployment.zh.md)

# Docker deployment and backend-authentication checkpoint

This guide deploys media-sync as a self-hosted container with the pinned MediaCrawler runtime. It was introduced by executions 0040/0041, updated by 0050, and expects a Linux host with Docker Compose v2. At the current execution 0055 checkpoint, the backend single-operator authentication boundary is implemented, but Console v2 and `/legacy` have not yet integrated its login, in-memory CSRF, logout, or expiry flow. The container can be started and its public health/readiness probes can be verified; do not claim the Web administration, QR-login, or media-server-control workflow usable yet.

## 1. Build

```bash
git clone <your-fork> media-sync && cd media-sync
sh scripts/fetch_mediacrawler.sh   # MANDATORY host-side prefetch of the locked upstream
cp docker-compose.example.yml docker-compose.yml   # your live copy is git-ignored
export MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE=/absolute/private/path/operator-credential.txt
docker compose build          # edit your copy first if you need different ports/paths
```

Before running any Compose command, create the referenced UTF-8 file outside the repository with mode `0600`. It contains only the dedicated operator credential (a final CR/LF is stripped): 16–1024 UTF-8 bytes, no control characters, and at least four distinct characters. Do not reuse a platform cookie or media-server key. The path supplied through `MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE` must be absolute and must remain available on every restart.

The example Compose file mounts that host file as the Docker secret `/run/secrets/operator_credential`, sets `MEDIA_SYNC_SECRET_FILE_DIR=/run/secrets`, and gives the application only the typed reference `file:operator_credential`. It also sets the exact browser origin `http://127.0.0.1:8632`. No credential value is committed to Git, copied into the image, or stored in SQLite.

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

- Public root shell: <http://127.0.0.1:8632/> (published to host loopback only). The current bundle has no operator-login shell, so it cannot operate protected APIs yet.
- `/legacy` and `/api/docs` are protected routes. They require an established browser session, but the checked-in clients do not yet establish one.
- `GET`/`HEAD /api/v1/health` and `/api/v1/ready` remain intentionally public for container probes; deep readiness and every business route require authentication.
- SQLite state, archive, Emby tree and MediaCrawler runtime live in the `media-sync-data` volume under `/data`.

After pulling an 0050-or-later revision, rebuild the image before restarting; `git pull` alone cannot replace the static bundle inside an existing image:

```bash
git pull --ff-only
sh scripts/fetch_mediacrawler.sh
docker compose build --no-cache
docker compose up -d
```

`media-sync serve` resolves the required credential and origin policy before calling Uvicorn. The container binds `0.0.0.0:8632` internally, while Compose publishes it only as host `127.0.0.1:8632`; the explicit loopback browser origin may therefore use HTTP. Every request still passes an exact raw `Host` gate, and forwarded Host/proto headers are ignored.

Do not expose the example by merely changing the port mapping to a LAN address. Every non-loopback browser origin must be an exact HTTPS origin in `MEDIA_SYNC_OPERATOR_ALLOWED_ORIGINS`, with TLS terminated by a reviewed reverse proxy that preserves the allowed `Host`; wildcard origins are forbidden. The application does not trust forwarding headers or provide public-network, multi-user, RBAC, SSO, or MFA support.

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

## 3. Web and QR-login status at this checkpoint

The backend now exposes strict operator login/session/logout contracts, an HttpOnly `SameSite=Strict` process-local cookie, and CSRF enforcement for cookie-authenticated unsafe requests. A successful login rotates the sole session; restart, logout, expiry, or credential change invalidates it. An optional, separately resolved Bearer credential may be configured for non-browser automation, but it cannot replace the browser-only confirmation authority planned later in 0055.

Console v2 currently calls protected APIs before establishing that session and does not attach the in-memory CSRF value to mutations. `/legacy` has the same limitation. Consequently the prior click-through QR instructions are suspended: receiving the public root HTML or a green healthcheck is not proof that the console works. Continue to use the CLI and, for already configured subscriptions, the resident supervisor. Resume browser QR qualification only after the Web login/CSRF checkpoint has its own verified closeout.

## 4. Subscribe and download

The subscription, scheduler, download, archive and Emby/Jellyfin publication backends remain available. At this checkpoint, administer them with the existing CLI rather than the incomplete Web authentication client. For an already configured unattended chain, enable the resident supervisor service with `docker compose --profile supervisor up -d`; it does not run `serve` and receives no operator credential. The resulting library still lands at `/data/library`.

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
| `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED` | Shared server-side gate for every media-server network action, including probe, both scan modes, and author lookup; defaults to `false` |

Inject the API-key value through the environment variable or secret file named by the reference; never commit it. The configuration API returns a hand-built redacted summary and never echoes the key, full secret reference, Library ID, server path, or network ranges. The connector disables environment proxies and redirects, validates every DNS answer and pins the actual connection IP while retaining the original Host/TLS SNI.

Start with `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED=false`. After checking the configured origin, TLS posture, network-rule count and Library digest through a reviewed authenticated client, open the gate and restart. The following backend behaviors are implemented, but their former Console v2 controls remain unavailable until the Web authentication integration lands:

1. Managed-tree inspection verifies pages of the manifest authorized by the successful database publication chain. It is read-only: it does not repair, delete, create an author lock, or expose a host path.
2. Connection probe calls only `GET /System/Info` and `GET /Library/VirtualFolders`, requiring an exact unique Library ID and path match.
3. Item inspection performs a read-only complete bounded lookup of the exact managed provider/path identity. `not_found` and one unique `matched` result are observations only; neither proves a refresh completed or that media plays.
4. The strict legacy `{}` refresh calls only `POST /Items/{configured-library-id}/Refresh`; `404/405/501` fail closed and never fall back to global `/Library/Refresh`. A successful Operation proves only a trusted 2xx acceptance.
5. Author refresh-and-verify accepts exactly `{"author_id":"<uuid>"}` after a current, complete tree inspection grants the action. It first requires a complete absent baseline. If the exact item already exists, it sends no POST and returns `media_server_scan_observation_precondition_failed`. Success requires one accepted refresh followed by two separated observations of the same unique item; it still does not prove provider task completion or playback.
6. Durable `media-server-probe` / `media-server-scan` Operations keep accepted, observed, acceptance-unknown and completion-unknown distinct. After transport entry, uncertain acceptance becomes non-retryable `media_server_scan_acceptance_unknown`. After trusted acceptance, an unproven observation becomes non-retryable `media_server_scan_completion_unknown` while retaining the accepted checkpoint. Never retry either ambiguity automatically.

On restart, an author observation in `preparing` or `baselining` is a pre-dispatch interruption; `dispatching` becomes acceptance unknown; `accepted` or `polling` becomes completion unknown with its accepted checkpoint preserved; only a valid persisted `observed` checkpoint may reconcile to success. Legacy targetless scans retain their conservative 0054-A recovery. A probe may be retried manually, but a scan ambiguity requires server-side inspection before any new request.

`GET /api/v1/qualifications` schema v2 separates local automated counts, implementation status and human qualification. This workspace has no real server credentials, so implemented connection probe, Library discovery, targeted-refresh acceptance, item lookup and post-refresh item observation all remain human `NOT_RUN`. `provider_task_completion` is `NOT_IMPLEMENTED` with reason `provider_api_unsupported`; authenticated playback evidence and automatic post-export scanning are also `NOT_IMPLEMENTED`. Every unimplemented capability has `human_status: null`—it must not be reported as human `NOT_RUN`, `FAIL` or `PASS`.

## 6. Verification checklist (record honestly)

| Row | Evidence |
| --- | --- |
| Real QR login (which platform/account) | Remains `NOT_RUN` at this checkpoint; record the authenticated console outcome plus `login-status` only after Web auth is delivered |
| Creator crawl (which creator, item count) | scheduler job result + asset counts |
| Real media download | asset rows reaching `verified`/`archived`; SHA-256 files under `/data/archive` |
| Emby tree published | `/data/library` author directory listing |
| Real Emby/Jellyfin connection and Library discovery | successful `media-server-probe` record + server version; `NOT_RUN` if not exercised |
| Targeted refresh accepted by a real server | successful `media-server-scan` record; not scan completion; `NOT_RUN` if not exercised |
| Exact provider/path item lookup on a real server | implemented in 0054-B; one complete lookup snapshot; `NOT_RUN` if not exercised |
| Post-refresh item observation on a real server | implemented in 0054-B; absent baseline + one accepted POST + the same unique item observed twice; `NOT_RUN` if not exercised |
| Provider task completion | `NOT_IMPLEMENTED` (`provider_api_unsupported`); no human status |
| Authenticated playback evidence | `NOT_IMPLEMENTED`; backend operator authentication alone is not playback evidence; no human status |
| Automatic post-export scan | `NOT_IMPLEMENTED`; no frozen follow-up assignment and no human status |

Live evidence is limited to what actually ran; anything not exercised stays `NOT_RUN` per the project's truth rules.
