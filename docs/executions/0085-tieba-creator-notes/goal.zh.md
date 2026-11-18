[English](goal.md) | **中文**

# 目标：贴吧创作者主题耐久交付

## 结果

一个精确的贴吧创作者订阅获得与其他六个平台相同的耐久交付链，且每条规则都从钉定贴吧源码重新推导。

## 为什么贴吧形状不同

在验证记录中重读并引用（`.upstream/MediaCrawler/media_platform/tieba/`）：

- 分页是签名 PC feed 端点 `/c/u/feed/myThread` 上的 **1 起页码**，参数 `pn` 与 `rn=20`（`client.py:684-710`）。没有不透明游标，也没有 `since_id`。
- 循环在 `max_note_count == 0 or len(result) < max_note_count` 时继续走页，页内无 thread id 时中断，`int(data.get("has_more") or 0)` 为假时中断（`client.py:790-830`）。
- 业务 `error_code != 0` 或畸形响应体会让上游记录并中断（`client.py:806-810`）；那不是源末。
- 创作者身份是从创作者 URL 提取的 `portrait`（`client.py:172-186`），主题身份是 `thread_info.tid`（或 `id`）（`help.py:240-250`）。

由于 `pn` 是始终递增的整数，重复页无法仅靠游标发现：耐久层必须比较页身份，并把不前进的页计为停滞。

## 必需行为

1. **页码游标。** 页码作为有界正整数，存放在不透明 `tb-work-v1:` 命名空间下，沿用其他四个平台相同的封闭 schema 往返纪律。
2. **四种停止原因，四个固定码。** `has_more_false`（服务端声明结束，连同页见证保留并用于开启对账）、`empty_page_end`（有效页上无 thread id）、`access_restricted`（非零 `error_code`、畸形响应体、`DataFetchError` 或任何传输失败）与 `unit_cap_reached`。
3. **页尾保留。** 当 `max_items` 在页尾前停下单元时，同一页码原地保留、页见证保留；下一单元重发同一请求，并按稳定 `thread_id` 跳过已交付主题。
4. **停滞防护。** 身份元组连续重复的页没有进展；此类单元累计到有界次数后以固定码阻塞，而不是无限循环。
5. **身份把守的交付。** 每个列出主题都从呈现它的同一页经 `get_note_by_id` 抓取，按完整 Content 发布，一个失败主题绝不阻塞无关主题。

## 验收

- 游标往返、四种停止原因、页尾回放、停滞阻塞与绑定变更拒绝均有单元测试。
- 页解析不保留任何主题载荷、标题或媒体 URL；非零 `error_code` 或畸形响应体记录 `access_restricted`，绝不是源末。
- 集成测试跨重启驱动三个及以上页步，到达 `has_more_false`，对账头部，进入增量模式，并把一条文章作品经归档 → Emby 发布且零工作重放。
- 每个头修订钉定测试推进到 `0019_tieba_creator_notes`。
- 完整 Python/Web/静态/文档门通过。
- 部署、真人登录与任何真实请求保持 `NOT_RUN`。

## 明确非目标

- 回复、混合/富内容主题媒体，或超出 0020–0022 已冻结形状的图集。
- 任何 Emby/Jellyfin 服务器控制，以及任何对 0074/0076/0080/0081/0084 语义的改动。
