[English](verification.md) | **中文**

# 执行 0012 验证

- 状态：离线实现与收尾门禁通过
- 环境：Windows、本地工作区、由 `uv` 解析 Python 环境
- 证据日期：2026-08-31
- 计划提交：`4494226`
- 实现提交：`28655f8`

## 起始基线

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 既有通用父进程硬终止及登录正常超时/取消 | `uv run pytest -q tests/contract/test_mediacrawler_supervision.py::test_hard_parent_death_stops_real_child_tree_and_allows_safe_recovery tests/contract/test_mediacrawler_login.py::test_timeout_and_cancellation_join_the_complete_process_tree` | `0` | `PASS` — `3 passed in 8.15s` |

该基线只是前置证据；下方每项交付声明都来自实现后的测试，不会重新解释该历史运行。

## 实现专项证据

| 范围 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| Windows 精确结果后父进程硬终止 guardian 窗口 | `uv run pytest -q tests/contract/test_mediacrawler_login.py::test_hard_parent_death_after_result_frame_stops_guardian_tree_before_lock_release` | `0` | `PASS` — `1 passed in 4.49s` |
| 登录单元与契约边界 | `uv run pytest -q tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py` | `0` | `PASS` — `61 passed in 43.66s` |
| 登录及共享 MediaCrawler bridge/supervision 回归 | `uv run pytest -q tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py tests/contract/test_mediacrawler_supervision.py tests/contract/test_mediacrawler_bridge.py` | `0` | `PASS` — `149 passed, 1 skipped in 117.16s` |
| 截止时间回收、游标公平性、登录应用、CLI 与监督器 | `uv run pytest -q tests/integration/test_login_session_repository.py tests/integration/test_mediacrawler_login_application.py tests/unit/test_cli_login.py tests/unit/test_scheduler_supervisor.py tests/integration/test_scheduler_supervisor.py` | `0` | `PASS` — `127 passed in 14.83s` |
| 监督器重复取消单元竞态 | `uv run pytest -q tests/unit/test_scheduler_supervisor.py` | `0` | `PASS` — `32 passed in 0.71s` |
| 监督器集成、CLI 与登录专项组合 | `uv run pytest -q tests/unit/test_scheduler_supervisor.py tests/integration/test_scheduler_supervisor.py tests/unit/test_cli_supervisor.py tests/unit/test_cli_login.py` | `0` | `PASS` — `50 passed in 3.25s` |
| 根任务执行 0012 合并门禁 | `uv run pytest -q tests/unit/test_mediacrawler_login.py tests/contract/test_mediacrawler_login.py tests/contract/test_mediacrawler_supervision.py tests/contract/test_mediacrawler_bridge.py tests/integration/test_login_session_repository.py tests/integration/test_mediacrawler_login_application.py tests/unit/test_cli_login.py tests/unit/test_scheduler_supervisor.py tests/integration/test_scheduler_supervisor.py tests/unit/test_cli_supervisor.py` | `0` | `PASS` — `283 passed, 1 skipped in 129.24s` |

唯一跳过项为 `tests/contract/test_mediacrawler_supervision.py:556`：POSIX mode bit 不是 Windows ACL 边界；它在当前环境不适用，不是功能失败。

专项证据证明：精确请求/结果长度 framing、START gate、CANCEL/EOF/非法控制关闭、Windows 外层与 child 自持 Job 收容、POSIX 所属进程组收容、结果已读/控制未关的 guardian 窗口、完整树退出前账户锁持续持有、精确截止时间/CAS 回收与回滚、有界轮转游标公平性、单 cycle Fake 持久 sync 到 pipeline 成功、停止后不再 claim、订阅 cancel/join、pipeline heartbeat drain，以及两条 join 对重复 task cancellation 的承受能力。

## 根任务完整收尾门禁

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 完整离线套件 | `uv run pytest -q` | `0` | `PASS` — `1156 passed, 1 skipped in 256.84s` |
| 静态检查 | `uv run ruff check .` | `0` | `PASS` — `All checks passed!` |
| 格式 | `uv run ruff format --check .` | `0` | `PASS` — `207 files already formatted` |
| 严格类型 | `uv run mypy src/media_sync` | `0` | `PASS` — `Success: no issues found in 77 source files` |
| 文档链接 | `uv run python scripts/check_docs.py` | `0` | `PASS` — `Documentation links OK (64 Markdown files checked)` |
| 锁定上游 | `uv run python scripts/check_upstreams.py` | `0` | `PASS` — `Upstreams OK (2 locked checkouts verified)` |
| 源码包与 wheel | `uv build` | `0` | `PASS` — built `media_sync-0.1.0.tar.gz` and `media_sync-0.1.0-py3-none-any.whl` |
| 补丁空白 | `git diff --check` | `0` | `PASS` — no output |

本执行未运行覆盖率命令，因此不声明覆盖率。Fake scheduler 到 pipeline 集成只使用本地 SQLite 与确定性 handler；它不证明真实 CDN 流量、真实媒体字节、FFmpeg 对平台媒体的处理或 Emby/Jellyfin 入库。

## 最终保留产物与密钥审计

| 审计 | 退出码 | 最终计数 |
| --- | ---: | --- |
| tracked、untracked 与 runtime/profile/QR 清单 | `0` | `tracked=225`; `tracked_forbidden=0`; `untracked=0`; `suspicious_untracked=0`; `.media-sync files=911`; `.upstream files=849`; `unexpected runtime=0`; `unexpected profile=0`; `QR output=0`; `credential runtime files=0`; `historical profile fixtures=2` |
| 源码、文档、SQLite 与 runtime 高置信密钥扫描 | `0` | `files=1136`; `SQLite=232`; `sidecars=22`; `SQLite logical values=18205`; `total scanned values=19341`; `high-confidence matches=0`; `nonreserved credentialed URLs=0`; reserved `.test` fixture URLs `=3`; loopback fixture URLs `=1` |
| 最终补丁空白 | `0` | 无输出 |

审计命令会枚举 Git 与 runtime 数据，但不打印匹配值、带凭据 URL 或 profile 路径。历史 profile fixture 仅允许存在于冻结的执行 0007/0008 保留哨兵根目录内。

## 真人验收矩阵

未使用真人浏览器、二维码扫码、账户凭据、作者端点、签名 CDN 请求、媒体下载或 Emby/Jellyfin 服务器。

| 平台 | 真人 QR 与保存会话 | 真人作者同步 | 真人 CDN 媒体 | 真人 Emby/Jellyfin 重扫/播放 |
| --- | --- | --- | --- | --- |
| 小红书 `xhs` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 抖音 `dy` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 快手 `ks` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 哔哩哔哩 `bili` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 微博 `wb` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 百度贴吧 `tieba` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |
| 知乎 `zhihu` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` | `NOT_RUN` |

## 排除项

执行 0012 不声明 daemon 化、自动重启、Windows Service/systemd 集成、Docker、REST、同步 pipeline 线程强制终止、跨主机 HA、七平台完整可下载媒体或任何真人验收。第二次 OS 信号有意执行强制退出；既有持久租约、父进程存活收容与 fencing 负责后续恢复。当前自动信号证据由信号 handler 单元测试、drain 测试及租约 fencing 测试组合而成，不是真实 active pipeline 下第二次信号的端到端运行。
