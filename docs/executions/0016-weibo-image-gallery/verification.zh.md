[English](verification.md) | **中文**

# 执行 0016 验证

- 状态：离线实现与收尾门禁通过；真人验收保持 `NOT_RUN`
- 环境：Windows、本地工作区、由 `uv` 解析 Python 环境
- 证据日期：2026-08-31
- 计划提交：`b7bb818`
- 实现提交：`a77ca74`

## 起始基线

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 既有导入、detail、refresh/runtime、下载器/网络、Emby application/layout 及 Bilibili/快手/抖音组合 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py tests/integration/test_douyin_playable_pipeline.py` | `0` | `PASS` — `272 passed in 46.92s` |

该基线证明前置的平台无关图片原语与三个既有视频平台组合；不证明微博媒体捕获、Asset 发现、detail 刷新、传输或 Emby 图片发布。

## 实现证据

| 范围 | 状态 | 证据 |
| --- | --- | --- |
| Creator child shim | `PASS` | 真实隔离 fake child 导入已验证 checkout、安装 shim、运行并发 note task，并证明 task-local 有序捕获及重复/转发/page-info/漂移关闭失败。 |
| Detail child shim | `PASS` | `MediaCrawlerDetailProcessRunner` 跨越 child 边界，证明 `platform=wb`、精确纯 numeric `WEIBO_SPECIFIED_ID_LIST`、JSONL/媒体关闭/并发配置、有界 framing、稳定 profile 与成功 attempt 清理。 |
| 封闭源形状 | `PASS` | 只有规范 numeric 原创帖子、无媒体 `page_info`、唯一有序 PID、`sinaimg.cn` 或子域 authority，以及 `jpg/jpeg/png/webp` 扩展名会产生 Asset；外部源站、视频/GIF/未知扩展名与畸形形状均关闭失败。 |
| IMAGE/GALLERY 归一化 | `PASS` | 单图成为 `IMAGE`；多图成为 `GALLERY`；Asset kind、position、remote ID、MIME 与 source-hint 顺序确定。 |
| SQLite 身份与来源 | `PASS` | 两个有序 IMAGE Asset 持久化稳定 adapter-refresh locator 与绑定精确当前 Account/Subscription 的 `AssetRefreshSource` observation；重放不创建重复身份。 |
| 精确 WB detail 身份 | `PASS` | 请求构造、resolved reference 与 child load 都要求 `detail_reference == content_remote_id` 且为同一规范纯 numeric ID；刷新匹配 content、remote ID、kind、position 与无 query source hint；重排/重复漂移关闭失败。 |
| 双图传输与归档 | `PASS` | 组合 E2E 执行两次 detail 刷新、两次公网 DNS/默认 profile HTTP 请求，接收两份不同合成 PNG payload，并发布两个独立 SHA-256 归档；不发送 Cookie、Authorization、Referer 或 Origin。 |
| Emby 布局 | `PASS` | 首图作为 poster、次图作为 backdrop，两图以有序 gallery 001/002 文件输出；NFO 引用 poster/backdrop；source 元数据记录两个有序 ID/checksum，且不含 raw locator 或 source URL。 |
| 私有与瞬态边界 | `PASS` | 私有字段、两个 PID sentinel 与一个嵌套签名 URL sentinel 不存在于 normalized raw、SQLite 及 sidecar、runtime/work 根、两个归档、export staging 与媒体库输出。 |
| 零工作重放 | `PASS` | 重放不新增 detail runner、HTTP、DNS、probe、archive 或 export 工作，且归档/媒体库树逐字节一致。 |

## 独立审查与修复

| 发现 | 处理 |
| --- | --- |
| 代理转换接受任意内嵌源站。 | 把原始转换与 normalized proxy 校验都限制为 `sinaimg.cn` 及其子域，并增加外部源站关闭失败回归。 |
| IMAGE 接受视频、GIF 或未知后缀。 | 增加不区分大小写的 `jpg/jpeg/png/webp` 白名单，排除动图与非静态格式。 |
| 不同但规范的 WB numeric detail ID 能通过初始校验。 | 在请求构造、resolved-reference 与 child-load 三层要求完全相同的纯 numeric ID，并增加不相等回归。 |
| 初始组合测试只使用一张图却声明 Gallery 输出。 | 以双图 Gallery E2E 替代，证明两次刷新、传输、归档及有序 Emby gallery 文件。 |

## 质量门禁

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 15 文件合并专项门禁 | `uv run pytest -q tests/contract/test_mediacrawler_bridge.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/unit/test_media_downloader.py tests/unit/test_media_locator.py tests/unit/test_media_network.py tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_kuaishou_playable_pipeline.py tests/integration/test_douyin_playable_pipeline.py tests/integration/test_weibo_image_pipeline.py` | `0` | `PASS` — `388 passed in 125.73s` |
| 完整测试套件 | `uv run pytest -q` | `0` | `PASS` — `1251 passed, 1 skipped in 359.38s`; skip: Windows-inapplicable POSIX mode-bit test / 跳过：Windows 不适用的 POSIX mode-bit 测试 |
| Ruff 静态检查 | `uv run ruff check .` | `0` | `PASS` |
| Ruff 格式 | `uv run ruff format --check .` | `0` | 228 个文件格式正确 |
| 严格类型检查 | `uv run mypy src/media_sync` | `0` | 成功检查 78 个源码文件 |
| 锁定上游校验 | `uv run python scripts/check_upstreams.py` | `0` | 2 个上游条目校验通过 |
| 构建 | `uv build` | `0` | 产生 wheel 与源码分发包 |
| Diff 检查 | `git diff --check` and `git diff --cached --check` | `0` | `PASS` |
| 最终真值编辑后的文档检查 | `uv run python scripts/check_docs.py` | `0` | 检查 80 个 Markdown 文件 |

不宣称运行过覆盖率。以上专项及完整结果是实现提交证据。Git 推送及本地/tracking/GitHub 最终 SHA 核对只能在本文档提交产生后执行，因此其权威结果记录在任务交接中，而不在此处自引用写入。

## 保留产物与 Git 清单

只读收尾审计枚举 Git tracked、标准 untracked 路径，以及忽略目录 `.media-sync` 与 `dist` 下的每个真实文件。审计允许已跟踪的 `.env.example` 模板，但拒绝 runtime、upstream、build、浏览器 profile、真实环境与 SQLite 路径；它在不打印匹配数据的前提下，以拆分构造的执行私有字段/PID/签名 marker 扫描保留 `.media-sync` 文件，并确认冻结的执行 0007/0008 sentinel 根仍存在。

| 审计 | 退出码 | 结果 |
| --- | ---: | --- |
| 最终 tracked/untracked/runtime 清单及执行 0016 保留 marker 扫描 | `0` | `tracked=246`; `untracked=0`; `tracked_forbidden=0`; `suspicious_untracked=0`; `runtime_and_build_files=914`; `runtime_execution0016_marker_hits=0`; `sentinel_roots_preserved=2/2` |

## 真人验收

| 项目 | 状态 |
| --- | --- |
| 真人 QR/Cookie/saved-session 登录 | `NOT_RUN` |
| 真人 creator 扫描与增量重跑 | `NOT_RUN` |
| 真实 detail 与图片代理/CDN 传输 | `NOT_RUN` |
| 真实平台字节经生产 probe 依赖 | `NOT_RUN` |
| 真实 Emby/Jellyfin 服务器扫描与查看 | `NOT_RUN` |

这些 `NOT_RUN` 行不是失败，也不能由离线 mock 推导为通过；它们继续属于需要操作员协助的显式验收工作，微博视频/动图/长图语义、有界 creator 分页、新浪直连 profile、同 ID 替换检测、cleanup-failure quarantine 及其余跨平台总目标也同样未完成。
