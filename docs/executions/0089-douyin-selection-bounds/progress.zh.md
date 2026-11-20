[English](progress.md) | **中文**

# 进展：收尾 0088 延后的两个抖音选流缺口

状态：本地已实现并验证。未部署，未使用真人账户或平台请求。

## 结果

0083 的抖音选流排序现在在真实载荷上真的会执行，并且 shim 不再写入它自己的读取器会丢弃的 URL。

## 原来错在哪

1. **8 项上限使功能不可达。** 上游按每个（画质 × 编码）声明一项 `bit_rate[]`，因此现实载荷带 10–16 项。每个这样的载荷都抛 `douyin_media_field_invalid`；shim 把错误吃掉（`douyin_media.py:322-325`）并回退到钉定扁平化。功能实现了、用 2–3 项的 fixture 测过了，但在实践中从未生效。
2. **shim 与它的读取器对逗号不一致。** `validate_douyin_media_url` 接受 `,`；`apply_douyin_media_selection` 把这样的 URL 写进 `video_download_url`；`_dy_url_list(..., allow_scalar_commas=False)` 随后对它返回 `()`。直接探针：记录归一化为 `kind=text` 且零资产——一个视频作品静默变成了文本行。

## 改动内容

- `DOUYIN_MAX_BIT_RATE_ENTRIES`：8 → 32，并把"画质 × 编码"的理由写成内联注释。超过 32 仍抛错，因此无界的服务端数组保持被拒绝。
- `validate_douyin_media_url` 拒绝 `,`。刻意**没有**把放宽应用到 `_dy_url_list`——它被笔记图库与其他媒体字段共用，在那里逗号确实是列表成员的分隔符。

两处都在 0083 自己的范围内。钉定上游文件只被读取以取得事实（`store/douyin/__init__.py:122-139`），未被修改。

## 验证

抖音单元文件 `26 passed`（原有 24 + 新增 2），抖音/刷新/摄取子集 `212 passed`；Ruff、`ruff format --check` 与 182 个文件的 strict mypy 全绿。逐门禁的确切证据见 [verification.zh.md](verification.zh.md)。

## 仍未闭合（已记录，不靠猜）

- **快手图片 CDN 允许列表** —— 全树没有真实主机名，允许列表无法推导；需要一个操作者捕获的真实 URL。
- **小红书明文 `http`** —— 0018 记录并测试的是 HTTP/HTTPS，收紧它属于改动已取得资格的能力，需要操作者决定。
- **动画图片当作静态图** —— 只有快手/微博/知乎对扩展名做门控；变成通用规则会改动 0076/0081 语义，需要独立执行。

这三项保持 `NOT_RUN`/`OPEN`，而不是靠猜静默关闭。
