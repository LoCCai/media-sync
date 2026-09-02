[English](plan.md) | **中文**

# 执行 0013 计划

- 状态：已在冻结的离线边界内执行完成
- 计划日期：2026-08-31
- 完成日期：2026-08-31
- 前置：Execution 0012 closeout commit `7c6f567`
- 计划提交：`46323bd`
- 实现提交：`dd6cfec`

## 交付顺序

1. **冻结契约与基线**
   - 在修改源码前记录四份中英双语执行文档，把执行 0013 加入日志/路线图，并创建双语本地计划提交。
   - 保持精确锁定的上游提交及外部 runtime/许可证边界；不复制 MediaCrawler 或 bili-sync-up 源码。
   - 运行既有导入、detail refresh、locator、网络、下载、layout 与离线 pipeline 测试作为起始基线。

2. **创建稳定 Bilibili 视频发现槽位**
   - 先加红测，证明一个 Bilibili 视频元数据记录产生封面与一个 position 0 视频 Asset，而动态不会产生合成媒体。
   - 让领域快照的 source URL 显式可选，并产生一个 `source_url=None` 的 locator-only `<aid>:video:0` 槽。数据库列、`AssetUpsert`、指纹与刷新来源追踪已支持该形状，因此不计划 migration。
   - 只在精确 Bilibili video/position 0 形状中允许缺少 source hint；refresher 按绑定 content/remote-id/kind/position 选择刷新候选，所有既有形状继续保持非空 source-hint 精确匹配。

3. **在隔离 child 中解析首 P progressive URL**
   - 扩展 numeric-aid detail 路径：校验返回 aid 与首 P CID，调用锁定的 `get_video_play_url_task`，并解析封闭的单 `durl` 结果。
   - 在上游完成结果旁返回一个具名、repr-safe 的 progressive 结果。先读取普通 content JSONL，再只在内存中向有界字节注入一个私有桥字段；不改写 attempt 树。默认关闭的 detail-only 归一化 gate 接受该字段，在 envelope/raw 保留前移除它，并以瞬态 URL 产生同一个持久 Asset 身份。
   - 为不支持的 progressive 形状增加封闭 child 结果，并与播放地址瞬时获取失败及非法结果区分。

4. **把非密钥 Bilibili HTTP 配置传入下载器**
   - 为瞬态 `ResolvedLocator` 增加封闭 request-profile 标识；持久 locator schema v1 保持不变。
   - 在有界 HTTP 层应用精确固定的 User-Agent、Referer 与 Origin，同时仍只接受续传状态提供的 Range/If-Range；绝不传递 Cookie、Authorization 或任意 header。
   - 证明该配置在重定向、续传与既有一次 401/403 重解析中保持正确，且不削弱 DNS、重定向与 header 限制。

5. **组合离线可播放到 Emby 链路**
   - 增加契约测试，覆盖精确 aid/CID 绑定、瞬态签名输出、不支持/非法播放地址形状及 attempt 根清理。
   - 增加一个专项集成：使用合成元数据、假的当前 Subscription 来源、确定性 CDN 字节与受控媒体探测；断言持久下载成功、SHA-256/归档身份、主 `.mp4` episode 输出、NFO/source 元数据及幂等重放。
   - 扫描 SQLite、runtime 输出、CLI/日志捕获及 Git 可见文件，确认不存在签名 URL、Cookie 哨兵与禁止 header。

6. **验证、记录并提交**
   - 运行执行专项门禁、完整 pytest、Ruff lint/格式、mypy、文档/上游检查、构建及 `git diff --check`。
   - 运行保留产物与高置信密钥审计，不打印命中的密钥值。
   - 用精确命令、结果与提交更新目标/计划/推进/验证；更新能力文档但不提升任何真人行；创建双语实现与收尾提交。

## 风险与回退点

- `NULL` source URL 只允许用于精确 Bilibili 首 P 视频槽，且必须搭配稳定 MediaCrawler refresh locator；其他既有形状继续保持当前 source-hint 规则。
- `durl` 可能表示旧式分段媒体。执行 0013 只接受精确一个分段，确保输出可独立播放；多段拼接与 FLV remux 留待后续。
- 固定 Bilibili header 属于非密钥协议元数据；必须由封闭 profile 选择，不能作为调用方可控 mapping 持久化或与凭据混合。
- 因为 forward 元数据缺少 CID，0013 的稳定身份是逻辑 `<aid>:video:0` 槽；同一 aid 下首 CID 替换无法自动使已验证字节失效，该能力与 CID-aware 多 P 发现一并延期。
- 回退时移除合成 Bilibili 视频发现槽、播放地址补充及 request profile，同时保留执行 0012 与历史封面能力；不需要破坏性 migration。
