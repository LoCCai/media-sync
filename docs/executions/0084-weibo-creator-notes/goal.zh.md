[English](goal.md) | **中文**

# 目标：微博创作者笔记耐久交付

## 结果

一个精确的微博创作者订阅获得与 B 站（0074）、小红书（0076）、抖音（0080）、快手（0081）相同的耐久交付链，且每条规则都从钉定微博源码推导，而不是从其它平台复制。

## 为什么微博形状不同

`docs/executions/0083-douyin-media-profile/next-delivery.md` 记录了相关事实；本执行重新读取并引用它们：

- 分页是 `/api/container/getIndex`，`containerid=107603<uid>` 配逐字回放的 `since_id` 游标，并在 `cardlistInfo.since_id` 回显（`.upstream/MediaCrawler/media_platform/weibo/client.py:341-372`）。
- 页大小**不是**请求参数。上游按硬编码 `10` 推进算术计数器，并在 `cardlistInfo.total > counter` 时继续（`client.py:411-412`）。这是**推断**，不是 `has_more` 标记，并且每当 `card_type == 9` 过滤丢卡（`client.py:407`）时就与观察到的内容不一致。
- 假值响应体会被记录为疑似封禁并中断循环（`client.py:401-403`）；缺失 `cards` 键也会中断循环（`client.py:404-406`）。两者都不是源末。
- `core.py:326-331` 传 `crawl_interval=0` 且无条数上限，因此上游创作者循环无界，耐久层必须自带单元上限。

## 必需行为

1. **逐字游标。** `since_id` 按原样存储与回放，绝不解析、再生成或规范化。它位于不透明 `wb-work-v1:` 命名空间下，沿用与 `ks-work-v1:`、`dy-work-v1:` 相同的封闭 schema 往返纪律。
2. **四种停止原因，四个固定码。** `total_inferred_end`（算术候选，连同声明的 total 与页见证一起保留）、`empty_page_end`（无内容且无声明 total）、`access_restricted`（假值响应体、缺失 `cards`、`DataFetchError` 或任何传输失败）与 `unit_cap_reached`。
3. **推断的结束绝不是完整。** 声明的 `total`、已消耗页数与首页见证都保留在游标里，使头部对账日后能确认或否决该边界。任何 API、日志或文档都不得把 `total_inferred_end` 描述成完整历史。
4. **页尾保留。** 当 `max_items` 在页尾前停下单元时，同一 `since_id` 原地保留、页见证保留；下一单元重发同一请求，并按稳定 `mblog.id` 跳过已交付笔记。
5. **停滞防护。** 非空页回显 `since_id` 等于输入，或空过滤页重复其游标，都是上游永不察觉的零进展；此类单元累计到有界次数后以固定码阻塞。
6. **身份把守的交付。** 笔记从呈现它的同一页抓取，按完整 Content 发布，一条失败笔记绝不阻塞无关笔记。

## 验收

- 游标往返、四种停止原因、页尾回放、停滞阻塞与绑定变更拒绝均有单元测试。
- 页解析不保留任何媒体 URL、`mblog` 载荷或原始 `total`；假值响应体或缺失 `cards` 记录 `access_restricted`，绝不是源末。
- 集成测试跨重启驱动三个及以上 `since_id` 步，到达推断结束，对账头部，进入增量模式，并把一条 IMAGE/GALLERY 或 VIDEO 作品经归档 → Emby 发布且零工作重放。
- 每个头修订钉定测试推进到 `0018_weibo_creator_notes`。
- 完整 Python/Web/静态/文档门通过。
- 部署、真人登录与任何真实请求保持 `NOT_RUN`。

## 明确非目标

- 任何"算术结束证明历史完整"的声明。
- 微博转发原文、创作者路径上的 `page_info` 媒体、超出 0016/0031/0035/0036 已冻结形状的 GIF/视频变体。
- Emby/Jellyfin 服务器控制，以及任何对 0074/0076/0080/0081 语义的改动。
