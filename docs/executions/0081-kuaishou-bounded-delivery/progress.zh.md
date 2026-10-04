[English](progress.md) | **中文**

# 进展：快手创作者作品耐久交付

状态：本地实现已完成，并经三岗工作流（后端工程师、前端美化工程师、bug 测试员）离线验证。部署、Linux 验证与任何真人采集仍未开始。

## 结果

一个精确的快手创作者订阅现在携带与 Bilibili（0074）、小红书（0076）、抖音（0080）相同的耐久交付链，全部从钉定快手源码推导：

```text
/crawler/ 原生登录
  -> 把已保存的快手会话认领到一个 Account
  -> 添加一个创作者作品 Subscription
  -> 有界、pcursor 跟踪的历史批次，带页尾重列
  -> 按作品身份把守的详情抓取与已验证交付
  -> 真实 no_more 回显或空页结束之后的头部对账
  -> 面向新作品的增量头部检查
```

## 已实现

1. **迁移 `0017_kuaishou_creator_work`** 创建 `kuaishou_subscription_progress`，沿用 0015/0016 的约束纪律：封闭 `phase` 白名单、四个固定停止原因（`no_more_echoed`、`empty_page_end`、`access_restricted`、`unit_cap_reached`）、计数器范围、全有或全无证据三元组、`blocked_code` 当且仅当 `blocked`、护栏下线。
2. **`kuaishou_creator_work.py` 扫描状态机。** `KuaishouWorkIdentity`（`photo.id` + 列表摘要）、`KuaishouPageWitness`（回显 `pcursor` + 页尾见证）、`KuaishouScanUnit`/`KuaishouScanCoverage`。两个源末候选分码：服务端回显 `no_more` 记 `no_more_echoed` 且优先；回显未携带哨兵的空 `feeds` 页是客户端推断的 `empty_page_end`。`max_items` 截断绝不推进 feed——单元以输入 `pcursor` 原样结束并保留页见证，下一单元同参重列、按稳定 `photo.id` 跳过已交付作品（页尾重列）。非空页上不前进的回显累计 `stalled_units`，超界以固定 `kuaishou_cursor_stalled` 码阻塞——这是上游从未有过的防护（client.py:416-448）。
3. **`kuaishou_creator_capture.py` 子进程 shim。** 只有列表请求走签名 REST 通道（`__NS_hxfalcon` 来自活页面环境、每次尝试重新生成、绝不离线构造）；详情与创作者资料走无签名 GraphQL 通道，绝不携带签名材料。shim 锚定在已验证的工作目录，权威细节只留子进程内存，输出根封印一行 coverage JSONL。列表级失败（假值响应体、`result != 1`、`DataFetchError`、传输错误）限制整个 feed；详情失败只隔离该作品。
4. **Bridge/runner 接线。** `RunnerManifest.kuaishou_scan`/`kuaishou_scan_input_cursor` 与 Bili/XHS/Douyin 契约互斥，`ks` runner 分支在 checkout 验证后安装 shim。
5. **调度/摄取/API 接线。** `kuaishou_scan_continuation.py`（默认 300 秒，经 `MEDIA_SYNC_KUAISHOU_SCAN_CONTINUATION_DELAY_SECONDS`，两服务一致）、`kuaishou_delivery_progress.py`、`ingest_kuaishou_bounded`、管线 worker 发布、调度物化四路互斥、订阅详情 `kuaishou_delivery` 载荷，CLI/doctor/迁移允许名单推进到 `0017_kuaishou_creator_work`。
6. **前端。** 订阅控制台现在渲染 0080 暴露的抖音投放面板，三个平台面板共用一个数据映射助手（0081 上线时第四个面板直接复用），并统一间距/层级/状态色语义。

## 验证摘要

经三岗运行：bug 测试员确认全量 pytest 绿（收集 7261 项；套件退出 0）、svelte-check、vitest、prettier 全部退出 0，路由修复后零发现；静态门禁（compileall/ruff/严格 mypy）经一轮修复后通过。细节见 `verification.md`。

## 尚未完成

- 带镜像身份的部署重建、Linux 门禁与 XHS 金丝雀仍是操作员侧工作（`0077` 交接 + `next-delivery.md`）。
- 真人快手登录、真人创作者金丝雀与驻留进程重启验证保持 `NOT_RUN`。
