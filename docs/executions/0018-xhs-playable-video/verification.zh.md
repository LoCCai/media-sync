[English](verification.md) | **中文**

# 执行 0018 验证记录

- 状态：离线实现与文档门禁通过；真人验收 `NOT_RUN`
- 日期：2026-09-01
- 计划提交：`c9d3586`
- 实现提交：`356e254`

## 选型证据

| 候选 | 锁定证据 | 决策 |
| --- | --- | --- |
| 小红书视频 | `store/xhs/__init__.py` 输出 origin-key 或 H.264 `video_url`；media-sync 已能归一化 VIDEO、刷新小红书并探测/归档/发布视频。 | 本轮实现 |
| 贴吧静态图片 | `TiebaNote` 无媒体字段；首楼 API/HTML 媒体在 JSONL 前被丢弃，且防盗链字段需要冻结的脱敏夹具。 | 后续集成 shim |
| 知乎静态图/视频 | `ZhihuContent` 只保留文本/落地页 URL；HTML 图片属性及嵌套可播放视频结构在 JSONL 前被丢弃。 | 后续集成 shim |

## 实现证据

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 锁定上游源码形状 | `PASS` | 合约先校验锁定 checkout，再通过 AST 提取并执行真实小红书 store 函数，覆盖 `origin_video_key`、`originVideoKey`、H.264 `master_url`、逗号标量视频及标量图片输出。 |
| 小红书初始媒体 locator | `PASS` | 普通有界 HTTP/HTTPS、严格 LDH/IDNA 小红书 CDN host、默认端口及非根路径用例通过；userinfo、空白/控制字符、fragment、畸形/外域/自定义端口用例关闭失败；重定向继续使用既有逐跳公网策略。 |
| 自动作者视频目标 | `PASS` | 精确一个 raw 标量 VIDEO 与零或一个 raw 标量 IMAGE 一一映射为普通 `type="video"` VIDEO/MIXED 内容；重复、空分段、空白、畸形+有效列表、多候选、容器漂移及身份漂移均被拒绝。 |
| 进程与刷新合约 | `PASS` | 真实隔离 fake checkout 证明有界 creator 模式、精确 URL 选择、DEFAULT profile、成功清理及 repr-safe 权限处理；显式精确 note 兼容路径保持不变。 |
| 视频有效性 | `PASS` | 内嵌真实 H.264 MP4 通过生产 `FFprobeMediaProbe`；该证据与确定性记录型 probe 组合相互独立。 |
| 下载/归档/Emby 组合 | `PASS` | 精确 SQLite 来源、作者查找、mock 公网 DNS/HTTP、受控 MP4/PNG、SHA-256 归档及幂等 `.mp4`/poster/NFO/source 发布通过；仅 query 变化的重放不新增 detail、DNS、HTTP、probe、归档或导出工作。 |
| 持久与瞬态边界 | `PASS` | 持久 raw、Asset hint、SQLite、归档元数据、Emby 输出及已完成 attempt 清理均不保留签名 query、userinfo 或 fragment；`.upstream` 保持干净且未跟踪。 |

## 测试与质量门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 编辑前七文件基线 | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/integration/test_asset_download_orchestration.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_pipeline_runtime.py tests/integration/test_xhs_creator_authority_pipeline.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `167 passed in 46.50s` |
| 九文件专项 pytest | `uv run pytest -q tests/contract/test_mediacrawler_detail_refresh.py tests/contract/test_xhs_upstream_video_store.py tests/integration/test_asset_download_orchestration.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_mediacrawler_download_runtime.py tests/integration/test_pipeline_runtime.py tests/integration/test_xhs_creator_authority_pipeline.py tests/integration/test_xhs_playable_video_pipeline.py tests/unit/test_mediacrawler_refresh.py` | `PASS` — `222 passed in 43.69s` |
| 锁定上游源码合约 | `uv run pytest -q tests/contract/test_xhs_upstream_video_store.py` | `PASS` — `4 passed` |
| 真实 H.264 + 上游 + 组合 | `uv run pytest -q tests/contract/test_xhs_upstream_video_store.py tests/integration/test_xhs_playable_video_pipeline.py` | `PASS` — `6 passed in 8.84s` |
| 完整套件 | `uv run pytest -q` | 唯一跳过：Windows POSIX mode-bit |
| Ruff | `uv run ruff check .` | `PASS` |
| 格式 | `uv run ruff format --check .` | `PASS` — `241 files already formatted` |
| 严格 mypy | `uv run mypy src/media_sync` | `PASS` — `80 source files` |
| 字节编译 | `uv run python -m compileall -q src/media_sync` | `PASS` |
| 上游锁 | `uv run python scripts/check_upstreams.py` | 两个 checkout |
| 构建 | `uv build` | wheel 与 sdist |
| 文档 | `uv run python scripts/check_docs.py` | 检查 88 个 Markdown 文件 |
| Diff 检查 | `git diff --check`; `git diff --cached --check` | `PASS` |
| 独立最终审查 | 只读审查及专项回归 | 未发现 P0–P2 问题 |

不宣称运行过 coverage。

## 保留产物与 Git 审计

最终只读 PowerShell 审计运行 `git ls-files`、`git ls-files --others --exclude-standard`、`git ls-files -- archive exports jobs .media-sync dist .upstream`，递归统计被忽略的 `.media-sync`/`dist` 下真实文件，以 `Test-Path` 检查两个冻结 sentinel 根，并统计两个锁定上游的 `git -C <checkout> status --short`。审计只打印计数，不打印保留值或命中路径。结果：`tracked=259`；`untracked=0`；`tracked_runtime_upstream=0`；`runtime_and_build_files=914`；`sentinel_roots_preserved=2/2`；`mediacrawler_dirty_paths=0`；`bili_sync_up_dirty_paths=0`。

## 真人在线验收

| 验收行 | 结果 |
| --- | --- |
| 真人小红书 QR/Cookie 登录 | `NOT_RUN` |
| 真实 creator/feed/detail 查找 | `NOT_RUN` |
| 真实小红书 CDN 视频/封面字节 | `NOT_RUN` |
| 真实 Emby/Jellyfin 扫描/播放 | `NOT_RUN` |

离线 mock 不代表这些行通过。Execution 0018 只完成一条普通 `type="video"` 行、精确一个 VIDEO 与零或一个静态 IMAGE；多视频、多图片、更广混合/实况/动图形状、其余平台及更大的用户目标仍需继续推进。
