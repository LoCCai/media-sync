#!/usr/bin/env bash
set -Eeuo pipefail

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif docker-compose version >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "docker compose / docker-compose not found" >&2
  exit 1
fi

SERVICE="${1:-media-sync}"
CHECKOUT="/app/.upstream/MediaCrawler"
LOCK="/app/upstreams.lock.json"

echo "== compose service =="
"${COMPOSE[@]}" ps "$SERVICE"

echo
echo "== exact Python verifier exception =="
set +e
"${COMPOSE[@]}" exec -T "$SERVICE" /app/.venv/bin/python - <<'PY'
from pathlib import Path
from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout

try:
    result = verify_mediacrawler_checkout(
        Path("/app/upstreams.lock.json"),
        license_acknowledged=True,
    )
    print("CHECKOUT_OK")
    print(result)
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")
    raise
PY
VERIFY_RC=$?
set -e

echo
echo "== manual checkout checks =="
"${COMPOSE[@]}" exec -T "$SERVICE" sh -lc '
set +e
c=/app/.upstream/MediaCrawler

echo "-- identity --"
id
pwd

echo "-- paths --"
ls -ld /app /app/.upstream "$c" "$c/.git" 2>&1
ls -l "$c/main.py" "$c/config/__init__.py" "$c/LICENSE" 2>&1

echo "-- git root/revision --"
git -C "$c" rev-parse --show-toplevel 2>&1
git -C "$c" rev-parse HEAD 2>&1

echo "-- repository config --"
git -C "$c" remote get-url origin 2>&1
git -C "$c" config --show-origin --get core.autocrlf 2>&1

echo "-- worktree default --"
git -C "$c" status --porcelain --untracked-files=all 2>&1

echo "-- worktree with production autocrlf rule --"
git -C "$c" -c core.autocrlf=input status --porcelain --untracked-files=all 2>&1

echo "-- license --"
head -n1 "$c/LICENSE" 2>&1
echo "raw digest (diagnostic only):"
sha256sum "$c/LICENSE" 2>&1
echo "canonical LF qualification digest:"
/app/.venv/bin/python -c "from pathlib import Path; import hashlib; value=Path(\"$c/LICENSE\").read_bytes().replace(b\"\\r\\n\", b\"\\n\"); assert b\"\\r\" not in value; print(hashlib.sha256(value).hexdigest())" 2>&1
echo "expected canonical: aeff21de8609bec9d6e939bbbba7c2914ae0a6e7c9470ea7945c03f7d17a2a33"

for f in LICENSE main.py config/__init__.py; do
  echo "-- tracked blob: $f --"
  git -C "$c" ls-files --stage -- "$f" 2>&1
  echo "HEAD blob:"
  git -C "$c" rev-parse "HEAD:$f" 2>&1
  echo "working blob under core.autocrlf=input:"
  git -C "$c" -c core.autocrlf=input hash-object --path="$f" -- "$f" 2>&1
done

echo "-- build manifest --"
sed -n "1,120p" /opt/BUILD-MANIFEST.txt 2>&1
'

echo
echo "== runtime browser probe =="
"${COMPOSE[@]}" exec -T "$SERVICE" /opt/mediacrawler-venv/bin/python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    print("CHROMIUM_OK", browser.version)
    browser.close()
PY

echo
echo "Verifier exit code: ${VERIFY_RC}"
echo "Paste the exact CheckoutValidationError line and the manual-check section into the 0047-d1 record."
exit "$VERIFY_RC"
