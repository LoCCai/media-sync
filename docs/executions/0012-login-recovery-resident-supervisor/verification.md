**English** | [中文](verification.zh.md)

# Execution 0012 verification

- Status: Offline implementation and closeout gates pass
- Environment: Windows, local workspace, Python environment resolved by `uv`
- Evidence date: 2026-08-31
- Plan commit: `4494226`
- Implementation commit: `28655f8`

## Starting baseline

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Existing generic hard-parent-death plus login normal timeout/cancellation | `uv run pytest -q tests/contract/test_mediacrawler_supervision.py::test_hard_parent_death_stops_real_child_tree_and_allows_safe_recovery tests/contract/test_mediacrawler_login.py::test_timeout_and_cancellation_join_the_complete_process_tree` | `0` | `PASS` — `3 passed in 8.15s` |

The baseline was predecessor-only evidence. Every delivered claim below comes from post-implementation tests and does not reinterpret that historical run.

## Focused implementation evidence

| Scope | Command | Exit | Result |
| --- | --- | ---: | --- |
| Exact post-result hard-parent-death guardian window on Windows | `uv run pytest -q tests/contract/test_mediacrawler_login.py::test_hard_parent_death_after_result_frame_stops_guardian_tree_before_lock_release` | `0` | `PASS` — `1 passed in 4.49s` |
| Login unit and contract boundary | `uv run pytest -q tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py` | `0` | `PASS` — `61 passed in 43.66s` |
| Login plus shared MediaCrawler bridge/supervision regression | `uv run pytest -q tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py tests/contract/test_mediacrawler_supervision.py tests/contract/test_mediacrawler_bridge.py` | `0` | `PASS` — `149 passed, 1 skipped in 117.16s` |
| Deadline recovery, cursor fairness, login application, CLI and supervisor | `uv run pytest -q tests/integration/test_login_session_repository.py tests/integration/test_mediacrawler_login_application.py tests/unit/test_cli_login.py tests/unit/test_scheduler_supervisor.py tests/integration/test_scheduler_supervisor.py` | `0` | `PASS` — `127 passed in 14.83s` |
| Supervisor repeated-cancellation unit races | `uv run pytest -q tests/unit/test_scheduler_supervisor.py` | `0` | `PASS` — `32 passed in 0.71s` |
| Supervisor integration, CLI and login-focused composition | `uv run pytest -q tests/unit/test_scheduler_supervisor.py tests/integration/test_scheduler_supervisor.py tests/unit/test_cli_supervisor.py tests/unit/test_cli_login.py` | `0` | `PASS` — `50 passed in 3.25s` |
| Root integrated execution 0012 gate | `uv run pytest -q tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py tests/contract/test_mediacrawler_supervision.py tests/contract/test_mediacrawler_bridge.py tests/integration/test_login_session_repository.py tests/integration/test_mediacrawler_login_application.py tests/unit/test_cli_login.py tests/unit/test_scheduler_supervisor.py tests/integration/test_scheduler_supervisor.py tests/unit/test_cli_supervisor.py` | `0` | `PASS` — `283 passed, 1 skipped in 129.24s` |

The one skip is `tests/contract/test_mediacrawler_supervision.py:556`: POSIX mode bits are not the Windows ACL boundary. It is environment-inapplicable, not a failed feature.

The focused evidence proves: exact request/result length framing; START gating; CANCEL/EOF/malformed-control closure; Windows outer and child-owned Job containment; POSIX owned process-group containment; the result-read/pre-control-close guardian window; account-lock retention until complete-tree exit; exact deadline/CAS recovery and rollback; bounded rotating-cursor fairness; one-cycle Fake durable sync-to-pipeline success; stop-before-later-claim behavior; subscription cancel/join; pipeline heartbeat drain; and repeated task-cancellation resilience for both joins.

## Complete root closeout gates

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Complete offline suite | `uv run pytest -q` | `0` | `PASS` — `1156 passed, 1 skipped in 256.84s` |
| Lint | `uv run ruff check .` | `0` | `PASS` — `All checks passed!` |
| Format | `uv run ruff format --check .` | `0` | `PASS` — `207 files already formatted` |
| Strict typing | `uv run mypy src/media_sync` | `0` | `PASS` — `Success: no issues found in 77 source files` |
| Documentation links | `uv run python scripts/check_docs.py` | `0` | `PASS` — `Documentation links OK (64 Markdown files checked)` |
| Pinned upstreams | `uv run python scripts/check_upstreams.py` | `0` | `PASS` — `Upstreams OK (2 locked checkouts verified)` |
| Source distribution and wheel | `uv build` | `0` | `PASS` — built `media_sync-0.1.0.tar.gz` and `media_sync-0.1.0-py3-none-any.whl` |
| Patch whitespace | `git diff --check` | `0` | `PASS` — no output |

No coverage command ran, so execution 0012 makes no coverage claim. The Fake scheduler-to-pipeline integration uses local SQLite and deterministic handlers; it does not prove real CDN traffic, actual media bytes, FFmpeg against platform media, or Emby/Jellyfin ingestion.

## Final retained-artifact and secret audits

| Audit | Exit | Final counts |
| --- | ---: | --- |
| Tracked, untracked and runtime/profile/QR inventory | `0` | `tracked=225`; `tracked_forbidden=0`; `untracked=0`; `suspicious_untracked=0`; `.media-sync files=911`; `.upstream files=849`; `unexpected runtime=0`; `unexpected profile=0`; `QR output=0`; `credential runtime files=0`; `historical profile fixtures=2` |
| Source/docs/SQLite/runtime high-confidence secret scan | `0` | `files=1136`; `SQLite=232`; `sidecars=22`; `SQLite logical values=18205`; `total scanned values=19341`; `high-confidence matches=0`; `nonreserved credentialed URLs=0`; reserved `.test` fixture URLs `=3`; loopback fixture URLs `=1` |
| Final patch whitespace | `0` | `git diff --check` produced no output |

The audit commands enumerate Git and runtime data without printing matched values, credentialed URLs or profile paths. Historical profile fixtures are permitted only under the frozen execution 0007/0008 retained sentinel roots.

## Live qualification matrix

No real browser, QR scan, account credential, creator endpoint, signed CDN request, media download or Emby/Jellyfin server was used.

| Platform | Real QR and saved session | Real creator sync | Real CDN media | Real Emby/Jellyfin scan/playback |
| --- | --- | --- | --- | --- |
| XHS | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Douyin | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Kuaishou | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Bilibili | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Weibo | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Tieba | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Zhihu | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

## Exclusions

Execution 0012 does not claim daemonization, automatic restart, Windows Service/systemd integration, Docker, REST, forced termination of synchronous pipeline threads, cross-host HA, seven-platform complete downloadable media, or any live qualification. A second OS signal is intentionally forceful; existing durable leases, parent-liveness containment and fencing own later recovery. The current automated signal evidence composes signal-handler unit tests, drain tests and lease-fencing tests; it is not a real active-pipeline second-signal end-to-end run.
