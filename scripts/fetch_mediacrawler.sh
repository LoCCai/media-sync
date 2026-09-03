#!/bin/sh
# Prefetch the pinned MediaCrawler checkout for hosts where the Docker BUILD
# container cannot reach github.com (mainland-China servers commonly reach
# PyPI but not GitHub from a clean container network).
#
# Clones the exact commit recorded in upstreams.lock.json into
# .mediacrawler-local/ (kept out of git via .gitignore; allowed into the
# Docker build context via .dockerignore). The Dockerfile prefers this
# pre-fetched checkout and verifies its SHA before use; when absent it falls
# back to the in-build git fetch.
#
# Usage:
#   sh scripts/fetch_mediacrawler.sh            # clone/verify into .mediacrawler-local
#   sh scripts/fetch_mediacrawler.sh --clean    # remove any previous copy first
#
# Env overrides (same meaning as the Dockerfile build args):
#   MEDIACRAWLER_REPO     git remote (default: the locked repository URL)
#   BUILD_HTTPS_PROXY     optional HTTPS proxy for this host-side clone
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

repo=${MEDIACRAWLER_REPO:-https://github.com/NanmiCoder/MediaCrawler.git}
# Probe for a real Python (some desktops ship a no-op python3 shim).
py=
for candidate in python3 python; do
    if "$candidate" -c 'import json' >/dev/null 2>&1; then
        py=$candidate
        break
    fi
done
if [ -z "$py" ]; then
    echo "no usable python3/python found to read upstreams.lock.json" >&2
    exit 1
fi
commit=$("$py" - "$root/upstreams.lock.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    lock = json.load(handle)
for upstream in lock["upstreams"]:
    if upstream["name"] == "MediaCrawler":
        print(upstream["commit"])
        break
else:
    raise SystemExit("MediaCrawler entry missing from upstreams.lock.json")
PY
)
target=".mediacrawler-local"

if [ "${1:-}" = "--clean" ]; then
    rm -rf "$target"
fi

if [ -d "$target/.git" ] && [ "$(git -C "$target" rev-parse HEAD)" = "$commit" ] \
    && [ -z "$(git -C "$target" status --porcelain)" ]; then
    echo "prefetched checkout already current at $commit"
    exit 0
fi

rm -rf "$target"
if [ -n "${BUILD_HTTPS_PROXY:-}" ]; then
    export HTTPS_PROXY="$BUILD_HTTPS_PROXY"
fi
git init --quiet "$target"
git -C "$target" remote add origin "$repo"
git -c http.version=HTTP/1.1 -C "$target" fetch --quiet --depth 1 origin "$commit"
git -C "$target" checkout --quiet FETCH_HEAD
actual=$(git -C "$target" rev-parse HEAD)
if [ "$actual" != "$commit" ]; then
    echo "fetched commit $actual does not match locked $commit" >&2
    exit 1
fi
if [ -n "$(git -C "$target" status --porcelain)" ]; then
    echo "prefetched checkout is not clean" >&2
    exit 1
fi
echo "prefetched $repo at $commit into $target/"
