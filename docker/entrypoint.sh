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

# Headed QR-login children need an X display even inside a container. Probe an
# actual X11 connection: /tmp may be tmpfs and Linux can use abstract sockets,
# so neither a filesystem socket nor Xvfb's initial stderr proves readiness.
if ! command -v timeout >/dev/null 2>&1 || ! command -v xdpyinfo >/dev/null 2>&1 \
    || ! command -v sleep >/dev/null 2>&1; then
    printf '%s\n' '{"detail":"xvfb_probe_unavailable"}' >&2
    exit 1
fi
DISPLAY=:99
export DISPLAY
Xvfb :99 -screen 0 1280x900x24 -nolisten tcp >/dev/null 2>&1 &
XVFB_PID=$!
trap 'kill "$XVFB_PID" 2>/dev/null || true; kill -KILL "$XVFB_PID" 2>/dev/null || true; wait "$XVFB_PID" 2>/dev/null || true' EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

XVFB_READY_ATTEMPTS=10
XVFB_READY=0
while [ "$XVFB_READY_ATTEMPTS" -gt 0 ]; do
    if ! kill -0 "$XVFB_PID" 2>/dev/null; then
        printf '%s\n' '{"detail":"xvfb_start_failed"}' >&2
        exit 1
    fi
    # Each handshake is bounded independently, including forced termination
    # of an unresponsive probe. Re-check our process after a successful probe
    # to catch a child that exited while the connection probe was running.
    if { timeout --kill-after=1s 1s xdpyinfo -display "$DISPLAY"; } >/dev/null 2>&1; then
        if ! kill -0 "$XVFB_PID" 2>/dev/null; then
            printf '%s\n' '{"detail":"xvfb_start_failed"}' >&2
            exit 1
        fi
        XVFB_READY=1
        break
    fi
    XVFB_READY_ATTEMPTS=$((XVFB_READY_ATTEMPTS - 1))
    if [ "$XVFB_READY_ATTEMPTS" -gt 0 ]; then
        sleep 0.2
    fi
done
if [ "$XVFB_READY" -ne 1 ]; then
    printf '%s\n' '{"detail":"xvfb_ready_timeout"}' >&2
    exit 1
fi

# Initialize/upgrade the SQLite schema before serving (idempotent).
/app/.venv/bin/media-sync db init

exec /app/.venv/bin/media-sync "$@"
