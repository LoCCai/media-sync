[English](verification.md) | **中文**

# 执行 0026 验证记录

- 状态：冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- 日期：2026-09-02
- 前置：`7cb84fc6c93b832492b95513d9cb6a9708ee6cc9`
- 计划提交：`0694934bc9230151a85c040a061d6e704dffc4fc`
- 实现提交：`190488f77d1704492cc148b890d6f9ae16d84f84`

## 前置基线

| 检查 | 结果 |
| --- | --- |
| Execution 0025 专项回归 | `PASS — 466 passed in 66.96s` |
| Execution 0025 完整套件 | `PASS — 1790 passed, 1 skipped in 331.33s` |
| 生产备用路径收尾复验 | `PASS — 1 passed in 1.74s` |
| 文档与上游锁 | 116 份 Markdown；2 个锁定且干净的 checkout` |
| 仓库审计 | 跟踪 304；未跟踪 0；跟踪 runtime/upstream 0` |
| 本地/tracking/GitHub 核对 | `PASS — 7cb84fc6c93b832492b95513d9cb6a9708ee6cc9` |

## 已实现证据

| 范围 | 结果 |
| --- | --- |
| 严格 v6 协议解析 | 精确一个 progressive `durl` 接受一个主地址、等价 `backup_url`/`backupUrl` 别名及最多八个已校验互异备用地址；畸形、冲突、重复、与主地址相同及超限候选均关闭失败 |
| 私有桥接兼容 | 单 P 私有备用字段与多分 P 可选 `backup_urls` 可到达运行时 `ResolvedLocator`；历史仅主地址 payload 继续接受 |
| 共享候选顺序 | 普通 progressive 与 DASH locator 共用既有 Asset 锁、截止时间、字节上限及 restart 预算下的主地址优先轮次；主地址成功时备用 DNS/HTTP 为零 |
| 可切换与立即失败 | DNS、timeout、传输、中断、HTTP 与 Range 不兼容可推进；网络策略、重定向/header/encoding、chunk/size、文件系统、探测、合并、归档及发布失败继续立即关闭 |
| 严格 partial 连续性 | 跨候选追加要求 offset、总长度、validator 类型和值完全一致；混合失败保留合法 partial，只有完整候选轮次拒绝 partial 后才有界丢弃/restart |
| Adapter 刷新语义 | adapter 一轮仅含 `401`/`403` 时重解析详情一次；第二轮仍全鉴权失败返回 `locator_refresh_auth_expired`；混合/非鉴权穷尽与 direct locator 不刷新 |
| 瞬态边界 | 主/备用签名值与全部私有字段递归地不存在于保留 SQLite、Job、runtime、work、归档、导出及运维证据中 |
| 单 P 组合 | SQLite → 精确 CID 详情 → 主地址 `503` → 备用字节 → 受控探测 → SHA-256 归档 → Emby MP4/NFO/source 成功；重放不新增 detail/DNS/HTTP/probe/archive/export 工作 |
| 多分 P 组合 | 三个分 P 的主地址均返回 `503`，有序备用地址提供互异字节，主媒体/part 发布成功且重放零工作 |
| 兼容 | 无备用 progressive、DASH 备用故障切换、静态媒体、恢复路径与十二个冻结媒体形状计数保持通过 |

## 测试与质量门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 实现专项回归 | `uv run pytest tests/unit/test_media_locator.py tests/unit/test_mediacrawler_refresh.py tests/unit/test_media_mux.py tests/unit/test_media_dash_downloader.py tests/unit/test_media_downloader.py tests/unit/test_cli.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/integration/test_bilibili_playable_pipeline.py tests/integration/test_bilibili_multipart_progressive_pipeline.py tests/integration/test_bilibili_dash_pipeline.py -q` | `PASS — 490 passed in 73.31s` |
| 单 P progressive 备用 → Emby | `uv run pytest -q tests/integration/test_bilibili_playable_pipeline.py` | 文档收尾复验 `1 passed in 1.45s`（实现运行 `1.64s`） |
| 多分 P progressive 备用 → Emby | `uv run pytest -q tests/integration/test_bilibili_multipart_progressive_pipeline.py` | 文档收尾复验 `1 passed in 1.70s`（实现运行 `1.95s`） |
| DASH 故障切换兼容 | `uv run pytest -q tests/integration/test_bilibili_dash_pipeline.py` | 文档收尾复验 `1 passed in 1.87s`（实现运行 `2.11s`） |
| 完整套件 | `uv run pytest -q` | 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | 全部通过；290 个文件格式正确` |
| 严格 mypy | `uv run mypy --strict src` | 84 个源码文件无问题` |
| 字节编译与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | wheel 与源码包构建成功` |
| 文档与上游锁 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | 120 份 Markdown；2 个锁定 checkout` |
| Git/上游/diff 审计 | 显式状态、跟踪/runtime/upstream 与 diff 检查 | 跟踪 308；未跟踪 0；跟踪 runtime/upstream/dist 0；上游 diff 为 0；两个上游 dirty 数均为 0` |

不宣称运行过 coverage。

## Git 核对

计划 `0694934bc9230151a85c040a061d6e704dffc4fc` 与实现 `190488f77d1704492cc148b890d6f9ae16d84f84` 已推送并在本地 `main` 与 `origin/main` 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中。

## 登录与现网验收

| 验收行 | 结果 |
| --- | --- |
| 真人 Bilibili QR/Cookie 登录 | `NOT_RUN` |
| 登录态 progressive 详情/播放 API | `NOT_RUN` |
| 真实主/备用 bilivideo CDN 行为 | `NOT_RUN` |
| 真实 progressive 字节与生产 ffprobe | `NOT_RUN` |
| 真实 Emby/Jellyfin 扫描与播放 | `NOT_RUN` |

离线证据不能代表上述真人行、分段 `durl`、FLV、CDN 排序/竞速/缓存或完整 Bilibili 支持通过。
