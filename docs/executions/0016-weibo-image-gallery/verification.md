# Execution 0016 verification / 执行 0016 验证

- Status / 状态：Offline implementation and closeout gates pass; live qualification remains `NOT_RUN` / 离线实现与收尾门禁通过；真人验收保持 `NOT_RUN`
- Environment / 环境：Windows, local workspace, Python environment resolved by `uv` / Windows、本地工作区、由 `uv` 解析 Python 环境
- Evidence date / 证据日期：2026-08-31
- Plan commit / 计划提交：`b7bb818`
- Implementation commit / 实现提交：`a77ca74`

## Starting baseline / 起始基线

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Existing ingestion, detail, refresh/runtime, downloader/network, Emby application/layout and Bilibili/Kuaishou/Douyin compositions / 既有导入、detail、refresh/runtime、下载器/网络、Emby application/layout 及 Bilibili/快手/抖音组合 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py tests/integration/test_douyin_playable_pipeline.py` | `0` | `PASS` — `272 passed in 46.92s` |

The baseline proved predecessor platform-neutral image primitives and the three existing video-platform compositions. It did not prove Weibo media capture, Asset discovery, detail refresh, transfer or Emby image publication. / 该基线证明前置的平台无关图片原语与三个既有视频平台组合；不证明微博媒体捕获、Asset 发现、detail 刷新、传输或 Emby 图片发布。

## Implementation evidence / 实现证据

| Scope / 范围 | Status / 状态 | Evidence / 证据 |
| --- | --- | --- |
| Creator child shim / Creator child shim | `PASS` | A real isolated fake child imports a verified checkout, installs the shim, runs concurrent note tasks and proves task-local ordered capture plus fail-closed duplicate/retweet/page-info/drift behavior. / 真实隔离 fake child 导入已验证 checkout、安装 shim、运行并发 note task，并证明 task-local 有序捕获及重复/转发/page-info/漂移关闭失败。 |
| Detail child shim / Detail child shim | `PASS` | `MediaCrawlerDetailProcessRunner` crosses the child boundary with `platform=wb`, exact plain numeric `WEIBO_SPECIFIED_ID_LIST`, JSONL/media-off/concurrency configuration, bounded framing, stable profile and successful attempt cleanup. / `MediaCrawlerDetailProcessRunner` 跨越 child 边界，证明 `platform=wb`、精确纯 numeric `WEIBO_SPECIFIED_ID_LIST`、JSONL/媒体关闭/并发配置、有界 framing、稳定 profile 与成功 attempt 清理。 |
| Closed source shape / 封闭源形状 | `PASS` | Only canonical numeric original posts, no media `page_info`, unique ordered PIDs, `sinaimg.cn` or subdomain authority, and `jpg/jpeg/png/webp` extensions emit Assets. Foreign hosts, video/GIF/unknown extensions and malformed shapes fail closed. / 只有规范 numeric 原创帖子、无媒体 `page_info`、唯一有序 PID、`sinaimg.cn` 或子域 authority，以及 `jpg/jpeg/png/webp` 扩展名会产生 Asset；外部源站、视频/GIF/未知扩展名与畸形形状均关闭失败。 |
| IMAGE/GALLERY normalization / IMAGE/GALLERY 归一化 | `PASS` | One image becomes `IMAGE`; multiple images become `GALLERY`; Asset kind, position, remote ID, MIME and source-hint order are deterministic. / 单图成为 `IMAGE`；多图成为 `GALLERY`；Asset kind、position、remote ID、MIME 与 source-hint 顺序确定。 |
| SQLite identity/provenance / SQLite 身份与来源 | `PASS` | Two ordered IMAGE Assets persist stable adapter-refresh locators and exact current Account/Subscription-bound `AssetRefreshSource` observations; replay does not create duplicate identities. / 两个有序 IMAGE Asset 持久化稳定 adapter-refresh locator 与绑定精确当前 Account/Subscription 的 `AssetRefreshSource` observation；重放不创建重复身份。 |
| Exact WB detail identity / 精确 WB detail 身份 | `PASS` | Request construction, resolved reference and child load all require `detail_reference == content_remote_id` as the same canonical plain numeric ID. Refresh matches content, remote ID, kind, position and query-free source hint; reorder/duplicate drift fails closed. / 请求构造、resolved reference 与 child load 都要求 `detail_reference == content_remote_id` 且为同一规范纯 numeric ID；刷新匹配 content、remote ID、kind、position 与无 query source hint；重排/重复漂移关闭失败。 |
| Two-image transfer/archive / 双图传输与归档 | `PASS` | The composition E2E performs two detail refreshes, two public-DNS/default-profile HTTP requests, receives two distinct synthetic PNG payloads and publishes two independent SHA-256 archives. No Cookie, Authorization, Referer or Origin is sent. / 组合 E2E 执行两次 detail 刷新、两次公网 DNS/默认 profile HTTP 请求，接收两份不同合成 PNG payload，并发布两个独立 SHA-256 归档；不发送 Cookie、Authorization、Referer 或 Origin。 |
| Emby layout / Emby 布局 | `PASS` | First image is poster, second is backdrop, both appear as ordered gallery 001/002 files, NFO references poster/backdrop, and source metadata records both ordered IDs/checksums without raw locators or source URLs. / 首图作为 poster、次图作为 backdrop，两图以有序 gallery 001/002 文件输出；NFO 引用 poster/backdrop；source 元数据记录两个有序 ID/checksum，且不含 raw locator 或 source URL。 |
| Private/transient boundary / 私有与瞬态边界 | `PASS` | The private field, two PID sentinels and a nested signed-URL sentinel are absent from normalized raw, SQLite and sidecars, runtime/work roots, both archives, export staging and library output. / 私有字段、两个 PID sentinel 与一个嵌套签名 URL sentinel 不存在于 normalized raw、SQLite 及 sidecar、runtime/work 根、两个归档、export staging 与媒体库输出。 |
| Zero-work replay / 零工作重放 | `PASS` | Replay adds no detail runner, HTTP, DNS, probe, archive or export work and leaves archive/library trees byte-identical. / 重放不新增 detail runner、HTTP、DNS、probe、archive 或 export 工作，且归档/媒体库树逐字节一致。 |

## Independent review and repair / 独立审查与修复

| Finding / 发现 | Resolution / 处理 |
| --- | --- |
| The proxy transformation accepted an arbitrary embedded source host. / 代理转换接受任意内嵌源站。 | Restricted both raw transformation and normalized proxy validation to `sinaimg.cn` and its subdomains; added foreign-host fail-closed regressions. / 把原始转换与 normalized proxy 校验都限制为 `sinaimg.cn` 及其子域，并增加外部源站关闭失败回归。 |
| IMAGE accepted video, GIF or unknown suffixes. / IMAGE 接受视频、GIF 或未知后缀。 | Added a case-insensitive `jpg/jpeg/png/webp` allowlist; excluded animation and non-static formats. / 增加不区分大小写的 `jpg/jpeg/png/webp` 白名单，排除动图与非静态格式。 |
| Different canonical numeric WB detail IDs passed initial validation. / 不同但规范的 WB numeric detail ID 能通过初始校验。 | Required exact same plain numeric ID at request construction, resolved-reference and child-load boundaries; added mismatch regressions. / 在请求构造、resolved-reference 与 child-load 三层要求完全相同的纯 numeric ID，并增加不相等回归。 |
| The first composition test used only one image while claiming Gallery output. / 初始组合测试只使用一张图却声明 Gallery 输出。 | Replaced it with a two-image Gallery E2E proving two refreshes, transfers, archives and ordered Emby gallery files. / 以双图 Gallery E2E 替代，证明两次刷新、传输、归档及有序 Emby gallery 文件。 |

## Quality gates / 质量门禁

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Combined focused gate across 15 files / 15 文件合并专项门禁 | `uv run pytest -q tests/contract/test_mediacrawler_bridge.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py tests/integration/test_douyin_playable_pipeline.py tests/integration/test_weibo_image_pipeline.py` | `0` | `PASS` — `388 passed in 125.73s` |
| Complete test suite / 完整测试套件 | `uv run pytest -q` | `0` | `PASS` — `1251 passed, 1 skipped in 359.38s`; skip: Windows-inapplicable POSIX mode-bit test / 跳过：Windows 不适用的 POSIX mode-bit 测试 |
| Ruff lint / Ruff 静态检查 | `uv run ruff check .` | `0` | `PASS` |
| Ruff format / Ruff 格式 | `uv run ruff format --check .` | `0` | `PASS` — 228 files already formatted / 228 个文件格式正确 |
| Strict typing / 严格类型检查 | `uv run mypy src/media_sync` | `0` | `PASS` — success for 78 source files / 成功检查 78 个源码文件 |
| Pinned upstream verification / 锁定上游校验 | `uv run python scripts/check_upstreams.py` | `0` | `PASS` — 2 upstream entries verified / 2 个上游条目校验通过 |
| Build / 构建 | `uv build` | `0` | `PASS` — wheel and source distribution produced / 产生 wheel 与源码分发包 |
| Diff checks / Diff 检查 | `git diff --check` and `git diff --cached --check` | `0` | `PASS` |
| Documentation after final truth edits / 最终真值编辑后的文档检查 | `uv run python scripts/check_docs.py` | `0` | `PASS` — 80 Markdown files checked / 检查 80 个 Markdown 文件 |

No coverage run is claimed. The focused and complete results above are implementation-commit evidence. Git push and final local/tracking/GitHub SHA reconciliation occur after this documentation commit exists, so their authoritative result is reported in the task handoff rather than self-referentially embedded here. / 不宣称运行过覆盖率。以上专项及完整结果是实现提交证据。Git 推送及本地/tracking/GitHub 最终 SHA 核对只能在本文档提交产生后执行，因此其权威结果记录在任务交接中，而不在此处自引用写入。

## Retained and Git inventory / 保留产物与 Git 清单

The read-only closeout audit enumerated Git tracked and standard-untracked paths plus every real file below ignored `.media-sync` and `dist`. It allowed the tracked `.env.example` template but rejected runtime, upstream, build, browser-profile, real environment and SQLite paths. It byte-scanned retained `.media-sync` files for the split execution-private field/PID/signature markers without printing matched data and verified that the frozen execution 0007/0008 sentinel roots still exist. / 只读收尾审计枚举 Git tracked、标准 untracked 路径，以及忽略目录 `.media-sync` 与 `dist` 下的每个真实文件。审计允许已跟踪的 `.env.example` 模板，但拒绝 runtime、upstream、build、浏览器 profile、真实环境与 SQLite 路径；它在不打印匹配数据的前提下，以拆分构造的执行私有字段/PID/签名 marker 扫描保留 `.media-sync` 文件，并确认冻结的执行 0007/0008 sentinel 根仍存在。

| Audit / 审计 | Exit / 退出码 | Result / 结果 |
| --- | ---: | --- |
| Final tracked/untracked/runtime inventory and execution-0016 retained-marker scan / 最终 tracked/untracked/runtime 清单及执行 0016 保留 marker 扫描 | `0` | `tracked=246`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `runtime_execution0016_marker_hits=0`; `sentinel_roots_preserved=2/2` |

## Live qualification / 真人验收

| Item / 项目 | Status / 状态 |
| --- | --- |
| Real QR/Cookie/saved-session login / 真人 QR/Cookie/saved-session 登录 | `NOT_RUN` |
| Real creator scan and incremental rerun / 真人 creator 扫描与增量重跑 | `NOT_RUN` |
| Real detail and image-proxy/CDN transfer / 真实 detail 与图片代理/CDN 传输 | `NOT_RUN` |
| Real platform bytes through production probe dependencies / 真实平台字节经生产 probe 依赖 | `NOT_RUN` |
| Real Emby/Jellyfin server scan and viewing / 真实 Emby/Jellyfin 服务器扫描与查看 | `NOT_RUN` |

These `NOT_RUN` rows are not failures and are not implied by offline mocks. They remain explicit operator-assisted qualification work, as do Weibo video/animation/long-image semantics, bounded creator pagination, a Sina-direct profile, same-ID replacement detection, cleanup-failure quarantine and the remaining cross-platform objective. / 这些 `NOT_RUN` 行不是失败，也不能由离线 mock 推导为通过；它们继续属于需要操作员协助的显式验收工作，微博视频/动图/长图语义、有界 creator 分页、新浪直连 profile、同 ID 替换检测、cleanup-failure quarantine 及其余跨平台总目标也同样未完成。
