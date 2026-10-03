[English](progress.md) | **中文**

# 进展：抖音创作者作品耐久交付

状态：本地实现已完成并离线验证。部署、Linux 验证与任何真人采集仍未开始。

## 结果

一个精确的抖音创作者订阅现在携带与 Bilibili（0074）、小红书（0076）相同的耐久交付链，全部从钉定抖音源码推导：

```text
/crawler/ 原生登录
  -> 把已保存的抖音会话认领到一个 Account
  -> 添加一个创作者作品 Subscription
  -> 有界、max_cursor 跟踪的历史批次（每页 18 条）
  -> 按作品身份把守的详情抓取与已验证交付
  -> 真实 has_more != 1 之后的头部对账
  -> 面向新作品的增量头部检查
```

## 已实现

1. **迁移 `0016_douyin_creator_work`** 创建 `douyin_subscription_progress`，约束纪律与 0015 相同：封闭 `phase` 白名单、四个固定停止原因、计数范围、交付/源末/对账三组全有或全无证据三元组、`blocked_code` 当且仅当 `blocked`、受护栏下线（在线审计、PostgreSQL `ACCESS EXCLUSIVE`、SQLite exclusive-maintenance 证明、历史拒绝）。
2. **`douyin_creator_work.py` 扫描状态机。** `DouyinWorkIdentity`（数字 `aweme_id` + 列表摘要）、`DouyinPageWitness`（回显 `max_cursor` + 页尾见证）、`DouyinScanUnit`/`DouyinScanCoverage` 携带四种停止原因：只有 `has_more != 1` 可 qualified 为源末候选；`aweme_list` 为空而 `has_more == 1` 是 `empty_page_stalled`；风控与抓取失败是 `access_restricted`；单元 `max_items` 上限是 `unit_cap_reached`。游标在不透明 `dy-work-v1:` 命名空间下规范往返并拒绝任何绑定变更。
3. **`douyin_creator_capture.py` 子进程 shim。** 只替换 `DouYinCrawler.get_creators_and_videos` 为一个按页界定的单元，走 `get_user_aweme_posts`/`get_video_by_id`，所有文件系统访问锚定在已验证的工作目录（绝不来自 manifest 字段），权威细节只留在子进程内存，并在输出根封印一行 coverage JSONL。列表级抓取失败（`DataFetchError`/`IPBlockError`）限制整个 feed；详情级失败只隔离该作品。
4. **Bridge/runner 接线。** `RunnerManifest.douyin_scan`/`douyin_scan_input_cursor` 与 Bili/XHS 契约互斥、绑定校验、双向规范序列化往返，以及 runner 在 checkout 验证后安装 shim 的 `dy` 分支。
5. **调度面接线。** `douyin_scan_continuation.py`（默认 300 秒，经 `MEDIA_SYNC_DOUYIN_SCAN_CONTINUATION_DELAY_SECONDS`，两服务一致）、`douyin_delivery_progress.py`（绑定/仓储/载荷）、`ingest_douyin_bounded` 单事务页发布、管线 worker 的成功/终端失败发布、调度仓储物化互斥，以及订阅详情 `douyin_delivery` 载荷。
6. **期望修订推进。** `cli.py` 钉定、`job_diagnostics` 迁移列表、doctor `douyin_delay_seconds` 与迁移允许名单现在携带 `0016_douyin_creator_work`。

## 验证摘要

26 个新测试通过：9 单元（游标/停止原因/漂移）、8 契约（解析隐私、shim 封印、受限 ≠ 源末）、3 摄取集成（单事务游标/内容、受限零提交、未证明记录拒绝）、3 迁移（空升级、元数据一致、护栏下线）、3 交付转移（backfill → 源末 → 对账 → 增量、受限阻塞、终端失败）。所有头修订钉定测试（打包迁移、CLI、support bundle、离线/调度管线、部署来源）干净推进到 `0016_douyin_creator_work`；完整套件与剩余门禁记录于 `verification.md`。

## 尚未完成

- 带镜像身份的部署重建、Linux 门禁与 XHS 金丝雀仍是操作员侧工作（`0077` 交接 + `next-delivery.md`）。
- 真人抖音登录、真实创作者金丝雀与驻留进程重启验证保持 `NOT_RUN`。
