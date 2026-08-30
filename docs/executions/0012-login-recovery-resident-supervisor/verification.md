# Execution 0012 verification / 执行 0012 验证

- Status / 状态：Offline implementation and closeout gates pass / 离线实现与收尾门禁通过
- Environment / 环境：Windows, local workspace, Python environment resolved by `uv` / Windows、本地工作区、由 `uv` 解析 Python 环境
- Evidence date / 证据日期：2026-08-31
- Plan commit / 计划提交：`4494226`
- Implementation commit / 实现提交：`28655f8`

## Starting baseline / 起始基线

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Existing generic hard-parent-death plus login normal timeout/cancellation / 既有通用父进程硬终止及登录正常超时/取消 | `uv run pytest -q tests/contract/test_mediacrawler_supervision.py::test_hard_parent_death_stops_real_child_tree_and_allows_safe_recovery tests/contract/test_mediacrawler_login.py::test_timeout_and_cancellation_join_the_complete_process_tree` | `0` | `PASS` — `3 passed in 8.15s` |

The baseline was predecessor-only evidence. Every delivered claim below comes from post-implementation tests and does not reinterpret that historical run. / 该基线只是前置证据；下方每项交付声明都来自实现后的测试，不会重新解释该历史运行。

## Focused implementation evidence / 实现专项证据

| Scope / 范围 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Exact post-result hard-parent-death guardian window on Windows / Windows 精确结果后父进程硬终止 guardian 窗口 | `uv run pytest -q tests/contract/test_mediacrawler_login.py::test_hard_parent_death_after_result_frame_stops_guardian_tree_before_lock_release` | `0` | `PASS` — `1 passed in 4.49s` |
| Login unit and contract boundary / 登录单元与契约边界 | `uv run pytest -q tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py` | `0` | `PASS` — `61 passed in 43.66s` |
| Login plus shared MediaCrawler bridge/supervision regression / 登录及共享 MediaCrawler bridge/supervision 回归 | `uv run pytest -q tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py tests/contract/test_mediacrawler_supervision.py tests/contract/test_mediacrawler_bridge.py` | `0` | `PASS` — `149 passed, 1 skipped in 117.16s` |
| Deadline recovery, cursor fairness, login application, CLI and supervisor / 截止时间回收、游标公平性、登录应用、CLI 与监督器 | `uv run pytest -q tests/integration/test_login_session_repository.py tests/integration/test_mediacrawler_login_application.py tests/unit/test_cli_login.py tests/unit/test_scheduler_supervisor.py tests/integration/test_scheduler_supervisor.py` | `0` | `PASS` — `127 passed in 14.83s` |
| Supervisor repeated-cancellation unit races / 监督器重复取消单元竞态 | `uv run pytest -q tests/unit/test_scheduler_supervisor.py` | `0` | `PASS` — `32 passed in 0.71s` |
| Supervisor integration, CLI and login-focused composition / 监督器集成、CLI 与登录专项组合 | `uv run pytest -q tests/unit/test_scheduler_supervisor.py tests/integration/test_scheduler_supervisor.py tests/unit/test_cli_supervisor.py tests/unit/test_cli_login.py` | `0` | `PASS` — `50 passed in 3.25s` |
| Root integrated execution 0012 gate / 根任务执行 0012 合并门禁 | `uv run pytest -q tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py tests/contract/test_mediacrawler_supervision.py tests/contract/test_mediacrawler_bridge.py tests/integration/test_login_session_repository.py tests/integration/test_mediacrawler_login_application.py tests/unit/test_cli_login.py tests/unit/test_scheduler_supervisor.py tests/integration/test_scheduler_supervisor.py tests/unit/test_cli_supervisor.py` | `0` | `PASS` — `283 passed, 1 skipped in 129.24s` |

The one skip is `tests/contract/test_mediacrawler_supervision.py:556`: POSIX mode bits are not the Windows ACL boundary. It is environment-inapplicable, not a failed feature. / 唯一跳过项为 `tests/contract/test_mediacrawler_supervision.py:556`：POSIX mode bit 不是 Windows ACL 边界；它在当前环境不适用，不是功能失败。

The focused evidence proves: exact request/result length framing; START gating; CANCEL/EOF/malformed-control closure; Windows outer and child-owned Job containment; POSIX owned process-group containment; the result-read/pre-control-close guardian window; account-lock retention until complete-tree exit; exact deadline/CAS recovery and rollback; bounded rotating-cursor fairness; one-cycle Fake durable sync-to-pipeline success; stop-before-later-claim behavior; subscription cancel/join; pipeline heartbeat drain; and repeated task-cancellation resilience for both joins. / 专项证据证明：精确请求/结果长度 framing、START gate、CANCEL/EOF/非法控制关闭、Windows 外层与 child 自持 Job 收容、POSIX 所属进程组收容、结果已读/控制未关的 guardian 窗口、完整树退出前账户锁持续持有、精确截止时间/CAS 回收与回滚、有界轮转游标公平性、单 cycle Fake 持久 sync 到 pipeline 成功、停止后不再 claim、订阅 cancel/join、pipeline heartbeat drain，以及两条 join 对重复 task cancellation 的承受能力。

## Complete root closeout gates / 根任务完整收尾门禁

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Complete offline suite / 完整离线套件 | `uv run pytest -q` | `0` | `PASS` — `1156 passed, 1 skipped in 256.84s` |
| Lint / 静态检查 | `uv run ruff check .` | `0` | `PASS` — `All checks passed!` |
| Format / 格式 | `uv run ruff format --check .` | `0` | `PASS` — `207 files already formatted` |
| Strict typing / 严格类型 | `uv run mypy src/media_sync` | `0` | `PASS` — `Success: no issues found in 77 source files` |
| Documentation links / 文档链接 | `uv run python scripts/check_docs.py` | `0` | `PASS` — `Documentation links OK (64 Markdown files checked)` |
| Pinned upstreams / 锁定上游 | `uv run python scripts/check_upstreams.py` | `0` | `PASS` — `Upstreams OK (2 locked checkouts verified)` |
| Source distribution and wheel / 源码包与 wheel | `uv build` | `0` | `PASS` — built `media_sync-0.1.0.tar.gz` and `media_sync-0.1.0-py3-none-any.whl` |
| Patch whitespace / 补丁空白 | `git diff --check` | `0` | `PASS` — no output |

No coverage command ran, so execution 0012 makes no coverage claim. The Fake scheduler-to-pipeline integration uses local SQLite and deterministic handlers; it does not prove real CDN traffic, actual media bytes, FFmpeg against platform media, or Emby/Jellyfin ingestion. / 本执行未运行覆盖率命令，因此不声明覆盖率。Fake scheduler 到 pipeline 集成只使用本地 SQLite 与确定性 handler；它不证明真实 CDN 流量、真实媒体字节、FFmpeg 对平台媒体的处理或 Emby/Jellyfin 入库。

## Final retained-artifact and secret audits / 最终保留产物与密钥审计

| Audit / 审计 | Exit / 退出码 | Final counts / 最终计数 |
| --- | ---: | --- |
| Tracked, untracked and runtime/profile/QR inventory / tracked、untracked 与 runtime/profile/QR 清单 | `0` | `tracked=225`; `tracked_forbidden=0`; `untracked=0`; `suspicious_untracked=0`; `.media-sync files=911`; `.upstream files=849`; `unexpected runtime=0`; `unexpected profile=0`; `QR output=0`; `credential runtime files=0`; `historical profile fixtures=2` |
| Source/docs/SQLite/runtime high-confidence secret scan / 源码、文档、SQLite 与 runtime 高置信密钥扫描 | `0` | `files=1136`; `SQLite=232`; `sidecars=22`; `SQLite logical values=18205`; `total scanned values=19341`; `high-confidence matches=0`; `nonreserved credentialed URLs=0`; reserved `.test` fixture URLs `=3`; loopback fixture URLs `=1` |
| Final patch whitespace / 最终补丁空白 | `0` | `git diff --check` produced no output / 无输出 |

The audit commands enumerate Git and runtime data without printing matched values, credentialed URLs or profile paths. Historical profile fixtures are permitted only under the frozen execution 0007/0008 retained sentinel roots. / 审计命令会枚举 Git 与 runtime 数据，但不打印匹配值、带凭据 URL 或 profile 路径。历史 profile fixture 仅允许存在于冻结的执行 0007/0008 保留哨兵根目录内。

## Live qualification matrix / 真人验收矩阵

No real browser, QR scan, account credential, creator endpoint, signed CDN request, media download or Emby/Jellyfin server was used. / 未使用真人浏览器、二维码扫码、账户凭据、作者端点、签名 CDN 请求、媒体下载或 Emby/Jellyfin 服务器。

| Platform / 平台 | Real QR and saved session / 真人 QR 与保存会话 | Real creator sync / 真人作者同步 | Real CDN media / 真人 CDN 媒体 | Real Emby/Jellyfin scan/playback / 真人 Emby/Jellyfin 重扫/播放 |
| --- | --- | --- | --- | --- |
| XHS / 小红书 `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Douyin / 抖音 `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Kuaishou / 快手 `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Bilibili / 哔哩哔哩 `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Weibo / 微博 `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Tieba / 百度贴吧 `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| Zhihu / 知乎 `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

## Exclusions / 排除项

Execution 0012 does not claim daemonization, automatic restart, Windows Service/systemd integration, Docker, REST, forced termination of synchronous pipeline threads, cross-host HA, seven-platform complete downloadable media, or any live qualification. A second OS signal is intentionally forceful; existing durable leases, parent-liveness containment and fencing own later recovery. The current automated signal evidence composes signal-handler unit tests, drain tests and lease-fencing tests; it is not a real active-pipeline second-signal end-to-end run. / 执行 0012 不声明 daemon 化、自动重启、Windows Service/systemd 集成、Docker、REST、同步 pipeline 线程强制终止、跨主机 HA、七平台完整可下载媒体或任何真人验收。第二次 OS 信号有意执行强制退出；既有持久租约、父进程存活收容与 fencing 负责后续恢复。当前自动信号证据由信号 handler 单元测试、drain 测试及租约 fencing 测试组合而成，不是真实 active pipeline 下第二次信号的端到端运行。
