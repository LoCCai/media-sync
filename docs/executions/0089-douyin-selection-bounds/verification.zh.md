[English](verification.md) | **中文**

# 验证：收尾 0088 延后的两个抖音选流缺口

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 排序可达性 | `PASS` | `tests/unit/test_douyin_media.py::test_a_realistic_multi_codec_bit_rate_array_still_ranks` 构起 12 项载荷（4 画质 × 3 编码）并断言它排序到 2160×3840 条目。改动前同一载荷抛 `douyin_media_field_invalid`，shim 把它吃掉（`douyin_media.py:322-325`），0083 的排序等于从未生效。 |
| 边界仍生效 | `PASS` | 既有超限用例现在用新常量：33 项数组仍抛 `douyin_media_field_invalid`，因此无界的服务端数组保持被拒绝。 |
| shim 与读取器一致 | `PASS` | `test_a_comma_bearing_signed_url_is_refused_rather_than_silently_downgraded`：含逗号的 URL 被 `validate_douyin_media_url` 与 `select_douyin_media` 双双拒绝。改动前直接探针：同一 URL 归一化为 `kind=text` 且零资产，即一个 VIDEO 作品被静默降级为 TEXT。 |
| 回退一致性保持 | `PASS` | 既有回退测试仍通过：无 `bit_rate` 时选中的 URL 精确等于 `play_addr_h264` → `play_addr_256` → `play_addr` 的最后一个 `url_list` 条目。 |
| 抖音与刷新子集 | `PASS` | `tests/contract/test_douyin_media_capture.py`、`tests/integration/test_douyin_playable_pipeline.py`、`tests/unit/test_mediacrawler_refresh.py`、`tests/integration/test_douyin_creator_work_ingestion.py` → `212 passed in 5.06s`。 |
| 抖音单元文件 | `PASS` | `tests/unit/test_douyin_media.py` → `26 passed in 0.90s`（原有 24 + 新增 2）。 |
| 静态门禁 | `PASS` | `ruff check src tests` → `All checks passed!`；`ruff format --check` → `466 files already formatted`；`mypy --strict src` → `Success: no issues found in 182 source files`。 |
| 真人金丝雀 | `NOT_RUN` | 未部署、未登录、未发平台请求、未取 CDN 字节。 |

## 改动内容

1. `DOUYIN_MAX_BIT_RATE_ENTRIES` 8 → 32，理由写在代码内联注释里，避免下一位读者又把它压回不可达的值。
2. `validate_douyin_media_url` 现在拒绝 `,`。逗号对 `_dy_url_list` 仍然有意义——该函数被笔记图库与其他媒体字段共用，在那里逗号确实是列表分隔符；放宽它会接受被夹带的第二个 URL，所以拒绝必须放在选流侧。

两处改动都在 0083 自己的范围内（抖音选流）。没有触碰其他平台行为，也没有触碰钉定上游文件。

## 刻意仍未闭合

| 发现 | 为什么不在本次修复 |
| --- | --- |
| 快手图片 CDN 允许列表 | 本仓库、钉定上游检出与任何 fixture 中都不存在真实的快手 CDN 主机名。全树搜索 `yximgs`、`kwimgs`、`kwaicdn`、`kscdn`、`kuaishoucdn` 零命中，所有测试 fixture 用的是 `img.example.test`。允许列表无法从已提交证据推导；凭空猜一个会对每一个真实 atlas 都 fail-closed。它需要一个操作者捕获的真实 URL。 |
| 小红书明文 `http` | 0018 自己的验证把范围定为"普通有界 HTTP/HTTPS"，其测试套件断言 `http://xhscdn.com:80/…` 被接受，所以代码与其记录在案的契约一致。审查者"文档承诺只允许 HTTPS"的说法不准确。收紧它属于改动已取得资格的能力，需要操作者决定。 |
| 动画图片被当作静态图发布 | 只有快手、微博与知乎对图片扩展名做门控（`.jpeg/.jpg/.png/.webp`）；小红书、贴吧与抖音没有，而侦探式静态图门（`src/media_sync/application/downloads.py:44-45`）只适用于贴吧/知乎。已核实：GIF 字节仍能通过抖音/快手门。把它变成通用规则会改动 0076/0081 的媒体语义，需要独立执行。 |

## 已运行命令

```text
python -m pytest tests/unit/test_douyin_media.py -q
python -m pytest tests/contract/test_douyin_media_capture.py tests/integration/test_douyin_playable_pipeline.py tests/unit/test_mediacrawler_refresh.py tests/integration/test_douyin_creator_work_ingestion.py -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
git diff --check
```
