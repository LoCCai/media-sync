[English](progress.md) | **中文**

# 进展：知乎创作者回答耐久交付

状态：本地已实现并验证。未部署，未使用真人账户或平台请求。

## 结果

一个知乎创作者订阅现在拥有与 B 站（0074）、小红书（0076）、抖音（0080）、快手（0081）、微博（0084）、贴吧（0085）相同的耐久链，且每条规则都从钉定知乎源码重新推导。

```text
/crawler/ 原生登录
  -> 把已保存的知乎会话认领到一个 Account
  -> 添加一个创作者回答 Subscription
  -> 带页见证的有界 offset 单元
  -> 身份把守的交付与已验证媒体
  -> 服务端声明结束后的头部对账
  -> 面向新回答的增量头部检查
```

## 已实现

1. **迁移 `0020_zhihu_creator_answers`** 创建 `zhihu_subscription_progress`，纪律与 0015–0019 相同：封闭 `phase` 白名单、四个固定停止原因、计数范围、交付/源末/对账全有或全无三元组、`last_offset` 范围、`blocked_code` 当且仅当 `blocked`，以及受护栏下线。
2. **`zhihu_creator_work.py` 扫描状态机。** `ZhihuWorkIdentity`（`content_id` + 列表摘要）、`ZhihuPageWitness`（offset、limit、`is_end`、身份）、不透明 `zh-work-v1:` 游标、按同一 offset 的页尾重放，以及通过比较页身份元组实现的**窗口位移检测**——客户端可选整数 offset 唯一能提供的信号。
3. **`zhihu_creator_capture.py` 子进程 shim。** 只替换 `get_all_anwser_by_creator`，调用 `get_creator_answers(url_token, offset, limit)`，把 extractor 的 `content_id` 顺序与原始 id 交叉校验，并把假值/畸形响应体、`DataFetchError`/`IPBlockError` 或传输失败映射为 `access_restricted` 而非源末。0033 图库 shim 继续产出相同冻结形状。
4. **Bridge/runner 接线。** `RunnerManifest.zhihu_scan` / `zhihu_scan_input_cursor` 与其他六个有界契约互斥并在 manifest 中往返；`BridgeRequest` 接受标志与游标；`runner.py` 在媒体捕获之后安装 shim。
5. **调度面。** `zhihu_delivery_progress.py`、`zhihu_scan_continuation.py`（默认 300 秒，两服务一致）、`MEDIA_SYNC_ZHIHU_SCAN_CONTINUATION_DELAY_SECONDS` 设置、`ingest_zhihu_bounded`、管线 worker 发布、调度物化、handler 创作者绑定、订阅详情 `zhihu_delivery`，以及 CLI/doctor/job-diagnostics 修订允许名单推进到 `0020_zhihu_creator_answers`。

## 验证

- `tests/unit/test_zhihu_creator_work.py`（13 项）：游标往返与绑定拒绝、四种停止原因、小上限单元行为、offset 重放、以 `zhihu_window_shifted` 阻塞位移窗口、头部边界复现、覆盖 JSON 往返、失败详情隔离、有界形状。
- `tests/contract/test_zhihu_creator_capture.py`（9 项）：页解析隐私、六种漂移形状被拒、覆盖封印、受限 feed ≠ 源末。
- `tests/integration/test_zhihu_creator_answers_delivery.py`（3 项）：`is_end` → 对账 → 增量并记录 `last_offset`、受限阻塞码、终态失败阻塞码。
- 头修订钉定测试已推进：打包迁移携带 `0020`、域表包含 `zhihu_subscription_progress`、CLI 预期/已知修订与表计数（30）已更新。

## 未完成

- 部署、Linux 主机门禁、真人知乎登录与任何真实请求保持 `NOT_RUN`。
