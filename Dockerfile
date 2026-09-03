# syntax=docker/dockerfile:1
# media-sync deployment image (personal/self-hosted use).
#
# Builds both layers in one image:
#   1. media-sync itself (uv-managed project venv at /app/.venv)
#   2. the pinned MediaCrawler checkout at /opt/mediacrawler with its own
#      venv, Playwright and Chromium, so the license-gated bridge children
#      (QR login / creator crawl) run against the exact locked SHA.
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
FROM ${BASE_IMAGE} AS base

# Mirror overrides for mainland-China builds; defaults stay on official
# sources so the image remains reproducible anywhere. The example compose file
# passes Aliyun/npmmirror values by default — comment them out abroad.
#   APT_MIRROR:      host replacing deb.debian.org in the apt sources
#   PYPI_INDEX:      PyPI simple index used by pip and uv
#   PLAYWRIGHT_DOWNLOAD_HOST: browser binary mirror host
ARG APT_MIRROR=deb.debian.org
ARG PYPI_INDEX=https://pypi.org/simple
ARG PLAYWRIGHT_DOWNLOAD_HOST=""

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PYPI_INDEX} \
    UV_LINK_MODE=copy \
    UV_DEFAULT_INDEX=${PYPI_INDEX} \
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
COPY scripts ./scripts
COPY alembic.ini ./
RUN pip install --no-cache-dir uv==0.12.9 \
    && uv sync --locked --no-dev \
    && uv cache clean

# ------------------------------------------------------- pinned MediaCrawler
# The checkout fetches ONLY the locked commit snapshot (--depth 1) over forced
# HTTP/1.1: mainland-China links to GitHub regularly fail with "curl 16 Error
# in the HTTP2 framing layer" on full clones. If direct access still fails,
# override MEDIACRAWLER_REPO with a mirror prefix or set BUILD_HTTPS_PROXY.
ARG MEDIACRAWLER_REPO=https://github.com/NanmiCoder/MediaCrawler.git
ARG MEDIACRAWLER_COMMIT=d6f7c5bb906b6dac40ddf343ef9e26438a3de092
ARG BUILD_HTTPS_PROXY=""
RUN if [ -n "${BUILD_HTTPS_PROXY}" ]; then export HTTPS_PROXY="${BUILD_HTTPS_PROXY}"; fi \
    && git init --quiet /opt/mediacrawler \
    && git -C /opt/mediacrawler remote add origin "${MEDIACRAWLER_REPO}" \
    && git -c http.version=HTTP/1.1 -C /opt/mediacrawler fetch --quiet --depth 1 origin "${MEDIACRAWLER_COMMIT}" \
    && git -C /opt/mediacrawler checkout --quiet FETCH_HEAD \
    && git -C /opt/mediacrawler rev-parse HEAD | grep -qx "${MEDIACRAWLER_COMMIT}" \
    && rm -rf /opt/mediacrawler/.git
# The upstream venv installs from a hashed lock compiled from the pinned
# checkout's requirements.txt (docker/mediacrawler-requirements.lock), so the
# same source SHA always builds the same dependency set; playwright is thereby
# pinned too (1.62.0), which pins the Chromium revision it downloads.
COPY docker/mediacrawler-requirements.lock /tmp/mediacrawler-requirements.lock
RUN python -m venv /opt/mediacrawler-venv \
    && /opt/mediacrawler-venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/mediacrawler-requirements.lock \
    && if [ -n "${PLAYWRIGHT_DOWNLOAD_HOST}" ]; then \
           export PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST}"; \
       fi \
    && /opt/mediacrawler-venv/bin/python -m playwright install --with-deps chromium \
    && rm -f /tmp/mediacrawler-requirements.lock

# Build manifest: record every runtime toolchain version baked into this
# image (review §5 reproducibility). Full SBOM generation stays deferred.
RUN { echo "python: $(python --version)"; \
      echo "uv: $(uv --version)"; \
      echo "ffmpeg: $(ffmpeg -version | head -n1)"; \
      echo "playwright: $(/opt/mediacrawler-venv/bin/python -m playwright --version)"; \
      echo "chromium: $(/opt/mediacrawler-venv/bin/python -c 'from playwright.sync_api import sync_playwright; p = sync_playwright().start(); print(p.chromium.executable_path); p.stop()' || echo unknown)"; \
      echo "--- app venv ---"; /app/.venv/bin/python -m pip freeze 2>/dev/null || true; \
      echo "--- mediacrawler venv ---"; /opt/mediacrawler-venv/bin/python -m pip freeze; \
    } > /opt/BUILD-MANIFEST.txt

# --------------------------------------------------------------- runtime env
# Data roots are volumes; the API must bind 0.0.0.0 inside the container
# network namespace (compose publishes it to a trusted host network only).
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
RUN chmod +x /usr/local/bin/media-sync-entrypoint \
    && mkdir -p /data/state /data/archive /data/library /data/jobs /data/mediacrawler \
    && useradd --system --create-home --uid 1000 mediasync \
    && chown -R mediasync:mediasync /data /app

USER mediasync
WORKDIR /app
EXPOSE 8632
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8632/api/v1/health || exit 1

ENTRYPOINT ["/usr/local/bin/media-sync-entrypoint"]
CMD ["serve"]
