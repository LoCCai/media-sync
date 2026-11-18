[English](progress.md) | **中文**

# 进展：抖音媒体请求 profile 与有界选流

状态：本地已实现并验证。未做任何部署，未使用任何平台账户或真实 CDN 字节。

## 结果

一次抖音创作者作品交付现在能取用钉定详情响应声明的最高流，而不是上游 store 恰好留下的扁平 URL；其媒体请求也带上平台期望的封闭桌面 header 集合。

## 已实现

1. **封闭媒体 profile。** `MediaRequestProfile.DOUYIN_MEDIA` 只携带 `User-Agent`（桌面 Chrome）、`Referer: https://www.douyin.com/` 与 `Accept: */*`。`refresh.py` 通过 `_platform_media_profile()` 选择它；其他平台保持 `DEFAULT`，B 站 progressive/dynamic 分支不受影响。不存在 Cookie、`Authorization`、`Origin`、调用方 header 或 TLS 指纹伪装。
2. **有界选流。** `douyin_media.py` 把单个钉定 `aweme_detail` 归约为冻结的 `DouyinMediaSelection`。排序为 `max(width, height)` 最高，其次声明 `bit_rate` 最高，再次 `data_size` 最大，最后声明顺序；`bit_rate` 最多 8 项。该模块拒绝而不是猜测：缺失 `url_list`、重复 URL、超界数组、`http` URL、带 userinfo/端口/fragment/根路径的 URL，或落在封闭抖音媒体后缀表之外的 host，都会抛出带固定码的 `DouyinMediaSelectionError`。
3. **钉定 store shim。** `install_douyin_media_capture()` 用任务局部 `ContextVar` 包装 `store.douyin.update_douyin_aweme` 与 `store.douyin._store_impl.DouyinJsonlStoreImplement.store_content`，与快手图集 shim 同构。只有 `bit_rate` 档会改写 `video_download_url`；回退档复现钉定扁平化顺序，使当前可交付的每条作品保持字节一致。私有字段 `__media_sync_dy_media_rank_v1` 已登记进 `_PRIVATE_MEDIA_FIELDS`，因此绝不进入 envelope 或持久 `raw`；它只携带 `{"rank": ..., "width": ..., "height": ...}`。
4. **runner 接线。** `runner.py` 为每个抖音子进程安装该 shim；`detail_runner.py` 为单详情刷新路径安装，使刷新看到与创作者扫描相同的排序。

没有改动任何迁移、游标、覆盖、停止原因或进度表语义；迁移头仍为 `0017_kuaishou_creator_work`。

## 有意未做

- 不做 `a_bogus`/`msToken`/`uifid` 签名、不做 TLS 指纹伪装、不采用参考实现的重试/分片策略。MediaCrawler 仍是唯一签名权威，未复制任何 GPLv3 源码。
- 不作去水印声明，也不做真实 CDN 字节获取：在真人金丝雀之前，不对交付字节作任何陈述。

## 工作期间的观察

0082 的失败模式影响了这里的检查方式：`ruff format --check` 与 `ruff check` 都按全仓运行，而不是只看改动文件，这正是能抓到那些必须同步修改的测试侧 profile 断言的原因。
