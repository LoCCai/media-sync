[English](goal.md) | 中文

# 目标：收乲 0088 延后的两个抖音选流缺口

## 为什么需要这次执行

[0088](../0088-code-review/verification.zh.md)修复了 26 个已核实缺陷，并刻意把四条发现延后到各自的执行，
因为它们会改动 0076/0081/0083 已冻结的行为。本次执行取其中属于 0083 抖音选流、
且可以**不编造事实**就收乲的两条：

1. **8 项 `bit_rate` 上限使整个功能不可达。** 上游按每个（画质 × 编码）声明一项，
   因此现实载荷带 10–16 项。每个这样的载荷都抛 `douyin_media_field_invalid`，
   shim 把它吃掉（`douyin_media.py:324-325`），回退到钉定的扁平化规则——
   这正是 0083 存在的意义所在。
2. **shim 会写入它自己的读取器拒绝的 URL。** `validate_douyin_media_url` 接受逗号；
   `apply_douyin_media_selection` 随后把该 URL 写进 `video_download_url`，而
   `_dy_url_list(..., allow_scalar_commas=False)` 对任何含逗号的标量返回 `()`——
   于是该作品变成无资产的 `TEXT` 行而不是 `VIDEO`。

## 已核实，不是推测

- 12 项载荷（4 画质 × 3 编码）在此次修复前到达 `douyin_media_field_invalid`，
  现在能正确排序到 2160×3840 条目。
- 33 项载荷仍被拒绝，因此边界仍是 fail-closed。
- 含逗号的 URL 此前归一化为 `kind=text` 且零资产；现在在选流时就被拒绝。

## 刻意仍未闭合

- **快手图片 CDN 允许列表。** 本仓库、钉定上游检出与任何 fixture 中都没有真实的快手 CDN 主机名：
  全树搜索 `yximgs`/`kwimgs`/`kwaicdn`/`kscdn`/`kuaishoucdn` 零命中。允许列表无法从已提交证据推导，
  凭空猜一个会对每一个真实 atlas 都 fail-closed。它需要一个操作者捕获的真实 URL。
- **小红书明文 `http`。** [0018 自己的验证](../0018-xhs-playable-video/verification.md)把范围定为
  "普通有界 HTTP/HTTPS"，并且它的测试断言 `http://…:80` 被接受，因此代码与其契约一致；
  审查者“文档承诺只允许 HTTPS”的说法不准确。收紧它是对已冻结执行的**能力改动**，需要操作者决定。
- **动画图片。** 只有快手、微博与知乎对图片扩展名做门控（`.jpeg/.jpg/.png/.webp`）；
  小红书、贴吧与抖音没有，而偵探式静态图门（`application/downloads.py:44-45`）只适用于贴吧/知乎。
  因此 GIF 仍可能在小红书与抖音上被当作静态图发布。

## 不在范围

- 对钉定上游文件的任何改动。
  行为仅从 `.upstream/MediaCrawler/store/douyin/__init__.py:122-139` 重新推导。
- 部署、登录或任何平台请求。按 [0087](../0087-operator-canary/qualification.zh.md)，
  每一行真人工作保持 `NOT_RUN`。
