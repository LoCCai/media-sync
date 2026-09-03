#!/bin/sh
# media-sync container entrypoint: virtual display, idempotent schema, then CMD.
set -eu

# Headed QR-login children need an X display even inside a container.
Xvfb :99 -screen 0 1280x900x24 -nolisten tcp &
XVFB_PID=$!
trap 'kill "$XVFB_PID" 2>/dev/null || true' TERM INT EXIT

# Initialize/upgrade the SQLite schema before serving (idempotent).
/app/.venv/bin/media-sync db init

exec /app/.venv/bin/media-sync "$@"
