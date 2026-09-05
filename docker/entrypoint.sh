#!/bin/sh
# media-sync container entrypoint: read-only serve preflight before startup work.
set -eu

# Typer accepts one global option terminator before its command. Normalize it
# before dispatch so `-- serve` cannot bypass the read-only serve preflight.
if [ "${1:-}" = "--" ] && [ "${2:-}" = "serve" ]; then
    shift
fi

# Help never initializes runtime state, including help for non-serve commands.
for argument do
    if [ "$argument" = "--help" ]; then
        exec /app/.venv/bin/media-sync "$@"
    fi
done

if [ "${1:-}" = "serve" ]; then
    for argument do
        if [ "$argument" = "--check-config" ]; then
            exec /app/.venv/bin/media-sync "$@"
        fi
    done
    # Reuse serve's parser, overrides and secret/origin validation as this UID.
    # set -e prevents Xvfb and migrations when configuration validation fails.
    /app/.venv/bin/media-sync "$@" --check-config
fi

# Headed QR-login children need an X display even inside a container.
Xvfb :99 -screen 0 1280x900x24 -nolisten tcp &
XVFB_PID=$!
trap 'kill "$XVFB_PID" 2>/dev/null || true' TERM INT EXIT

# Initialize/upgrade the SQLite schema before serving (idempotent).
/app/.venv/bin/media-sync db init

exec /app/.venv/bin/media-sync "$@"
