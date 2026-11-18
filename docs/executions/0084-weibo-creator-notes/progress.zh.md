[English](progress.md) | **中文**

# 进展：微博创作者笔记耐久交付

状态：本轮会话中实现完成。未部署，未使用真人账户或平台请求。

## 已实现

1. **迁移 `0018_weibo_creator_notes`** 创建 `weibo_subscription_progress`，沿用 0015–0017 的约束纪律：封闭 `phase` 白名单、四个固定停止原因（`total_inferred_end`、`empty_page_end`、`access_restricted`、`unit_cap_reached`）、计数范围、交付/源末/对账三组全有或全无证据三元组、`blocked_code` 当且仅当 `blocked`、`declared_total` 范围与受护栏下线。
2. **`weibo_creator_work.py` 扫描状态机。** `WeiboWorkIdentity`（`mblog.id` + 列表摘要）、`WeiboPageWitness`（回显 `since_id`、`declared_total`、页身份）、`WeiboCreatorPage.ends_after(pages)` 精确镜像上游算术（`total > 10 * pages`），以及 `wb-work-v1:` 不透明命名空间下的 `WeiboScanState`/`WeiboScanUnit`/`WeiboScanCoverage`。推断结束保留声明 total、已消耗页数与首页见证，因此永不被当作完整。
3. **`weibo_creator_capture.py` 子进程 shim。** 只替换 `WeiboCrawler.get_creators_and_notes`，调用钉定 `get_notes_by_creator(creator_id, "107603<uid>", since_id)` 与 `get_note_info_by_id`，按 `card_type == 9` 过滤，并把假值响应体或缺失 `cards` 键映射为 `access_restricted` 而非源末。0016/0031/0035/0036 媒体 shim 继续产出相同的冻结形状。
4. **Bridge/runner 接线。** `RunnerManifest.weibo_scan` / `weibo_scan_input_cursor` 与其他四个有界契约互斥、双向校验并在 manifest 中往返；`BridgeRequest` 接受标志与游标；`runner.py` 安装 shim。
5. **调度接线。** `weibo_delivery_progress.py`（绑定、载荷、回执栅栏、四阶段迁移、停滞/受限阻塞码）、`weibo_scan_continuation.py`（默认 300 秒，`MEDIA_SYNC_WEIBO_SCAN_CONTINUATION_DELAY_SECONDS`）、`ingest_weibo_bounded`、管线 worker 成功/终态发布、调度仓储物化、handler 创作者绑定/策略指纹/有界请求、订阅详情 `weibo_delivery` 载荷，以及 CLI/doctor/job-diagnostics 迁移允许名单推进到 `0018_weibo_creator_notes`。

## 已完成的验证

- `tests/unit/test_weibo_creator_work.py`（14 项）：游标往返与绑定拒绝、四种停止原因、页尾回放、停滞阻塞、头部对账、覆盖 JSON 往返、推断结束与完整性区分。
- `tests/contract/test_weibo_creator_capture.py`（11 项）：页解析隐私、漂移拒绝、覆盖封印、受限列表 ≠ 源末、完整页到达算术结束。
- `tests/integration/test_weibo_creator_notes_delivery.py`（4 项）：推断结束 → 对账 → 增量、受限阻塞码、停滞阻塞码、终态失败阻塞码。
- 头修订钉定测试已推进：打包迁移包含 0018、数据库域表、CLI 预期/已知修订、表计数、离线/调度管线修订断言。

## 收尾结果

- Python 完整套件 `7257 passed, 63 skipped, 108 warnings`。
- Ruff lint/format 通过；strict mypy 174 个源文件通过；文档与上游检查通过；Web `30 files / 843 tests`、Svelte check 与 Prettier 通过。

部署、真人微博登录与任何真实请求保持 `NOT_RUN`。
