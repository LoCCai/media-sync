# syntax=docker/dockerfile:1
# media-sync deployment image (personal/self-hosted use).
#
# Builds both layers in one image:
#   1. media-sync itself (uv-managed project venv at /app/.venv)
#   2. the pinned MediaCrawler checkout at /app/.upstream/MediaCrawler (the
#      exact lock-relative path) with its own venv, Playwright and Chromium,
#      so the license-gated bridge children (QR login / creator crawl) run
#      against the exact locked SHA.
#
# The upstream checkout is cloned at the SHA recorded in upstreams.lock.json
# for the operator's own deployment (non-commercial learning license). This
# image is for personal use and must not be published or redistributed.
#
# Build:   docker build -t media-sync:local .
# Run:     docker compose up -d

# Reproducibility: override BASE_IMAGE with a digest-pinned reference on the
# build host and commit the value you used, e.g.
#   docker buildx imagetools inspect python:3.13-slim-bookworm   # copy the digest
#   docker build --build-arg BASE_IMAGE=python:3.13-slim-bookworm@sha256:<digest> ...
# Debian package versions remain unpinned (apt snapshots are deferred); the
# build manifest below records what actually got installed.
ARG BASE_IMAGE=python:3.13-slim-bookworm
ARG NODE_IMAGE=node:24-bookworm-slim
ARG NPM_REGISTRY=https://registry.npmjs.org

# ----------------------------------------------------------- Web Console v2
# Build the SvelteKit SPA separately. Node.js and pnpm never enter the final
# runtime image; only fingerprinted static output is copied into the package.
FROM ${NODE_IMAGE} AS web-build
ARG NPM_REGISTRY
WORKDIR /web
RUN npm config set registry "${NPM_REGISTRY}" \
    && npm install --global pnpm@11.19.0
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm check \
    && pnpm test \
    && pnpm build \
    && { echo "node: $(node --version)"; \
         echo "pnpm: $(pnpm --version)"; \
         echo "web_lock_sha256: $(sha256sum pnpm-lock.yaml | cut -d' ' -f1)"; \
       } > /web/WEB-BUILD-MANIFEST.txt

FROM ${BASE_IMAGE} AS base
# Re-declare so the build manifest can record the (possibly digest-pinned) base.
ARG BASE_IMAGE

# Mirror overrides for mainland-China builds; defaults stay on official
# sources so the image remains reproducible anywhere. The example compose file
# passes Aliyun/npmmirror values by default — comment them out abroad.
#   APT_MIRROR:      host replacing deb.debian.org in the apt sources
#   PYPI_INDEX:      PyPI simple index used by the PIP steps only (installing
#                    uv itself and the mediacrawler venv). It must NOT be
#                    applied to `uv sync`: uv records the registry it resolved
#                    against inside uv.lock, so validating the committed lock
#                    against a mirror rewrites every source URL and `--locked`
#                    fails (phase-B finding d2). uv therefore always resolves
#                    against pypi.org; set BUILD_HTTPS_PROXY if that is slow.
#   PLAYWRIGHT_DOWNLOAD_HOST: browser binary mirror host
ARG APT_MIRROR=deb.debian.org
ARG PYPI_INDEX=https://pypi.org/simple
ARG PLAYWRIGHT_DOWNLOAD_HOST=""
ARG BUILD_HTTPS_PROXY=""

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PYPI_INDEX} \
    UV_LINK_MODE=copy \
    DEBIAN_FRONTEND=noninteractive

# ffmpeg/ffprobe for media probing and stream-copy, plus Xvfb and fonts so the
# headed QR-login browser can run on a virtual container display.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    sed -i "s|deb\.debian\.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    sed -i "s|deb\.debian\.org|${APT_MIRROR}|g" /etc/apt/sources.list 2>/dev/null || true; \
    apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      xvfb \
      xauth \
      fonts-noto-cjk \
      fonts-liberation \
      ca-certificates \
      curl \
      git \
      procps \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------- media-sync
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY --from=web-build /web/build ./src/media_sync/interfaces/static/console-v2
COPY --from=web-build /web/WEB-BUILD-MANIFEST.txt /tmp/WEB-BUILD-MANIFEST.txt
COPY scripts ./scripts
COPY alembic.ini ./
# Pin uv to the exact version that authored uv.lock (revision 3). A newer uv
# rewrites the lock format and refuses `--locked` (phase-B finding d1). Bump
# this ONLY together with regenerating and re-validating uv.lock. uv resolves
# against pypi.org (never a mirror — see PYPI_INDEX above, finding d2); use
# BUILD_HTTPS_PROXY here too when that is slow.
RUN if [ -n "${BUILD_HTTPS_PROXY}" ]; then export HTTPS_PROXY="${BUILD_HTTPS_PROXY}"; fi \
    && pip install --no-cache-dir uv==0.9.18 \
    && uv sync --locked --no-dev \
    && uv cache clean

# ------------------------------------------------------- pinned MediaCrawler
# The checkout lives at the exact lock-relative path: upstreams.lock.json
# records local_path ".upstream/MediaCrawler", which the verifier resolves
# against the lock file's directory (/app), so the container checkout MUST be
# /app/.upstream/MediaCrawler with its .git directory intact — the verifier
# requires a git repository at the locked commit with a clean tracked tree.
#
# The checkout is PREFETCHED HOST-SIDE (phase-B finding d3: build containers
# on mainland hosts cannot reach github.com, while the host itself can — it
# cloned this repository). MANDATORY before `docker compose build`:
#
#   sh scripts/fetch_mediacrawler.sh          # or: BUILD_HTTPS_PROXY=... sh ...
#
# It clones the locked commit into .mediacrawler-local/ (git-ignored, allowed
# into the build context). The step below verifies HEAD equals the locked
# commit, requires a clean tree, and relocates it — the build itself needs
# ZERO github.com access.
ARG MEDIACRAWLER_REPO=https://github.com/NanmiCoder/MediaCrawler.git
ARG MEDIACRAWLER_COMMIT=d6f7c5bb906b6dac40ddf343ef9e26438a3de092
COPY .mediacrawler-local/ /tmp/mediacrawler-prefetch/
RUN mkdir -p /app/.upstream \
    && test -d /tmp/mediacrawler-prefetch/.git \
    && [ "$(git -C /tmp/mediacrawler-prefetch rev-parse HEAD)" = "${MEDIACRAWLER_COMMIT}" ] \
    && [ -z "$(git -C /tmp/mediacrawler-prefetch status --porcelain)" ] \
    && mv /tmp/mediacrawler-prefetch /app/.upstream/MediaCrawler \
    && git -C /app/.upstream/MediaCrawler remote set-url origin "${MEDIACRAWLER_REPO}" \
    && git -C /app/.upstream/MediaCrawler rev-parse HEAD | grep -qx "${MEDIACRAWLER_COMMIT}"
# The upstream venv installs from a hashed lock compiled from the pinned
# checkout's requirements.txt (docker/mediacrawler-requirements.lock), so the
# same source SHA always builds the same dependency set; playwright is thereby
# pinned too (1.62.0), which pins the Chromium revision it downloads.
# Browsers install into a fixed shared path so the root build user and the
# mediasync runtime user resolve the same cache; the runtime user must be
# able to launch Chromium, which phase B verifies in-container.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
COPY docker/mediacrawler-requirements.lock /tmp/mediacrawler-requirements.lock
RUN python -m venv /opt/mediacrawler-venv \
    && /opt/mediacrawler-venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/mediacrawler-requirements.lock \
    && if [ -n "${PLAYWRIGHT_DOWNLOAD_HOST}" ]; then \
           export PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST}"; \
       fi \
    && /opt/mediacrawler-venv/bin/python -m playwright install --with-deps chromium \
    && rm -f /tmp/mediacrawler-requirements.lock

# Runtime user owns the data roots, the app tree and the shared browser cache.
RUN useradd --system --create-home --uid 1000 mediasync \
    && mkdir -p /data/state /data/archive /data/library /data/jobs /data/mediacrawler \
    && chown -R mediasync:mediasync /data /app /opt/ms-playwright

# Build manifest: record every runtime toolchain version baked into this
# image (review §5 reproducibility). The Chromium entry launches the browser
# as the mediasync user and records the real version, not a derived path.
# BuildKit RUN containers often expose a small /dev/shm, so this build-only
# probe uses Chromium's disk-backed shared-memory fallback. The deep readiness
# endpoint still performs a normal runtime-user launch in the running container.
# Full SBOM generation stays deferred.
RUN { echo "python: $(python --version)"; \
      echo "uv: $(uv --version)"; \
      echo "ffmpeg: $(ffmpeg -version | head -n1)"; \
      echo "playwright: $(/opt/mediacrawler-venv/bin/python -m playwright --version)"; \
      echo "chromium: $(su mediasync -s /bin/sh -c '/opt/mediacrawler-venv/bin/python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True, args=[\"--disable-dev-shm-usage\"]); print(b.version); b.close(); p.stop()"' || echo launch-failed)"; \
      echo "base_image: ${BASE_IMAGE}"; \
      cat /tmp/WEB-BUILD-MANIFEST.txt; \
      echo "--- app venv ---"; /app/.venv/bin/python -m pip freeze 2>/dev/null || uv --project /app pip freeze 2>/dev/null || true; \
      echo "--- mediacrawler venv ---"; /opt/mediacrawler-venv/bin/python -m pip freeze; \
    } > /opt/BUILD-MANIFEST.txt \
    && rm -f /tmp/WEB-BUILD-MANIFEST.txt

# --------------------------------------------------------------- runtime env
# Data roots are volumes; the API binds 0.0.0.0 inside the container network
# namespace. Deployments must inject operator auth and an exact browser origin;
# the example compose publishes only to host loopback.
ENV MEDIA_SYNC_STATE_DIR=/data/state \
    MEDIA_SYNC_ARCHIVE_DIR=/data/archive \
    MEDIA_SYNC_EXPORT_DIR=/data/library \
    MEDIA_SYNC_JOB_DIR=/data/jobs \
    MEDIA_SYNC_MEDIACRAWLER_PYTHON_EXECUTABLE=/opt/mediacrawler-venv/bin/python \
    MEDIA_SYNC_MEDIACRAWLER_RUNTIME_DIR=/data/mediacrawler \
    MEDIA_SYNC_MEDIACRAWLER_LOCK_PATH=/app/upstreams.lock.json \
    MEDIA_SYNC_API_HOST=0.0.0.0 \
    MEDIA_SYNC_API_PORT=8632 \
    DISPLAY=:99

COPY upstreams.lock.json /app/upstreams.lock.json
COPY docker/entrypoint.sh /usr/local/bin/media-sync-entrypoint
# Exercise the exact configured venv launcher through the application verifier.
# This catches dependency drift and accidental symlink dereferencing while the
# image is still being built.
RUN chmod +x /usr/local/bin/media-sync-entrypoint \
    && chown mediasync:mediasync /app/upstreams.lock.json /usr/local/bin/media-sync-entrypoint \
    && su mediasync -s /bin/sh -c \
      '/app/.venv/bin/media-sync mediacrawler doctor --accept-license --json'

USER mediasync
WORKDIR /app
EXPOSE 8632
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8632/api/v1/health || exit 1

ENTRYPOINT ["/usr/local/bin/media-sync-entrypoint"]
CMD ["serve"]
