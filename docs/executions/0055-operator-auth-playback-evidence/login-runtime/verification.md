**English** | [中文](verification.zh.md)

# Login browser runtime verification

- Date: 2026-09-05
- Status: Full collected regression, focused and real local blank-browser checks passed; publication closeout in progress

Baseline inspection: `git status --short` empty; HEAD `db6c3c7`; triage and delivery priorities read. Previous evidence is diagnostic, not rebuilt-image or live-platform acceptance. Commands, failures, corrections and measured results will be appended after execution.

## Focused checks and corrections

- Environment interception: `.venv/Scripts/python.exe -m pytest tests/unit/test_mediacrawler_browser_environment.py -q` — 10 passed in 1.00s. Every login platform, creator specification and actual detail spawn retains the cache; synthetic operator/proxy/Python/debug/control values are denied. No real crawler subprocess runs in this test.
- Initial pinned-launch policy tests: 50 passed in 1.66s. Review identified that these exercised real launcher bodies but a synthetic factory. An additional 29 tests now execute verified pinned factory/main bodies and the real login/creator/detail entry wiring, including numeric Bilibili aid detail. Combined policy/wiring: 79 passed in 2.36s. Browser/network work is still fake.
- Final root focused union: `.venv/Scripts/python.exe -m pytest -q tests/contract/test_upstream_browser_policy.py tests/contract/test_browser_policy_wiring.py tests/unit/test_mediacrawler_browser_environment.py tests/unit/test_mediacrawler_browser_preflight.py tests/unit/test_login_browser_smoke_script.py tests/unit/test_login_preflight.py` — 134 passed in 4.96s.
- Existing login/detail/session/scheduler union — 205 passed in 184.35s. Earlier runs were stopped on synthetic fixture failures (missing factory/launcher or the removed private allowlist); they are not PASS. Fixtures were repaired without weakening the strict production hook.
- Bridge/CLI union — 152 passed, one Windows/POSIX skip in 101.64s. Its first broader run had 12 failures, 167 passes and one skip in 98.43s; all 12 were obsolete non-browser factory fixtures, repaired before the successful rerun.
- Entrypoint plus configuration-only checks — 77 passed in 33.70s using Git Bash, fake Xvfb/xdpyinfo and real coreutils timeout. Initial fixture PATH omissions were fixed. A real hung probe also revealed a shell-generated `Killed` diagnostic escaping the inner redirect; command-group redirection fixed it. Assertions verify early rejection, no migration and cleanup. This is not a Linux X server test.

## Real local blank-browser smoke

The project venv did not contain Playwright. A preliminary isolated `uv run --no-project --with playwright==1.62.0` lookup confirmed the existing bundled Chromium, but produced pending-connection cleanup warnings; this was only a path-discovery probe, not successful launch evidence. An ignored isolated runtime was then created from the project's Python 3.11.8, using cached packages:

```powershell
uv venv --python .venv/Scripts/python.exe .media-sync/login-browser-probe-venv
uv pip install --offline --python .media-sync/login-browser-probe-venv/Scripts/python.exe playwright==1.62.0
.venv/Scripts/python.exe scripts/check_login_browser.py --python .media-sync/login-browser-probe-venv/Scripts/python.exe
```

The actual new supervised headed-persistent path completed with exit 0 and only:

```json
{"ok": true, "browser": "bundled-chromium", "mode": "headed-persistent", "version": "151.0.7922.34", "live_qualification": "NOT_RUN"}
```

This used a disposable profile and no platform URL/account. It verifies Windows launch and ordinary cleanup with Playwright 1.62.0, not the Linux image or platform authentication. The probe runtime and raw test artifacts remain Git-ignored; no private profile or credential was retained in these records.

## Quality and packaging

- `.venv/Scripts/python.exe -m ruff check src scripts tests`: passed. Two import/blank-line formatting findings during integration were corrected.
- `.venv/Scripts/python.exe -m ruff format --check src scripts tests`: passed, 250 files.
- `.venv/Scripts/python.exe -m mypy src/media_sync`: passed, 109 source files.
- `.venv/Scripts/python.exe -m compileall -q src/media_sync scripts/check_login_browser.py`: passed.
- `.venv/Scripts/python.exe scripts/check_docs.py`: passed, 528 Markdown files; `scripts/check_upstreams.py`: both locked checkouts passed.
- Final `uv build --offline` succeeded: wheel 127 members, sdist 862 members. The wheel contains both new runtime modules; the sdist contains the smoke script and wiring tests. Exact-path scans exclude private Compose, `.env`, runtime/profile/tool-history directories and raw artifacts (the tracked `artifacts/README.md` is allowed).
- The first scan's broad patterns incorrectly rejected `.env.example` and `artifacts/README.md`. A subsequent content scan also found the pre-existing LAN example in the unchanged 2026-09-04 security/deployment plan. That historical tracked example was preserved and explicitly accounted for rather than claiming every IP was absent. The final scan passed with that exact legacy-file exception; no new deployed HTTPS authority or workstation-user path marker was found. The legacy file is unchanged from the frozen baseline.
- Web source is unchanged. The previous 114-test/Web build result is historical, not a rerun for this increment.

## Full regression and publication

The root full run `.venv/Scripts/python.exe -m pytest -q --junitxml=artifacts/login-runtime-python-full.xml` completed with **3264 passed, 22 skipped, one existing warning in 679.04s (11:19)**. It was started before the additional 29 wiring tests existed; those passed separately in the final 134-test union. Source behavior did not change after collection; subsequent integration formatting and documentation changes are not a new full-suite claim. Three skips are POSIX-specific on Windows; 19 are real PostgreSQL race cases without a configured server. The warning is the existing Starlette/httpx deprecation. No skipped gate is called passing.

Plan commit: `204655d`. Implementation/publication commit and remote verification are recorded after the available gates complete. No automatic deployment is performed.

## Operator handoff (not executed on the server)

Back up state first. Keep the working private Compose, exact HTTPS Origin, credential permissions and named volume. Do not copy the repository's loopback example over the configured deployment, and do not run `down -v`. In the existing deployment directory:

```bash
git pull --ff-only
docker-compose build media-sync
docker-compose run --rm --no-deps --entrypoint /app/.venv/bin/media-sync media-sync serve --check-config
docker-compose up -d --no-deps --force-recreate media-sync
docker-compose exec -T media-sync /app/.venv/bin/python /app/scripts/check_login_browser.py --python /opt/mediacrawler-venv/bin/python
```

Run each step only after the prior step succeeds. The lock did not change; rerun the existing upstream-prefetch script only if the prefetched directory is missing or a later revision changes the lock. If the supervisor profile is active, recreate it using the same new image. Share only the fixed preflight/smoke result, not configuration, credential files or raw platform logs. Then open accounts, preflight one account and let the operator scan its QR code; record the actual result before trying the remaining platforms.

The current Linux image/UID, X11 connectivity, reboot/restart/restore, QR display/scan, saved-session reuse, subscriptions/capture/download and Emby/Jellyfin playback remain unverified. No live PASS is created. Preflight covers ordinary success/failure/timeout/cancellation cleanup; a hard-killed POSIX parent is not given the full login runner's parent-death guarantee. Runtime failure classification after preflight and P1 evidence UI remain follow-up work.
