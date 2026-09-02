[English](verification.md) | **中文**

# 执行 0014 验证

- 状态：离线实现与收尾门禁通过；真人验收仍为 `NOT_RUN`
- 环境：Windows、本地工作区、由 `uv` 解析 Python 环境
- 证据日期：2026-08-31
- 计划提交：`95c7082`
- 实现提交：`c4ab537`

## 起始基线

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 既有导入、detail、refresh/runtime、下载器/网络、Emby layout/application 及通用离线 pipeline | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_offline_media_pipeline.py` | `0` | `PASS` — `211 passed in 27.81s` |

该基线证明既有快手 normalizer/单元 refresh case 及平台无关媒体机制；不证明锁定的快手 detail 配置、精确 runtime 来源、视频+封面传输、Emby 主媒体目录或平台级重放。

## 实现专项证据

| 范围 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 快手发现/raw、锁定 detail 进程、精确 Account/Subscription 刷新、视频+封面下载/探测/归档、Emby 发布及重放 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_kuaishou_playable_pipeline.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py` | `0` | `PASS` — `228 passed in 25.49s` |

专项门禁证明精确视频/封面 remote ID、position、MIME/source hint 与来源；userinfo/query/fragment/嵌套形状值不会进入归一化 raw、ORM 及 dispose 后 SQLite/sidecar；真实 fake checkout 经过 process runner；缺失/漂移/重复返回固定结果；惰性 runtime 精确绑定 Account/Subscription；默认 request profile 不含 Cookie 或 Authorization；确定性 MP4/PNG 完成传输、强制视频探测、SHA-256 归档及 Emby `.mp4`/海报/NFO/source 发布。仅 query 变化的重放会保留 generation，并重新读取实时计数，证明不会再次调用 detail runner、HTTP、DNS 或 probe。

## 根任务完整收尾门禁

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 完整离线套件 | `uv run pytest -q` | `0` | `PASS` — `1206 passed, 1 skipped in 269.21s` |
| 静态检查 | `uv run ruff check .` | `0` | `PASS` — `All checks passed!` |
| 格式 | `uv run ruff format --check .` | `0` | `PASS` — `217 files already formatted` |
| 严格类型 | `uv run mypy src/media_sync` | `0` | `PASS` — `Success: no issues found in 77 source files` |
| 文档链接 | `uv run python scripts/check_docs.py` | `0` | `PASS` — `Documentation links OK (72 Markdown files checked)` |
| 锁定上游 | `uv run python scripts/check_upstreams.py` | `0` | `PASS` — `Upstreams OK (2 locked checkouts verified)` |
| 源码包与 wheel | `uv build` | `0` | `PASS` — built `dist\media_sync-0.1.0.tar.gz` and `dist\media_sync-0.1.0-py3-none-any.whl` |
| 补丁空白 | `git diff --check` 与 `git diff --cached --check` | `0` | 无输出 |

唯一跳过项为 `tests/contract/test_mediacrawler_supervision.py:556`：POSIX mode bit 不是 Windows ACL 边界；它在当前环境不适用，不是功能失败。本执行未运行 coverage 命令，因此不声明覆盖率。

## 保留产物与瞬态数据审计

最终只读 PowerShell 审计枚举 tracked、标准 untracked 文件，以及忽略目录 `.media-sync` 与 `dist` 下的每个真实文件；它拒绝被跟踪/未跟踪的运行或凭据路径，从拆分的非密钥字面量构造三个执行标记，在不打印命中数据的情况下扫描 Git 可见/runtime/build 字节，并确认冻结的 `0007`/`0008` 哨兵根仍然存在。

| 审计 | 退出码 | 最终计数 |
| --- | ---: | --- |
| Git、runtime、build 清单及精确瞬态标记扫描 | `0` | `tracked=235`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `git_ephemeral_marker_hits=0`; `runtime_ephemeral_marker_hits=0`; `sentinel_roots_preserved=1` |

端到端测试还分别扫描 Author/Content/Asset raw 与 locator、Job/SyncRun payload、dispose 后 SQLite 及 sidecar、detail runtime、下载/导出工作根、归档、Emby 媒体库、source 元数据与对象表示。动态已知/未知 query、fragment、userinfo 及嵌套形状哨兵不会进入任何持久落点。

## 真人验收

| 项目 | 状态 |
| --- | --- |
| 真人 QR/Cookie/saved-session 登录 | `NOT_RUN` |
| 真人作者扫描与增量重跑 | `NOT_RUN` |
| 真人 detail 与签名 CDN 传输 | `NOT_RUN` |
| 真实平台字节经 FFmpeg/ffprobe | `NOT_RUN` |
| 真人 Emby/Jellyfin 重扫与播放 | `NOT_RUN` |

离线 fake checkout、mock DNS/HTTP 与合成字节不会提升任何真人行。同 ID/同 origin/path 字节替换及注入 detail 清理失败继续作为 `goal.md` 与 `progress.md` 中的明确限制。
