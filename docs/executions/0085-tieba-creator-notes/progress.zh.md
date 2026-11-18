[English](progress.md) | **中文**

# 进展：贴吧创作者主题耐久交付

状态：本地已实现并验证。未部署，未使用真人账户或平台请求。

## 结果

一个贴吧创作者订阅现在拥有与 B 站（0074）、小红书（0076）、抖音（0080）、快手（0081）、微博（0084）相同的耐久链，且每条规则都从钉定贴吧源码重新推导。

```text
/crawler/ 原生登录
  -> 把已保存的贴吧会话认领到一个 Account
  -> 添加一个创作者主题 Subscription
  -> 带页见证的有界 1 起页码批次
  -> 身份把守的详情抓取与已验证交付
  -> 服务端声明结束后的头部对账
  -> 面向新主题的增量头部检查
```

## 已实现

1. **迁移 `0019_tieba_creator_notes`** 创建 `tieba_subscription_progress`，沿用 0015–0018 纪律：封闭 `phase` 白名单、四个固定停止原因、计数范围、交付/源末/对账全有或全无三元组、`last_page_number` 范围、`blocked_code` 当且仅当 `blocked`，以及受护栏下线。
2. **`tieba_creator_work.py` 扫描状态机。** `TiebaWorkIdentity`（`thread_id` + 列表摘要）、`TiebaPageWitness`（1 起 `page`、`has_more`、页身份）、不透明 `tb-work-v1:` 游标，以及基于重复身份元组的停滞检测——由于页码总是递增，这是唯一可用信号。
3. **`tieba_creator_capture.py` 子进程 shim。** 只替换 `get_all_notes_by_creator_url`，调用 `get_notes_by_creator_portrait(portrait, pn, rn=20)` 与 `get_note_by_id`，把非零 `error_code`、畸形响应体、`DataFetchError`/`IPBlockError` 或任何传输失败映射为 `access_restricted` 而非源末。0020–0022 首楼图片 shim 继续产出相同冻结形状。
4. **Bridge/runner 接线。** `RunnerManifest.tieba_scan` / `tieba_scan_input_cursor` 与其他五个有界契约互斥并在 manifest 中往返；`BridgeRequest` 接受标志与游标；`runner.py` 在媒体捕获之后安装 shim。
5. **调度面。** `tieba_delivery_progress.py`、`tieba_scan_continuation.py`（默认 300 秒，两服务一致）、`MEDIA_SYNC_TIEBA_SCAN_CONTINUATION_DELAY_SECONDS` 设置、`ingest_tieba_bounded`、管线 worker 发布、调度物化、handler 创作者绑定、订阅详情 `tieba_delivery`，以及 CLI/doctor/job-diagnostics 修订允许名单推进到 `0019_tieba_creator_notes`。

## 验证

- `tests/unit/test_tieba_creator_work.py`（12 项）：游标往返与绑定拒绝、四种停止原因、页尾回放、停滞阻塞、头部对账、覆盖 JSON 往返、有界页/主题形状。
- `tests/contract/test_tieba_creator_capture.py`（10 项）：页解析隐私、六种漂移形状被拒、空页作为有效页接受、覆盖封印、受限 feed ≠ 源末。
- `tests/integration/test_tieba_creator_notes_delivery.py`（3 项）：服务端结束 → 对账 → 增量并记录 `last_page_number`、受限阻塞码、终态失败阻塞码。
- 头修订钉定测试已推进：打包迁移携带 `0019`、域表包含 `tieba_subscription_progress`、CLI 预期/已知修订与表计数（29）已更新。

## 未完成

- 部署、Linux 主机门禁、真人贴吧登录与任何真实请求保持 `NOT_RUN`。
