[English](verification.md) | **中文**

# 验证：抖音媒体请求 profile 与有界选流

计划基线：本目录中冻结的计划。实现是在 0082 加固之上的单个提交。

## 最终结果

| 门禁 | 结果 | 证据与边界 |
| --- | --- | --- |
| 排序规则 | `PASS` | `tests/unit/test_douyin_media.py`：`max(width, height)` 最高者胜；平局依次比较 `bit_rate`、`data_size`、声明顺序；`bit_rate` 上限 8 项。 |
| 漂移关闭失败 | `PASS` | 同文件：非映射 `bit_rate`、空数组、超界数组、缺失 `url_list`、重复 URL、`http`、userinfo、非默认端口、根路径、fragment，以及落在抖音媒体后缀表之外的 host，均以固定码抛出 `DouyinMediaSelectionError`。 |
| 回退等价 | `PASS` | 同文件：无 `bit_rate` 时，所选 URL 严格等于 `play_addr_h264` → `play_addr_256` → `play_addr` 的最后 `url_list` 项，即钉定扁平化规则。 |
| 私有字段纪律 | `PASS` | `test_private_rank_field_never_reaches_the_persisted_envelope`：归一化剥离 `__media_sync_dy_media_rank_v1`；字段名与签名 URL 哨兵都不出现在持久 envelope 中。 |
| store shim | `PASS` | `tests/contract/test_douyin_media_capture.py`：已安装 shim 优先声明更高的流、无排序时保持钉定记录字节一致、遇到漂移声明不臆造档位，重复安装幂等。 |
| 媒体 profile header | `PASS` | `tests/unit/test_media_network.py`：`DOUYIN_MEDIA` 只发 `User-Agent`、`Referer: https://www.douyin.com/`、`Accept: */*` 及传输层 `Accept-Encoding`；无 Cookie、`Authorization`、`Origin` 或调用方 header。调用方 header 仍以 `download_range_invalid` 拒绝。 |
| 刷新 profile 接线 | `PASS` | `tests/unit/test_mediacrawler_refresh.py` 与 `tests/contract/test_mediacrawler_detail_refresh.py`：抖音资产以 `DOUYIN_MEDIA` 解析；快手、微博、贴吧、知乎、小红书保持 `DEFAULT`；B 站保持自身 profile。 |
| 端到端交付 | `PASS` | `tests/integration/test_douyin_playable_pipeline.py`：SQLite → 刷新 → mock DNS/HTTP → 归档 → Emby 在断言线路上的 DY profile 下通过，另含图集切片与零工作重放。 |
| 完整 Python 套件 | `PASS` | `7228 passed, 63 skipped, 108 warnings in 1624.06s`。跳过项为已记录的 Windows/POSIX 符号链接、POSIX 目录与 PostgreSQL URL 分支。 |
| Ruff lint / format | `PASS` | `ruff check src tests` → `All checks passed!`；`ruff format --check src tests` → `441 files already formatted`。 |
| strict mypy | `PASS` | `mypy --strict src` → `Success: no issues found in 170 source files`。 |
| 文档 | `PASS` | `scripts/check_docs.py` → `Documentation links OK (828 Markdown files checked)`。 |
| Web 门禁 | `PASS` | `svelte-check` → `0 errors and 0 warnings`；`vitest` → `30 files / 843 tests`。本执行未改前端。 |
| Docker / Linux 主机 / 真人登录 / CDN 字节 | `NOT_RUN` | 未部署、未使用账户、未发平台请求、未取真实媒体字节。 |

## 跑门禁期间完成的修复

- 四个既有刷新测试与一个进程运行器测试为抖音断言了无 header 的 `DEFAULT` profile。它们现在断言 `DOUYIN_MEDIA`，这正是本执行有意改变的行为。
- `tests/contract/test_browser_policy_wiring.py` 按名称禁用捕获钩子；新抖音 store shim 必须加入该列表，否则真实 creator/detail 入口会因导入假 checkout 中不存在的 `store.douyin` 而以退出码 30 失败。
- `tests/contract/test_mediacrawler_detail_refresh.py` 构造的假 checkout 只有 config 与 main 模块。由于抖音 shim 会为每个抖音子进程安装，夹具现在也写入 shim 导入的 `store.douyin` 模块；夹具自身的 JSONL 路径不变。
- 集成管线 handler 此前断言抖音请求线上不得出现以 `Mozilla/5.0` 开头的 `User-Agent` 与 `Referer`。这正是本执行改变的内容，因此这些断言被替换为封闭 DY header 集合。

## 已运行命令

```text
python -m pytest -q
python -m pytest tests/unit/test_douyin_media.py tests/contract/test_douyin_media_capture.py -q
python -m pytest tests/integration/test_douyin_playable_pipeline.py -q
python -m pytest tests/contract/test_browser_policy_wiring.py -q
python -m pytest tests/contract/test_mediacrawler_detail_refresh.py -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
npm --prefix web run check | test
```

## 边界说明

- 选流是针对钉定上游源码与已文档化的 `bit_rate[]` 契约形状证明的。没有捕获真实响应，因此平台将来不再发出的形状会以固定 `douyin_media_field_invalid` 拒绝出现，而不是错误下载。
- profile 是封闭 header 集合，不是 TLS 指纹伪装。CDN 是否接受它，只能由一次操作者运行的金丝雀证明。
