# Execution 0016 plan / 执行 0016 计划

- Status / 状态：Planned; implementation pending / 已计划；实现待开始
- Plan date / 计划日期：2026-08-31
- Predecessor / 前置：Execution 0015 closeout commit `b105d00`
- Plan commit / 计划提交：Pending / 待提交
- Implementation commit / 实现提交：Pending / 待提交

## Delivery sequence / 交付顺序

1. **Freeze scope and baseline / 冻结范围与基线**
   - Record the upstream Weibo/Tieba/Zhihu audit and choose Weibo because raw `mblog.pics` is an existing pinned media input, whereas Tieba requires new HTML extraction and Zhihu exposes no stable media contract. / 记录微博/贴吧/知乎上游审计，并选择微博：原始 `mblog.pics` 是锁定版已有媒体输入；贴吧需要新增 HTML 提取，知乎没有稳定媒体契约。
   - Create these four bilingual records plus docs journal/roadmap entries before source edits. Record the 272-test predecessor gate. / 在源码编辑前创建四份双语记录及文档日志/路线图条目，并记录 272 项前置门禁。

2. **Add one shared Weibo media shim / 增加共享微博媒体 shim**
   - Add an integration-owned helper that validates ordinary original numeric-ID `mblog` records, transforms valid flat `pics` dictionaries using the pinned `i1.wp.com/<host>/large/<file>` rule, preserves order and rejects duplicates or opaque shape drift. / 增加由本集成拥有的 helper：校验普通原创 numeric-ID `mblog`，按锁定的 `i1.wp.com/<host>/large/<file>` 规则转换合法扁平 `pics` 字典、保持顺序，并拒绝重复或不透明形状漂移。
   - Install the helper in both creator runner and detail runner after verified checkout import. Use task-local capture so concurrent upstream calls cannot cross-contaminate records. Keep `.upstream` clean. / 在已验证 checkout 导入后，分别于 creator runner 与 detail runner 安装 helper；使用 task-local捕获，避免并发上游调用交叉污染记录，并保持 `.upstream` 干净。

3. **Normalize and refresh exact image Assets / 归一化并刷新精确图片 Asset**
   - Parse only the private v1 image field; map one image to `IMAGE`, multiple to `GALLERY`, and generate ordered position-based image Assets. Strip every integration-private field recursively before durable raw is built. / 只解析私有 v1 图片字段；单图映射为 `IMAGE`，多图映射为 `GALLERY`，并生成按 position 排序的图片 Asset；构建持久 raw 前递归移除全部集成私有字段。
   - Add WB to detail/refresh support for image kind only. Require numeric exact detail IDs and retain exact Account, Subscription, Asset identity and query-free source-hint matching. / 仅为 image kind 把 WB 加入 detail/refresh 支持；要求 numeric 精确 detail ID，并保持精确 Account、Subscription、Asset identity 与无 query source-hint 匹配。

4. **Compose the real production path offline / 离线组合真实生产路径**
   - Extend fake-checkout contracts for creator and detail installation/configuration/cleanup, then prove normalize→SQLite creates Assets and refresh provenance. / 扩展 fake checkout 契约以覆盖 creator/detail 安装、配置与清理，再证明 normalize→SQLite 创建 Asset 与刷新来源。
   - Add a Weibo-specific E2E using the real application/runtime wiring, fake detail payload, mock public DNS/HTTP, deterministic PNG/JPEG bytes and real controlled image probing. Prove archive plus Emby poster/backdrop/gallery/NFO/source output and zero-work replay. / 新增微博专项 E2E：使用真实 application/runtime 接线、fake detail payload、mock 公网 DNS/HTTP、确定性 PNG/JPEG 字节与真实受控图片探测；证明归档、Emby poster/backdrop/gallery/NFO/source 输出及零工作重放。

5. **Verify, document, commit and push / 验证、记录、提交并推送**
   - Run focused tests, full pytest, Ruff lint/format, strict mypy, docs/upstream checks, build, diff and retained-artifact audits. / 运行专项测试、完整 pytest、Ruff lint/格式、严格 mypy、文档/上游检查、构建、diff 与保留产物审计。
   - Update implemented/remaining truth in the execution records, README, roadmap, capability matrix and architecture; keep all live rows `NOT_RUN`. / 在执行记录、README、路线图、能力矩阵与架构中更新已实现/待实现真值；全部真人行保持 `NOT_RUN`。
   - Create separate bilingual plan, implementation and closeout commits; push `main` and compare local, `origin/main` and GitHub SHAs. / 分别创建双语计划、实现与收尾提交；推送 `main` 并比对本地、`origin/main` 与 GitHub SHA。

## Risks and rollback points / 风险与回退点

- The pinned upstream uses a third-party WordPress image proxy. Offline acceptance proves URL construction and the closed request profile, not proxy uptime, rate limits or service terms. / 锁定上游使用第三方 WordPress 图片代理；离线验收只证明 URL 构造与封闭请求 profile，不证明代理 uptime、限流或服务条款。
- Creator mode walks full history. Do not weaken the existing explicit acknowledgement or watchdog boundaries. / creator 模式遍历完整历史；不得弱化现有显式确认与 watchdog 边界。
- A reordered picture list changes position-based identity. Preserve pinned order and record same-note reorder/version-aware replacement as future work. / 图片列表重排会改变基于 position 的 identity；本轮保持锁定顺序，并把同帖重排/版本感知替换记录为后续工作。
- If the composition exposes a shared defect, repair the smallest common contract and rerun Bilibili/Kuaishou/Douyin regressions; do not expand into Weibo video or live qualification. / 若组合暴露共享缺陷，只修复最小公共契约并重跑 Bilibili/快手/抖音回归；不得扩展到微博视频或真人验收。
