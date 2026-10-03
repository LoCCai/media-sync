[English](verification.md) | **中文**

# 验证：抖音创作者作品耐久交付（0080）

计划基线：本目录中冻结的计划（提交 `d5cddd8`）。实现记录于本切片的 `feat` 提交。

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 抖音扫描状态单元测试 | `PASS` | `tests/unit/test_douyin_creator_work.py` → `9 passed`。规范游标往返、三个不透明游标步且只终结于真实 `has_more != 1`、空页停滞、访问受限 ≠ 源末、单元上限见证保留、失败详情隔离、头部漂移重开对账、绑定变更拒绝、上游页大小 18。 |
| 续传策略单元测试 | `PASS` | `tests/unit/test_douyin_scan_continuation.py` → `5 passed`。封闭延迟域（0/60…604800）、有界默认值、畸形上游 SHA 拒绝、锁缺失时失败关闭回退。 |
| 捕获 shim 契约测试 | `PASS` | `tests/contract/test_douyin_creator_capture.py` → `8 passed`。页解析器把列表缩减为有界身份（无 `desc` 泄漏）、歧义进度拒绝（字符串 `has_more`、越界值、畸形/重复 `aweme_id`）、shim 封印 coverage 且失败详情隔离、被拒 store 写入隔离、列表受限以 `access_restricted` 阻塞且无源末。 |
| 摄取集成 | `PASS` | `tests/integration/test_douyin_creator_work_ingestion.py` → `3 passed`。单事务页/游标/Run/内容发布与零工作重放；访问受限不提交任何耐久状态但记录停止原因；未被封印页证明的记录被拒绝且无状态变化。 |
| 迁移往返 | `PASS` | `tests/integration/test_douyin_creator_work_migration.py` → `3 passed`。默认为空的升级恰好新增 `douyin_subscription_progress`，元数据/迁移形状一致，拒绝历史且要求授权的下线。 |
| 交付转移 | `PASS` | `tests/integration/test_douyin_creator_work_delivery.py` → `3 passed`。backfill 源末产生证据三元组并把订阅游标切到头部泳道；一次稳定头部对账将基线闭合为增量并带 `baseline_snapshot_complete`；受限列表单元以固定 `douyin_access_restricted` 阻塞；终端管线失败以精确码阻塞。 |
| 头修订钉定回归更新 | `PASS` | `test_packaged_migrations`（14 passed；wheel 同时携带 0015 与 0016）、`test_cli`（修订/表数 26）、`test_support_bundle`、`test_api_support_bundle`、`test_offline_media_pipeline`、`test_scheduled_offline_pipeline`、`test_deployment_provenance`（允许名单补全 0015 + 0016）。 |
| 静态门禁 | `PASS` | Ruff format/check 在 `src tests` 全绿；严格 mypy：`Success: no issues found in 165 source files`；`compileall` 干净；`scripts/check_docs.py` OK（800 文件）；`scripts/check_upstreams.py` OK（2 个锁定检出）；`uv build` 产出 wheel。 |
| 完整 Python 套件 | `PASS` | 最终树上 `7185 passed, 42 skipped, 1 warning in 1492.01s（约 25 分钟）`（42 个跳过为既有 Windows/POSIX 与 PostgreSQL-URL 资质分支）。 |
| Docker 镜像 / Linux 门禁 | `NOT_RUN` | 0077 交接下的操作员侧工作；不主张任何部署。 |
| 真人抖音登录、真人创作者金丝雀、驻留进程重启 | `NOT_RUN` | 未使用任何平台凭据或真人爬虫；按冻结计划留待操作员执行。 |

## 源码追踪记录（计划第 1 步）

- 分页：`/aweme/v1/web/aweme/post/` 携带 `sec_user_id`、固定 `count: 18`、服务端回显字符串 `max_cursor`（起始为空），响应为整数 `has_more` + `max_cursor` + `aweme_list`（`client.py::get_user_aweme_posts`）。
- 上游停止：`while posts_has_more == 1`——`has_more != 1` 是唯一真实结束；`aweme_list` 为空而 `has_more == 1` 毫无进展（建模为 `empty_page_stalled`）。
- 签名：每请求经钉定 `douyin.js` 在 Playwright 页上生成 `a_bogus`（`client.py` 请求前钩子）；子 shim 把它保持在钉定运行时内。
- 封禁模型：空或字面 `"blocked"` 响应体抛 `account blocked` 并包进 `DataFetchError`；`IPBlockError` 标记限流。两者都是访问受限，绝不是源末。
- 身份/媒体：创作者 `sec_user_id` 来自 `parse_creator_info_from_url`；作品详情经 `get_video_by_id` 返回 `aweme_detail`；媒体分支 `_extract_note_image_list`（图集）与 `_extract_video_download_url`（视频）。

## 已运行命令

```text
uv run pytest -q tests/unit/test_douyin_creator_work.py tests/unit/test_douyin_scan_continuation.py
uv run pytest -q tests/contract/test_douyin_creator_capture.py
uv run pytest -q tests/integration/test_douyin_creator_work_ingestion.py tests/integration/test_douyin_creator_work_migration.py tests/integration/test_douyin_creator_work_delivery.py
uv run pytest -q   # 最终树完整套件
uv run ruff format src tests && uv run ruff check src tests
uv run mypy --strict src
uv run python -m compileall -q src
uv run python scripts/check_docs.py
uv run python scripts/check_upstreams.py
uv build
git diff --check
```

## 给评审者的设计说明

- **为什么 shim 锚定工作目录。** 子进程先验证 checkout（`verify_manifest_checkout`）并 `os.chdir` 进入其中，之后才安装 shim；把根再经参数传递会重新引入扫描器正确标记为路径穿越入口的 argv 派生污点。因此 shim 从 `Path.cwd()` 派生根，只对输出根做游标段校验。
- **为什么列表级与详情级失败不同。** 列表失败意味着 feed 端点本身拒绝或失败——状态机以 `access_restricted` 阻塞（绝不是源末）。详情失败只隔离该作品（`detail_unavailable`），保留页见证，让无关作品继续交付——符合按 Content 可见性契约。
- **为什么 `max_cursor` 只封装不解析。** 抖音回显不透明的服务端游标；任何解释它的尝试都会招致漂移。状态机把它逐字存入规范的 `dy-work-v1:` 信封，并在每次加载时重新校验绑定。
