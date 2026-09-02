[English](verification.md) | **中文**

# 执行 0021 验证记录

- 状态：冻结离线范围通过全部最终门禁；登录/现网验收 `NOT_RUN`
- 日期：2026-09-02
- 前置：`e5d871050cdf25da1a51e2f057ba317dea2cffb1`
- 计划提交：`5095ed6e803a8a2f0a3134e756dd3e101fef10bd`
- 实现提交：`e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7`

## 前置基线

| 检查 | 结果 |
| --- | --- |
| Execution 0020 专项回归 | `PASS — 368 passed in 41.18s` |
| Execution 0020 完整套件 | `PASS — 1650 passed, 1 skipped in 310.82s` |
| 质量/构建/文档/上游/审计 | `PASS` |
| 真实双图响应形状观察 | 仅作为瞬态有界证据通过` — no body or signed value retained / 未保留正文或签名值 |

## 已实现证据

| 范围 | 结果 |
| --- | --- |
| 精确双图捕获与单图兼容 | 独立 v2 有序列表；v1 字符串不变；双重声明、重复持久身份及三张以上拒绝 |
| 锁定丢失边界与并发 | 锁定 extractor 仍丢失两个 locator；精确对象跨 gather-child → parent-store 携带及并发隔离已证明 |
| 有序 ARTICLE + 两项 IMAGE 归一化 | 精确 `<note_id>:image:0/1`；两个私有字段递归移除；只保留互异无 query hint |
| Position 0/1 详情刷新与漂移拒绝 | 完整持久 gallery 绑定到刷新上下文；要求当前完整顺序/hint；缺图、重排、替换及双重声明拒绝 |
| 无凭据传输与静态门 | 两个 URL 均使用无 Cookie/Authorization/Referer/Origin 的 DEFAULT profile；生产贴吧静态门接受已测 JPEG/PNG |
| 双图 SQLite/归档/Emby 组合 | 两次精确下载与 SHA-256 归档；poster/backdrop/两项 gallery/body/NFO/source；query 重放不新增 detail/DNS/HTTP/archive/export 工作 |
| 保留状态边界 | SQLite/runtime/work/archive/export/library 整树断言不保留私有字段或任何 `tbpicau` token/value |

## 测试与质量门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 实现专项回归 | `uv run pytest -q tests/unit/test_tieba_media.py tests/contract/test_tieba_upstream_first_floor_media.py tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_mediacrawler_ingestion.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_tieba_first_floor_image_pipeline.py tests/integration/test_asset_download_orchestration.py` | `PASS — 413 passed in 44.50s` |
| 锁定贴吧源码合约 | `uv run pytest -q tests/contract/test_tieba_upstream_first_floor_media.py` | `PASS — 6 passed in 3.42s` |
| 双图 SQLite→Emby 组合 | `uv run pytest -q tests/integration/test_tieba_first_floor_image_pipeline.py` | `PASS — 2 passed in 1.94s` |
| 完整套件 | `$env:PYTHONDONTWRITEBYTECODE='1'; uv run pytest -q -p no:cacheprovider` | 跳过项为 Windows 不适用的 POSIX mode-bit 边界 |
| Ruff 与格式 | `uv run ruff check .`; `uv run ruff format --check .` | 全部通过；262 个文件格式正确` |
| 严格 mypy | `uv run mypy --strict src` | 82 个源码文件无问题` |
| 字节编译与构建 | `uv run python -m compileall -q src/media_sync`; `uv build` | wheel 与源码包构建成功` |
| 文档与上游锁 | `uv run python scripts/check_docs.py`; `uv run python scripts/check_upstreams.py` | 100 份 Markdown；2 个锁定 checkout` |
| Git/上游审计 | 显式状态、跟踪/未跟踪/runtime/upstream 与 diff 检查 | 跟踪 280；未跟踪 0；跟踪 runtime/upstream 0；两个上游 dirty 数均为 0` |

不宣称运行过 coverage。

## Git 核对

实现 `e0fb8d572c8f5535a5495c2dfbf5b9cdf78461e7` 已在本地 `main`、`origin/main` 与 GitHub 间核对一致。包含本记录的提交即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中。

## 登录与现网验收

| 验收行 | 结果 |
| --- | --- |
| 真人贴吧 QR/Cookie 登录 | `NOT_RUN` |
| 登录态作者/详情 gallery | `NOT_RUN` |
| 未来真实 CDN 字节/重定向行为 | `NOT_RUN` |
| 真实 Emby/Jellyfin 扫描/展示 | `NOT_RUN` |

离线证据不能代表上述真人行通过；三张及以上图片与完整贴吧 gallery/媒体支持也不在本执行范围内。
