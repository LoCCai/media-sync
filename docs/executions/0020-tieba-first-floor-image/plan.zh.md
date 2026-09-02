[English](plan.md) | **中文**

# 执行 0020 计划

- 状态：冻结离线范围已完成
- 计划日期：2026-09-02
- 前置：Execution 0019 closeout commit `431fd855dafce502e83f74a055a4b27ae5c6f40b`
- 计划提交：`df7a38a6f9beee35c6c19336260b512ebc87ce0d`
- 实现提交：`8a0e935624e944809af1a56b0f02186686433d95`
- 数据库迁移：计划无

## 前置基线

分支从已核对一致且干净的 `431fd855dafce502e83f74a055a4b27ae5c6f40b` 开始。编辑前的导入/detail/数据库/下载/runtime/refresh 专项基线通过 `307 passed in 36.66s`。两个锁定上游均通过校验，两个 checkout 工作树均干净。一次有界、未登录的公开 API 审计确认了当前 type/key/host/query 形状，且未保留响应正文或 query 值。

## 交付顺序

1. **冻结源码与响应合约 — completed / 已完成**
   - 增加绑定 MediaCrawler SHA `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` 的源码合约，执行真实 `extract_note_detail_from_api` → `TiebaNote` → `update_tieba_note` → JSONL 丢失边界；把测试绑定到 `_get_pc_page_data`、`get_note_by_id`、creator `asyncio.gather`/父存储及 JSONL 导出，且不修改上游。
   - 按已观察的当前形状冻结合成离线响应：普通 type-0 文本加精确一个 type-3 图片及精确 `origin_src` 权限。明确现网只读审计是当前结构证据，不是保留夹具或登录验收。

2. **捕获精确首楼媒体并约束作者 — completed / 已完成**
   - 增加集成拥有的 `tieba_media.py`，实现严格正整数主题 ID、canonical 主题 URL、有界首楼 item 校验、精确 type-3 键合约、严格 signed/query-free 图片 URL 校验及 source-hint 派生。
   - 只 patch 校验 checkout 对象：extractor → 精确对象冻结捕获 → 父 `update_tieba_note` ContextVar → 匹配 JSONL 行。完整重复安装允许幂等；错误来源、部分/冲突状态、模型无法携带、身份不匹配及跨任务泄漏均关闭失败。
   - 只在 scheduled 运行中以可信 Subscription 上限包装锁定 creator 循环。校验页面字典、`thread_list`、正整数唯一 ID、`has_more`、精确返回 note 身份及 callback batch 边界；在详情前截断，达到上限前停止额外 sleep，并拒绝重复/无推进/漂移页面。
   - 在 scheduled creator 与 detail 子进程中，均于校验导入后、上游 `main()` 前安装捕获。

3. **归一化并刷新 ARTICLE 所属单图 — completed / 已完成**
   - 全有或全无地扩展贴吧归一化：保留 ARTICLE，输出一个 `<note_id>:image:0`，递归移除私有字段并只持久化规范无 query 提示；保持历史零图片 ARTICLE 行。
   - 把贴吧加入精确详情执行与刷新支持。只从持久 canonical URL 派生 note ID，要求唯一精确 normalized content/Asset/hint 匹配，再次校验新签名 URL并以 DEFAULT profile 返回，不携带账户 header。

4. **校验字节并组合 Emby 输出 — completed / 已完成**
   - 为贴吧 IMAGE 启用既有有界静态图片结构门，并证明接受/拒绝边界及 normal/recovery/takeover 标志保持。
   - 增加隔离的 SQLite → fake detail → mock 公网 DNS/HTTP → 生产字节门 → 不可变归档 → Emby 集成测试，覆盖 poster/backdrop/gallery/body/NFO/source 输出及 query-only 零工作重放。
   - 审计保留数据库、WAL/SHM、runtime、archive 与 export 树，确保不含私有字段及瞬态 token/query 片段。

5. **验证、审查与发布 — completed / 已完成**
   - 运行源码合约、专项门、完整套件、Ruff、格式、严格 mypy、compileall、上游锁、构建、文档、diff 与保留产物审计；只记录真实执行的命令、数量、耗时与跳过项。
   - 更新这四份执行文档及能力/路线图/索引真值。登录态贴吧 login/creator/detail、未来 CDN 行为及真实 Emby/Jellyfin 扫描/展示保持 `NOT_RUN`；更广媒体形状继续推进。
   - 分别创建并推送双语计划、实现与收尾提交，并核对本地、tracking 与 GitHub SHA。

## 提交序列

1. `df7a38a` — `docs: 启动贴吧首楼图片闭环 / start Tieba first-floor image pipeline`
2. `8a0e935` — `feat: 闭环贴吧首楼图片 / close Tieba first-floor image pipeline`
3. 本次文档收尾提交 — `docs: 收尾贴吧首楼图片闭环 / close Tieba first-floor image pipeline`；其自引用 SHA 有意只保留在 Git 历史中。

整个执行期间，`.upstream` 必须继续排除在跟踪外、保持未修改且干净。
