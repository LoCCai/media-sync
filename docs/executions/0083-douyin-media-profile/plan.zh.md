[English](plan.md) | **中文**

# 计划：抖音媒体请求 profile 与有界选流

状态：**已冻结**。本计划不授权任何部署、平台请求或驻留进程重启。

## 1. 先复核钉定事实

- 写代码前重读 `.upstream/MediaCrawler/store/douyin/__init__.py:132-140`（扁平化顺序）与 `media_platform/douyin/client.py:211-221`（详情端点与 header 处理），并在验证记录中引用。
- 记录必须保持不变的 media-sync 调用点：0080 扫描状态机、`dy-work-v1:` 游标、四个停止原因，以及迁移头 `0017_kuaishou_creator_work`。

## 2. 请求 profile

- `src/media_sync/media/locator.py`：在封闭枚举中加入 `MediaRequestProfile.DY_MEDIA`（`"douyin_media"`）。
- `src/media_sync/media/network.py`：只为它加恰好三个 header——桌面 `User-Agent`、`Referer: https://www.douyin.com/`、`Accept: */*`——别的一律不加。没有 Cookie、没有 Authorization、没有调用方 header、不做 TLS 指纹。
- `src/media_sync/integrations/mediaCrawler/refresh.py`：用一个镜像既有 B 站分支的 helper 为 `Platform.DY` 选择 `DY_MEDIA`；默认分支继续返回 `DEFAULT`。其他平台不改。

## 3. 有界选流

- 新模块 `src/media_sync/integrations/mediacrawler/douyin_media.py`，持有一个只对单个 `aweme_detail` 映射求值的纯函数。它返回冻结的 `DouyinMediaSelection`：所选视频 URL（瞬态、`repr=False`）、封面 URL、排序事实（`bit_rate`、`play_addr_h264`、`play_addr_256`、`play_addr`、`none`）与声明画质。遇到漂移抛出固定 `ValueError` 子类；绝不返回部分猜测。
- 排序：先 `max(width, height)` 最高，再 `bit_rate` 最高，再 `data_size` 最大，最后声明顺序。最多 8 项；更多即漂移。
- URL 门：仅 HTTPS、无 userinfo、无 fragment、默认端口、host 必须落在封闭后缀表内的抖音媒体域、path 不得为根。
- 封面沿用上游规则（先 `raw_cover` 再 `origin_cover`，条目数≥2 时取 `url_list[1]`），且可选。

## 4. 不改持久形状的接线

- `douyin_creator_capture.py`：子进程内每条详情只计算一次选流，经 context variable 发布，完全仿照 `_ACTIVE_IDENTITY`；store 包装器加上私有 `__media_sync_dy_media_rank` 字段与瞬态所选 URL。
- `normalizers.py`：把新私有字段登记进既有 `_PRIVATE_MEDIA_FIELDS` 集合，使其在组装 envelope 前被剥离；并让 `_normalize_dy` 只在所选档位严格优于上游扁平字段时才优先使用所选 URL，否则保持今天字节一致的行为。
- 交付载荷不新增任何泄露 URL 的内容：最多一个固定档位字符串。

## 5. 验证序列

1. 单元：排序矩阵、每条拒绝分支、封面规则、回退等价性。
2. 契约：shim 发出私有字段；该字段绝不出现在 envelope 或持久 `raw` 中；回退逐字复现当前 URL。
3. 单元：profile header 集合恰为预期的三个 header，且其他平台仍然不发。
4. 集成：SQLite → 刷新 → mock DNS/HTTP → 归档 → Emby，覆盖 `bit_rate[]` 优于 `play_addr_h264` 的作品、零工作重放，以及以固定码关闭失败的漂移用例。
5. 完整 Python 与 Web 套件、Ruff、strict mypy、docs/upstreams、`git diff --check`；以双语记录精确数字。

## 6. 明确不在范围内

- 签名（`a_bogus`、`msToken`、`uifid`）、TLS 指纹伪装，或参考实现的重试策略。
- 任何关于真实 CDN 字节、水印状态或可播放输出的声明。
- 任何对 0074/0076/0080/0081 持久语义或迁移的改动。
