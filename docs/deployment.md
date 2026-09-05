**English** | [中文](deployment.zh.md)

# Docker deployment and secure-console checkpoint

This guide deploys media-sync with the pinned MediaCrawler runtime on a Linux host with Docker Compose v2. The current 0055 secure console and startup preflight are implemented and locally verified, including synthetic-browser checks; exact status is in [verification](executions/0055-operator-auth-playback-evidence/secure-console/verification.md). Backend authentication, Web session/memory-only CSRF, logout/expiry and QR/SSE are wired; `/legacy` is a protected migration notice, while root without a v2 build offers only a build/CLI notice. The current Linux image, runtime-user permissions and live platform/media-server workflows remain NOT_RUN; neither historical 0050 image PASS nor public health success substitutes for them.

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

Before starting or upgrading, verify that the credential file is readable by the **final image's runtime user**. The Dockerfile uses UID 1000. With ordinary rootful Linux mappings, a root-owned `0600` source is not readable by that user: align only this file's owner or restricted read access with the effective runtime identity. Rootless/user-namespace mappings require host-specific checks. File-backed Compose secrets must not be assumed to remap uid/gid/mode; do not use world-readable permissions or recursive ownership changes.

After building, use this configuration-only preflight to bypass the normal entrypoint; it reads and validates configuration as the final image's runtime identity without printing credentials:

```bash
docker compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync serve --check-config
```

This Docker example has not run on the current Windows workstation (Docker is unavailable); it is not a Linux UID/mount-permission pass. `serve --check-config` shares normal serve's settings, credential, origin and bind-syntax validation and host/port overrides. Success emits only fixed safe status, with no app/database construction, directory creation, DNS lookup, bind or migration. It does not prove port availability, complete readiness or final-image qualification; actual mounted-secret readability still requires execution on the deployment host. The entrypoint now preflights `serve` (including `-- serve`) before Xvfb/`db init`; explicit `--check-config`/`--help` do not migrate. Normal startup still migrates after a successful preflight, so retain compatible pre-upgrade backups and qualify current-image startup/restart/restore separately.

```bash
docker compose up -d
```

- Public root login entry: <http://127.0.0.1:8632/> (host loopback only). Login success must be followed by session/CSRF bootstrap before private pages mount; eight exact SPA HTML deep links redirect unauthenticated navigation here with 303.
- `/legacy` is a protected migration notice, and `/api/docs` remains protected; neither reopens anonymous business access.
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

### 2.2 Match the real QR browser launch

The login-runtime repair makes login, creator and detail children share the approved browser environment, including `PLAYWRIGHT_BROWSERS_PATH`. All seven standard upstream browser launches explicitly use the installed Playwright Chromium; five upstream `channel="chrome"` selectors are adapted in memory, not by changing the locked checkout. A system Google Chrome installation is not required by this policy. Platform-specific network and anti-abuse behavior still needs live qualification.

The image now includes `xdpyinfo` and waits for a live Xvfb connection before database initialization. `xvfb_probe_unavailable`, `xvfb_start_failed` or `xvfb_ready_timeout` stop startup with a nonzero exit before migration. Preserve the operator configuration preflight and restricted secrets; changing Origin or copying browsers into a user's home is not the fix.

After rebuilding and recreating the service, run this credential-free check as its normal runtime UID:

```bash
docker compose exec -T media-sync /app/.venv/bin/python /app/scripts/check_login_browser.py --python /opt/mediacrawler-venv/bin/python
```

Success reports `ok: true`, `mode: headed-persistent`, a numeric browser version and `live_qualification: NOT_RUN`. The check launches an empty persistent browser using a disposable profile, visits no platform, reads no account profile and closes the browser tree before returning. Normal failures/timeouts are supervised; a forcibly killed POSIX parent is not covered by the preflight cleanup guarantee. The account login-preflight now performs the same headed check, while generic deep readiness stays headless. Neither blank-browser success nor public readiness proves that a QR code was displayed or an account authenticated.

For an existing deployment, retain the private Compose/HTTPS Origin, secret mount and named volume. Back up state before upgrading, then run `git pull --ff-only`, `docker compose build media-sync`, the configuration-only preflight above, and `docker compose up -d --no-deps --force-recreate media-sync`. Do not run `down -v`. A restart alone cannot load these source/image changes. If the optional supervisor is enabled, recreate it from the same new image too. See the [repair verification and handoff](executions/0055-operator-auth-playback-evidence/login-runtime/verification.md) for actual evidence and remaining live gates.

### 2.3 JavaScript startup dependency and actionable failures

The upstream entry point imports helpers that call PyExecJS before any browser launches. A blank Chromium PASS therefore does not prove the full login runtime is ready. The final image now installs Debian Node.js and records `javascript_runtime` in its manifest. The Python doctor (also used by login preflight and the final non-root build gate) executes a fixed JavaScript arithmetic probe; missing/broken execution fails safely with `runtime_javascript_unavailable`. Updating only Python source or restarting the old image cannot install this dependency: rebuild and recreate using the existing private Compose.

The QR relay now accepts upstream base64 strings and permitted PNG/JPEG/WebP base64 data URIs, normalizes them to bounded PNG, and never fetches a URL or opens an image viewer. Unsupported/malformed/oversized input is rejected silently. Legacy byte input remains bounded and unchanged. Normal relay failures remove the private temporary file; a hard-killed child may leave a QR temporary file in its private account directory, so this is not a complete hard-kill cleanup guarantee.

Accounts show the latest uniquely linked login result separately from readiness. An observed terminal Operation stops QR waiting even if image delivery fails or hangs. `operation_login_browser_launch_failed` identifies the actual launch boundary; legacy `operation_login_failed` remains unknown, not a diagnosis of network/cookies. Malformed, ambiguous or contradictory stored diagnostics are omitted. See [current verification](executions/0055-operator-auth-playback-evidence/login-diagnostics/verification.md) and [runtime follow-up](executions/0055-operator-auth-playback-evidence/login-runtime-followup/verification.md). Pasted-Cookie validation/save UI is requested follow-up and is not available in this checkpoint; do not paste Cookie values into chat.

## 3. Web and QR-login status at this checkpoint

The backend now exposes strict operator login/session/logout contracts, an HttpOnly `SameSite=Strict` process-local cookie, and CSRF enforcement for cookie-authenticated unsafe requests. A successful login rotates the sole session; restart, logout, expiry, or credential change invalidates it. An optional, separately resolved Bearer credential may be configured for non-browser automation, but it cannot replace the browser-only confirmation authority planned later in 0055.

Console v2 now implements serialized login/session/logout, memory-only CSRF, private-page gating, expiry/401 reset and QR/SSE session wiring; these have a passing [local synthetic-browser verification](executions/0055-operator-auth-playback-evidence/secure-console/verification.md) result, with video loading/decoding only (no play click), not live platform/media-server qualification. Login 200 alone does not grant private access: session bootstrap must succeed. Late old responses cannot restore old sessions, and writes are not automatically replayed. Onboarding supports “later” browsing without accepting the MediaCrawler license or starting a crawler. CLI/resident-supervisor workflows remain available; authorized live canaries do not require the P1 playback-confirmation UI.

## 4. Subscribe and download

Subscription, scheduler, download, archive and Emby/Jellyfin publication backends remain available. Web administration-session wiring is implemented with a passing [local synthetic-browser verification](executions/0055-operator-auth-playback-evidence/secure-console/verification.md) result; the CLI remains available for authorized workflows. An already configured unattended chain can use `docker compose --profile supervisor up -d`; that resident supervisor does not run serve or receive operator credentials. The resulting library remains at `/data/library`.

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
| `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED` | Shared server-side gate for every media-server network action, including probe, both scan modes, author lookup, and playback confirmation revalidation; defaults to `false` |

Inject the API-key value through the environment variable or secret file named by the reference; never commit it. The configuration API returns a hand-built redacted summary and never echoes the key, full secret reference, Library ID, server path, or network ranges. The connector disables environment proxies and redirects, validates every DNS answer and pins the actual connection IP while retaining the original Host/TLS SNI.

Start with `MEDIA_SYNC_MEDIA_SERVER_OPERATIONS_ENABLED=false`. After checking the configured origin, TLS posture, network-rule count and Library digest through a reviewed authenticated client, open the gate and restart. The following backend behaviors are implemented; Console v2 authentication wiring has passed local synthetic-browser verification, while the new playback-confirmation UI is outside this P0 slice:

1. Managed-tree inspection verifies pages of the manifest authorized by the successful database publication chain. It is read-only: it does not repair, delete, create an author lock, or expose a host path.
2. Connection probe calls only `GET /System/Info` and `GET /Library/VirtualFolders`, requiring an exact unique Library ID and path match.
3. Item inspection performs a read-only complete bounded lookup of the exact managed provider/path identity. `not_found` and one unique `matched` result are observations only; neither proves a refresh completed or that media plays.
4. The strict legacy `{}` refresh calls only `POST /Items/{configured-library-id}/Refresh`; `404/405/501` fail closed and never fall back to global `/Library/Refresh`. A successful Operation proves only a trusted 2xx acceptance.
5. Author refresh-and-verify accepts exactly `{"author_id":"<uuid>"}` after a current, complete tree inspection grants the action. It first requires a complete absent baseline. If the exact item already exists, it sends no POST and returns `media_server_scan_observation_precondition_failed`. Success requires one accepted refresh followed by two separated observations of the same unique item; it still does not prove provider task completion or playback.
6. Durable `media-server-probe` / `media-server-scan` Operations keep accepted, observed, acceptance-unknown and completion-unknown distinct. After transport entry, uncertain acceptance becomes non-retryable `media_server_scan_acceptance_unknown`. After trusted acceptance, an unproven observation becomes non-retryable `media_server_scan_completion_unknown` while retaining the accepted checkpoint. Never retry either ambiguity automatically.
7. Playback confirmation uses `POST /api/v1/media-server/playback-evidence`. It is not an automation endpoint: it requires a logged-in browser session, exact Origin and CSRF, and rejects Bearer-only or mixed Cookie/Authorization before handler work. The strict body contains only canonical `author_id` and the matched lookup's opaque `observation_fingerprint`; `Idempotency-Key`, selectors, paths, remote IDs, timestamps and notes are rejected. The server performs resolve → one complete unique lookup → resolve before a short create-or-replay transaction and returns no fingerprint or internal context digest. Playback-confirmation UI remains P1 work; this backend contract is not yet a ready console interaction and does not block CLI live canaries.
8. Authenticated Cookie or Bearer clients can read `GET /api/v1/media-server/playback-evidence/by-author/{author_id}?limit=20`. Only canonical author UUID and one optional limit (1–50) are accepted. One fresh stable complete lookup precedes read-only history/current queries. Current evidence is returned separately; history truncation is explicit. Remote uncertainty yields unavailable current authority and unknown history, never stale or PASS.

On restart, an author observation in `preparing` or `baselining` is a pre-dispatch interruption; `dispatching` becomes acceptance unknown; `accepted` or `polling` becomes completion unknown with its accepted checkpoint preserved; only a valid persisted `observed` checkpoint may reconcile to success. Legacy targetless scans retain their conservative 0054-A recovery. A probe may be retried manually, but a scan ambiguity requires server-side inspection before any new request.

`GET /api/v1/qualifications` now uses schema v3. It accepts only one optional canonical `author_id`; without it, playback scope is `not_requested` and no evidence or remote lookup runs. Playback is IMPLEMENTED and remains NOT_RUN without exact current attestation. With an author, PASS requires a current durable human confirmation and is explicitly scoped to that author. Existing automated counts/Operation results never confer a human PASS. All workspace live rows remain NOT_RUN. Provider task completion remains NOT_IMPLEMENTED (`provider_api_unsupported`) and automatic scanning remains NOT_IMPLEMENTED; these retain null human status.

## 6. Verification checklist (record honestly)

| Row | Evidence |
| --- | --- |
| Real QR login (which platform/account) | Still `NOT_RUN`; record the exact commit, CLI or verified Web flow and `login-status` only after authorized platform execution. Synthetic QR does not constitute live login |
| Creator crawl (which creator, item count) | scheduler job result + asset counts |
| Real media download | asset rows reaching `verified`/`archived`; SHA-256 files under `/data/archive` |
| Emby tree published | `/data/library` author directory listing |
| Real Emby/Jellyfin connection and Library discovery | successful `media-server-probe` record + server version; `NOT_RUN` if not exercised |
| Targeted refresh accepted by a real server | successful `media-server-scan` record; not scan completion; `NOT_RUN` if not exercised |
| Exact provider/path item lookup on a real server | implemented in 0054-B; one complete lookup snapshot; `NOT_RUN` if not exercised |
| Post-refresh item observation on a real server | implemented in 0054-B; absent baseline + one accepted POST + the same unique item observed twice; `NOT_RUN` if not exercised |
| Provider task completion | `NOT_IMPLEMENTED` (`provider_api_unsupported`); no human status |
| Browser-only playback confirmation backend/API | Implemented and offline-verified; no real Emby/Jellyfin playback was submitted, so it grants no live status |
| Playback-evidence current/stale/unknown projection and qualification | IMPLEMENTED in schema v3; NOT_RUN without selected-author exact current evidence. Web confirmation UI and real playback qualification remain pending |
| Automatic post-export scan | `NOT_IMPLEMENTED`; no frozen follow-up assignment and no human status |

Live evidence is limited to what actually ran; anything not exercised stays `NOT_RUN` per the project's truth rules.
