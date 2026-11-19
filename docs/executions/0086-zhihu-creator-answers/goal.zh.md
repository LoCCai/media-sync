[English](goal.md) | **中文**

# 目标：知乎创作者回答耐久交付

media-sync 已为 B 站（0074）、小红书（0076）、抖音（0080）、快手（0081）、微博（0084）与贴吧（0085）交付耐久创作者作品。知乎是已冻结的[下一交付序列](../0083-douyin-media-profile/next-delivery.zh.md)中最后一个仍只依赖有界**计数**的平台：创作者订阅会在上限处停下、无法续跑、无法区分受限 feed 与源末，也无法发布按内容交付证据。本执行闭合这一缺口。

## 知乎的差异

只从钉定上游推导：

- 分页是 `/api/v4/members/<url_token>/answers` 上的**整数 `offset`**，`limit` 由客户端选择，`order_by=created`（`.upstream/MediaCrawler/media_platform/zhihu/client.py:399-419`）。
- 循环是 `while not is_end:` … `offset += limit`（`client.py:462-490`），所以结束是服务端声明的 **`paging.is_end`** 布尔值，绝不是页数。
- 假值响应体在读取任何 paging 之前就跳出循环（`client.py:483-484`），这**不是**结束。
- 创作者身份是 `/people/<url_token>` URL 中的 `url_token`（`core.py:265`）；内容身份是 extractor 的 `content_id`。

offset 是 page*limit 的乘积。两次请求之间的一次插入或删除会**整体位移窗口**：下一页随后会静默跳过或重复回答，而每个响应看起来仍然有效。这才是本执行必须使其耐久化的风险——而不只是"数页数"。

## 交付物

一个知乎创作者订阅：

1. 以每次一个按页界定的单元走过 offset 链，上限为 `max_items`；
2. 把服务端声明的 `is_end` 记录为**源末观察**，且仍只开启对账，绝不代表完整性；
3. 区分 `empty_page_end` 与声明的结束；
4. 把假值/畸形响应体、`DataFetchError`/`IPBlockError` 或传输失败视为 `access_restricted`，绝不推进游标；
5. 通过比较页身份元组检测**窗口位移**，重放同一 offset，并在有界次数的零进展单元后以 `zhihu_window_shifted` 阻塞；
6. 只凭封闭管线回执发布按内容交付，随后对账头部边界，之后才进入增量轮询；
7. 把迁移头推进到 `0020_zhihu_creator_answers`，约束纪律与 0015–0019 相同。

## 明确不在范围

- 部署、Linux 主机门禁、真人知乎登录与任何真实请求。这些行保持 `NOT_RUN`，属于操作者金丝雀（0087）。
- 对另外六个有界契约或 0033 图库 shim 的任何改动。
- 复制 GPL 或 NC 许可的上游源码。只使用从钉定检出推导出的行为与协议事实。
