**English** | [中文](verification.zh.md)

# Verification

Implementation revision: `165516a` (`feat(crawler): connect native sessions to subscriptions`). Planning baseline: `0b90aaa`.

## Final results

| Gate | Result | Evidence and boundary |
| --- | --- | --- |
| Focused adoption/WebUI/API tests | `PASS` | Six-file union: `83 passed, 1 warning in 19.37s`. Covers strict API schema, operator auth/CSRF, safe public errors, WebUI busy gate, copy/probe/replace/rollback, repository CAS, source retention and Zhihu child compatibility. The warning is the existing Starlette TestClient/httpx deprecation. |
| Adopted profile → scheduler | `PASS` | `1 passed, 59 deselected in 1.57s`. The exact Account profile reaches BridgeRequest and process spec as `saved_session`; Cookie resolution is unused; the sync Job and normalized ingestion succeed. |
| Existing delivery/NFO regression | `PASS` | `83 passed, 1 warning in 40.78s` across exact subscription delivery, platform output directories and the Emby export contract. No media-server provider is required by these tests. |
| Complete Python unit suite | `PASS` | Final run: `4683 passed, 3 skipped, 1 warning in 587.55s`. The three skips are existing Windows/POSIX qualification branches; the warning is the existing TestClient deprecation. |
| Corrected test failure | `FIXED` | The first complete run produced `4682 passed, 3 skipped` and one failure because the deny-by-default auth test still asserted 77 routes. The new protected adoption route makes 78; the exact count/name was updated, then the focused auth union passed `49 passed` and the complete suite above passed. |
| Complete media-sync Web suite | `PASS` | `26 files / 799 tests` passed. |
| Svelte/production Web build | `PASS` | `svelte-check` reported 0 errors and 0 warnings. Vite transformed 4,086 server and 4,095 client modules and produced the static build. |
| Frontend formatting | `PASS` | Repository-wide Prettier check reported all files formatted. |
| Python lint/format/type | `PASS` | Ruff check passed for `src tests`; Ruff format reported 396 files formatted; strict mypy reported no issues in 154 source files. |
| Locked upstreams | `PASS` | `scripts/check_upstreams.py`: two locked checkouts verified. A fresh `git fetch origin main` for MediaCrawler resolved the same locked/latest SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092`; `.upstream` was not modified. |
| Python packaging | `PASS` | `uv build` built `media_sync-0.1.0.tar.gz` and `media_sync-0.1.0-py3-none-any.whl` from the sdist in a temporary directory. Both new adoption modules are present in the artifacts. |
| Documentation links/whitespace | `PASS` | `scripts/check_docs.py`: `Documentation links OK (738 Markdown files checked).` `git diff --check` also passed immediately before the documentation commit. |
| Docker image for `165516a` | `NOT_RUN` | Docker is not available on this workstation; no local image/runtime claim is made. |
| Historical online 0072 `/crawler/` | Configuration gate observed | Before `165516a` deployment, the operator observed `license_acknowledgement_required` on the existing image. This proves that API license gate was closed, not that the native console or a platform login failed. It does not qualify the 0073 image; post-configuration access is still `NOT_RUN`. |
| Live QR/Cookie adoption and platform capture | `NOT_RUN` | No platform credential or live crawler was used in this local implementation verification. |
| Live CDN bytes, history completeness, later increment | `NOT_RUN` | Offline fixtures do not qualify these behaviors. |
| Emby/Jellyfin server scan/playback | `NOT_RUN` / optional | Directory/NFO generation is independent of a server connection; no server was contacted. |

## Commands run

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_api_mediacrawler_webui.py tests/unit/test_mediacrawler_webui_license_gate.py tests/unit/test_mediacrawler_webui.py tests/unit/test_mediacrawler_webui_child.py tests/unit/test_mediacrawler_profile_adoption_contract.py tests/integration/test_mediacrawler_profile_adoption.py -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_mediacrawler_scheduler_handler.py -k "adopted_webui_profile_is_the_exact_profile_used_by_scheduler" -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_exact_subscription_delivery.py tests/integration/test_pipeline_output_directories.py tests/contract/test_emby_export_contract.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/test_operator_auth_api.py tests/unit/test_api_mediacrawler_webui.py -q

pnpm --dir web test
pnpm --dir web run check
pnpm --dir web run build
pnpm --dir web run format:check

.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy --strict src/media_sync
.\.venv\Scripts\python.exe scripts/check_upstreams.py
.\.venv\Scripts\python.exe scripts/check_docs.py
git diff --check
uv build --out-dir <temporary-directory>
```

## Qualification conclusion

The deterministic implementation seam is qualified: native-WebUI profile snapshot → saved-session verification → Account publication → scheduler profile selection. This does not qualify a real platform login or download. The next authoritative evidence must come from the rebuilt Linux deployment, beginning with the corrected API license environment and one bounded Subscription canary.
