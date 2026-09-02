[English](verification.md) | **中文**

# 执行 0019 验证记录

- 状态：冻结离线范围通过全部最终门禁；真人验收 `NOT_RUN`
- 日期：2026-09-02
- 前置：`4fb639a`
- 计划提交：`dc1714c`
- 实现提交：`2edb9d763b4948c56cc182bcc5012914bcb644d1`

## 选型证据

| 候选 | 决策 | 证据边界 |
| --- | --- | --- |
| 作者普通回答精确一张静态 IMAGE | 已交付 | 锁定上游已接收回答 HTML，但会在 JSONL 前丢失图片属性；校验 shim 捕获冻结单图形状并成功约束作者执行。 |
| 回答多图 gallery | 延期 | 顺序、编辑/替换及部分捕获语义属于独立范围。 |
| 文章媒体 | 延期 | 锁定默认 creator 路径关闭文章枚举。 |
| zvideo 播放/封面 | 延期，等待夹具 | 嵌套播放/封面形状尚未冻结，且没有真实脱敏夹具。 |

## 已实现离线证据

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 锁定上游丢失边界 | `PASS` | 校验锁定 SHA，执行真实 `extract_text_from_html`、回答 extractor/update/JSONL store，以 AST 绑定 `content` include、仅回答 dispatch、缺少原生上限及两个 child 安装点；真实锁定 Pydantic content 可携带/消费私有绑定且不会通过 dump/JSON/repr 暴露。 |
| 运行时 shim 与作者上限 | `PASS` | 精确对象绑定跨越 `asyncio.gather` child → 父存储且保持任务隔离。Scheduled `max_items=23` 产生页面大小 `20 + 3` 的两次 API 请求与两次 callback 调用，callback 精确处理 23 行，页间执行一次节奏 sleep；达到上限后没有第三次请求或额外 sleep。空页、短非终止页、重复页、畸形页与基数漂移均关闭失败。 |
| HTML 与 URL 门 | `PASS` | 已覆盖冻结属性优先级、重复/竞争候选拒绝、多图/可播放/容器漂移拒绝、严格正 ID 与有界 canonical URL，包括空 query/fragment 分隔符拒绝。 |
| 持久身份与刷新 | `PASS` | ARTICLE 加唯一 `<content_id>:image:0` IMAGE、递归私有字段移除、无 query SQLite hint、精确 canonical 回答权限、父/child/当前 locator 复核及无凭据 DEFAULT profile 均通过；历史无 Asset 回答保持兼容。 |
| 静态结构资格校验 | `PASS` | 知乎 IMAGE 自动启用生产门；合格 JPEG/PNG/WebP 通过，GIF/APNG/animated WebP/AVIF 失败；normal、recovery 与 takeover 路径保留该标志。该门是有界结构/容器资格校验，不是完整像素解码。 |
| SQLite/归档/Emby 组合 | `PASS` | 精确来源、fake detail、mock 公网 DNS/HTTP、生产字节门、SHA-256 归档、poster/backdrop/gallery/body/NFO/source 发布及仅 query 变化的零工作重放通过；SQLite/runtime/archive/export 与 WAL/SHM sidecar 均不含私有/瞬态值。 |

## 测试与质量门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 编辑前专项基线 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `255 passed in 48.32s` |
| 首次专项联合门 | `uv run pytest -q tests/unit/test_zhihu_media.py tests/contract/test_zhihu_upstream_answer_store.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_zhihu_answer_image_pipeline.py tests/contract/test_mediacrawler_bridge.py::test_full_history_acknowledgement_matches_audited_platforms` | `PASS` — `364 passed in 41.04s` |
| 首次隔离 SQLite→Emby 组合 | `uv run pytest -q tests/integration/test_zhihu_answer_image_pipeline.py` | `PASS` — `1 passed` |
| 最终扩大专项门 | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider tests/unit/test_zhihu_media.py tests/contract/test_zhihu_upstream_answer_store.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_zhihu_answer_image_pipeline.py tests/integration/test_zhihu_scheduled_creator_bound.py tests/unit/test_media_downloader.py tests/integration/test_asset_download_orchestration.py tests/unit/test_media_locator.py tests/contract/test_mediacrawler_bridge.py::test_full_history_acknowledgement_matches_audited_platforms` | `PASS` — `505 passed in 48.82s` |
| 完整套件 | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | `1543 passed, 1 skipped in 318.39s`；跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff | `uv run ruff check .` | 全部检查通过 |
| 格式 | `uv run ruff format --check .` | `PASS` — `250 files already formatted` |
| 严格 mypy | `uv run mypy src/media_sync` | 81 个源码文件无问题 |
| 字节编译 | `uv run python -m compileall -q src/media_sync` | `PASS` |
| 上游锁 | `uv run python scripts/check_upstreams.py` | 2 个锁定 checkout 已验证 |
| 构建 | `uv build` | wheel 与源码包构建成功 |
| 文档 | `uv run python scripts/check_docs.py` | `PASS` |
| Diff、保留产物与上游审计 | 加密钥哨兵、SQLite/WAL/SHM、保留目录及上游干净性检查 | tracked `268`；untracked `0`；tracked runtime/upstream `0`；runtime/build 文件 `914`；执行 0019 保留 marker 命中 `0`；冻结 sentinel 根 `2/2`；两个上游 dirty path 计数均为 `0` |
| 独立最终审查 | `uv run pytest -q tests/unit/test_zhihu_media.py tests/contract/test_zhihu_upstream_answer_store.py tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_asset_download_orchestration.py tests/unit/test_media_downloader.py tests/integration/test_zhihu_scheduled_creator_bound.py tests/integration/test_zhihu_answer_image_pipeline.py` | `461 passed in 44.33s`；未发现 P0/P1/P2 |

不宣称运行过 coverage。

## 源码绑定证据限制

锁定源码合约与合成 HTML 在无需网络时证明锁定拦截边界及冻结形状的确定性处理。当前没有真实脱敏知乎回答/API 夹具，因此证据不证明现网属性、creator/detail API 兼容性、真实 `zhimg.com` 重定向/profile 行为或每张图片的完整像素解码；它确实证明上述有界结构用例，包括拒绝已测试的 GIF、APNG、animated WebP 与 AVIF 字节。

## Git 与真人验收

实现提交 `2edb9d763b4948c56cc182bcc5012914bcb644d1` 已在本地 `main`、`origin/main` 与 GitHub 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意不嵌入，推送后的本地/tracking/GitHub 核对结果在任务交接中报告。

| 真人验收行 | 结果 |
| --- | --- |
| 真人知乎 QR/Cookie 登录 | `NOT_RUN` |
| 真人 creator 回答分页 | `NOT_RUN` |
| 真人回答详情查找 | `NOT_RUN` |
| 真实 `zhimg.com` 字节、重定向与 DEFAULT profile | `NOT_RUN` |
| 真实 Emby/Jellyfin 扫描/展示 | `NOT_RUN` |

离线 mock 不代表真人行通过。Execution 0019 只交付第六个媒体平台上一条普通回答中的精确一张静态 IMAGE；多图、文章、zvideo、完整知乎覆盖、贴吧媒体及更大的七平台目标仍需继续推进。
