[English](verification.md) | **中文**

# 执行 0020 验证记录

- 状态：冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- 日期：2026-09-02
- 前置：`431fd855dafce502e83f74a055a4b27ae5c6f40b`
- 计划提交：`df7a38a6f9beee35c6c19336260b512ebc87ce0d`
- 实现提交：`8a0e935624e944809af1a56b0f02186686433d95`

## 选型证据

| 候选 | 证据边界 | 决策 |
| --- | --- | --- |
| 作者普通主题首楼精确一张静态 IMAGE | 锁定 `page_pc` 把完整 `first_floor.content` 交给 extractor；当前公开响应会暴露一个含 `origin_src` 的整数 type-3 项；现有文本 extractor 会在 JSONL 前丢弃它。 | 已交付 |
| 首楼多图 gallery | 真实审计行中存在多个 type-3 项，但顺序、替换与部分刷新语义属于独立范围。 | 延期 |
| 视频/语音/表情/链接/富卡片 | 当前响应存在其他整数 content type，其精确 schema 与 Emby 语义尚未冻结。 | 延期 |
| 回复/评论媒体 | 本执行只拦截 `first_floor` 主题详情与主题 JSONL 存储。 | 延期 |

## 当前响应只读证据

以下证据于 2026-09-02 瞬态产生，仅保留摘要，不保留响应正文、个人数据、签名 query 值或保存夹具。它可用于冻结当前合约，但不是可复现离线测试，也不验收登录流程或未来平台行为。

| 检查 | 结果 |
| --- | --- |
| 匿名签名 `/c/s/pc/sync` | HTTP 200、`error_code=0`，瞬态返回公开 TBS |
| 有界 `page_pc` 样本扫描 | 请求 18 个候选 ID；观察到真实零图、单图与双图行；未保留正文 |
| 单图 item 键 | 观察到上述键 |
| Origin 权限 | HTTPS 精确 host、规范路径、唯一 query 键 |
| 带签名 DEFAULT-profile 字节检查 | 仅观察请求通过` — HTTP 200 `image/jpeg`, 65,144 bytes, JPEG magic |
| 无 query 对照 | 风险证据通过` — HTTP 200 `image/jpeg`, 4,262 bytes, different body length; HTTP success alone is insufficient / 字节长度不同；仅 HTTP 成功不足以作为验收 |

## 已实现离线证据

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 锁定丢失边界 | `PASS` | 校验精确锁定 SHA；真实 extractor/model/update/JSONL 对象执行并证明未安装 shim 的行会丢失 type-3 locator。真实模型可携带并消费私有对象绑定，且不会通过 dump/JSON/repr 暴露；`.upstream` 保持干净。 |
| 当前 type-3 门 | `PASS` | 冻结门只接受有界文本加精确单图列表、精确十键整数 type-3 结构、严格标量边界与签名 `origin_src`；零图/多图/其他/drift 形状不产生合格 Asset。 |
| 精确对象捕获 | `PASS` | 已通过模块来源、完整/幂等安装、部分/marker/字段冲突拒绝、精确对象匹配、gather-child → parent-store 携带、仅嵌套 store 的 `ContextVar` 及并发隔离验证。 |
| 定时作者上限 | `PASS` | `max_items=23` 形成 `20 + 3` 详情与 callback 批次、精确 23 条成功行、一次页间 sleep，无第三次请求或达到上限后的 sleep；空页/短非终止页、重复、畸形及身份/基数漂移关闭失败。 |
| 归一化与持久身份 | `PASS` | ARTICLE 增加精确一个 position 0 的 `<note_id>:image:0` IMAGE；私有字段递归移除，SQLite/raw/archive/export 只保留无 query 的 scheme/authority/path 身份；历史零图 ARTICLE 行保持兼容。 |
| 精确详情刷新 | `PASS` | SQLite canonical 主题 URL 是唯一详情权限；refresh context、父请求与 child loader 复核其身份，上游实际接收 `TIEBA_SPECIFIED_ID_LIST=[<note_id>]`；唯一精确 ARTICLE/IMAGE/hint 匹配以无凭据 DEFAULT profile 返回新校验的签名 locator。 |
| 静态字节门 | `PASS` | 贴吧 IMAGE 自动启用生产有界结构门；合格 JPEG/PNG/WebP 通过，GIF/APNG/animated WebP/AVIF 失败；normal、recovery 与 takeover 准备链保留 `require_static_image=True`。该门不是完整像素解码。 |
| SQLite/归档/Emby 组合 | `PASS` | 精确来源、fake detail、mock 公网 DNS/HTTP、无 Cookie/Authorization/Referer/Origin 的 DEFAULT profile、生产字节门、SHA-256 归档及 poster/backdrop/gallery/body/NFO/source 发布通过。仅 query 变化的重放不新增 detail/DNS/HTTP/archive/export 工作；SQLite/WAL/SHM/runtime/archive/export 不保留私有字段或瞬态 `tbpicau`。 |

## 测试与质量门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 编辑前专项基线 | `uv run pytest -q tests/contract/test_mediacrawler_ingestion.py tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_asset_download_orchestration.py tests/integration/test_pipeline_runtime.py tests/unit/test_mediacrawler_refresh.py` | `PASS — 307 passed in 36.66s` |
| 上游锁 | `uv run python scripts/check_upstreams.py` | `PASS — Upstreams OK (2 locked checkouts verified)` |
| 上游工作树 | 及 bili-sync-up 对应命令 | 两者均干净` |
| 锁定贴吧源码合约 | `uv run pytest -q tests/contract/test_tieba_upstream_first_floor_media.py` | `PASS — 6 passed in 3.34s` |
| 隔离 SQLite→Emby 组合 | `uv run pytest -q tests/integration/test_tieba_first_floor_image_pipeline.py` | `PASS — 1 passed in 1.23s` |
| 实现专项回归 | `uv run pytest -q tests/unit/test_tieba_media.py tests/contract/test_tieba_upstream_first_floor_media.py tests/integration/test_tieba_first_floor_image_pipeline.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_asset_download_orchestration.py` | `PASS — 368 passed in 41.18s` |
| 完整套件 | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff | `uv run ruff check .` | 全部检查通过` |
| 格式 | `uv run ruff format --check .` | `PASS — 258 files already formatted` |
| 严格 mypy | `uv run mypy src/media_sync` | 82 个源码文件无问题` |
| 字节编译 | `uv run python -m compileall -q src/media_sync` | `PASS` |
| 构建 | `uv build` | wheel 与源码包构建成功` |
| 文档 | `uv run python scripts/check_docs.py` | 已检查 96 个 Markdown 文件` |
| Diff/保留产物审计 | 加显式 Git、保留树与上游审计 | 跟踪 276；未跟踪 0；跟踪 runtime/upstream 0；跟踪 upstream 0；保留产物文件 3；贴吧保留 marker 命中 0；两个上游 dirty path 计数均为 0` |

不宣称运行过 coverage。

## Git 核对

实现提交 `8a0e935624e944809af1a56b0f02186686433d95` 已在本地 `main`、`origin/main` 与 GitHub 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意不嵌入，推送后的核对结果在任务交接中报告。

## 登录与现网验收

| 验收行 | 结果 |
| --- | --- |
| 真人贴吧 QR/Cookie 登录 | `NOT_RUN` |
| 登录态作者枚举与精确详情 | `NOT_RUN` |
| 未来真实 CDN token/重定向/字节行为 | 已单独记录一次瞬态匿名观察 |
| 真实 Emby/Jellyfin 扫描/展示 | `NOT_RUN` |

离线 mock 与瞬态公开观察均不能代表这些验收行通过。Execution 0020 仅限一个冻结的普通首楼静态图片切片。
