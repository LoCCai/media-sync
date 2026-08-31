# Execution 0017 plan / 执行 0017 计划

- Status / 状态：In progress / 推进中
- Plan date / 计划日期：2026-09-01
- Predecessor / 前置：Execution 0016 closeout commit `4774c34`
- Database migration / 数据库迁移：Not planned / 不计划

## Baseline / 前置基线

Before source edits, the six-file gate passed `136 passed in 13.50s`: `test_mediacrawler_ingestion.py`, `test_mediacrawler_refresh.py`, `test_mediacrawler_db_ingestion.py`, `test_mediacrawler_download_runtime.py`, `test_pipeline_runtime.py`, and `test_packaged_migrations.py`. The branch was clean at `4774c34`, with local `main`, `origin/main` and GitHub reconciled. / 在源码修改前，六文件门禁通过 `136 passed in 13.50s`：`test_mediacrawler_ingestion.py`、`test_mediacrawler_refresh.py`、`test_mediacrawler_db_ingestion.py`、`test_mediacrawler_download_runtime.py`、`test_pipeline_runtime.py` 与 `test_packaged_migrations.py`。分支在 `4774c34` 保持干净，本地 `main`、`origin/main` 与 GitHub 已核对一致。

## Delivery sequence / 交付顺序

1. **Freeze authority protocol / 冻结权限协议**
   - Add an XHS creator-authority validator shared by refresh request and child-load boundaries. It accepts only exact HTTPS Xiaohongshu creator URLs whose `/user/profile/<id>` matches the trusted Author and whose `xsec_token` and `xsec_source` are unique and non-empty. / 增加由刷新请求与 child-load 边界共享的 XHS 作者权限校验器；只接受精确 HTTPS 小红书作者 URL，要求 `/user/profile/<id>` 匹配可信 Author，且 `xsec_token` 与 `xsec_source` 唯一非空。
   - Model explicit note detail and creator lookup as mutually exclusive repr-safe inputs; bump the child frame schema and repeat validation after deserialization. / 把显式 note detail 与作者查找建模为互斥、repr 安全的输入；升级 child frame schema，并在反序列化后重复校验。

2. **Compose exact Subscription authority / 组合精确 Subscription 权限**
   - In the lazy database-bound refresher, retain the explicit single-note reference as an override. Otherwise resolve only the selected source Subscription's validated `policy.mediacrawler.creator_input.secret_ref`. / 在数据库绑定的惰性 refresher 中保留显式单 note 引用作为覆盖项；否则只解析选中来源 Subscription 已校验的 `policy.mediacrawler.creator_input.secret_ref`。
   - Carry the trusted author ID and bounded `subscription.max_items` into the private request; reject missing or malformed authority with existing fixed errors. / 把可信作者 ID 与有界 `subscription.max_items` 带入私有请求；缺失或畸形权限继续使用既有固定错误拒绝。
   - Update pipeline preflight so either the compatibility note reference or a configured Subscription creator reference satisfies the XHS authority requirement before child Job state changes. / 更新 pipeline 前置校验，使兼容 note 引用或已配置的 Subscription 作者引用任一即可在 child Job 状态变化前满足 XHS 权限要求。

3. **Run bounded creator lookup / 运行有界作者查找**
   - Clear every upstream creator and detail list before setting one path. Creator lookup sets XHS creator mode, exactly one creator URL, `CRAWLER_MAX_NOTES_COUNT <= subscription.max_items`, concurrency one, JSONL output and existing disabled comment/media controls. Explicit note mode remains unchanged and isolated. / 在设置单一路径前清空所有上游 creator 与 detail 列表。作者查找设置 XHS creator 模式、精确一个作者 URL、`CRAWLER_MAX_NOTES_COUNT <= subscription.max_items`、单并发、JSONL 输出及现有评论/媒体关闭控制；显式 note 模式保持不变且相互隔离。
   - Allow the bounded child to return multiple content rows; reuse exact content remote ID, Asset kind/position and source-hint matching to select one refreshed URL. / 允许有界 child 返回多条 content 记录；复用精确 content remote ID、Asset kind/position 与 source-hint 匹配选出一个刷新 URL。

4. **Prove contracts and composition / 证明合约与组合**
   - Add isolated fake-checkout tests for creator-mode configuration, max-note bounding, multiple records, exact author authority, explicit note compatibility, mutual exclusion, frame validation and cleanup. / 增加隔离 fake-checkout 测试，覆盖 creator 模式配置、最大 note 限制、多记录、精确作者权限、显式 note 兼容、互斥、frame 校验及清理。
   - Extend unit/runtime tests for Subscription policy fallback, explicit override precedence, non-XHS isolation, missing authority preflight and fixed failures. / 扩展单元/运行时测试，覆盖 Subscription policy 回退、显式覆盖优先级、非 XHS 隔离、缺失权限前置失败及固定错误。
   - Add an offline XHS IMAGE/GALLERY composition using fake detail output, mock public DNS/HTTP and synthetic static image bytes through SQLite provenance, archive and Emby/Jellyfin layout with replay. / 增加 XHS IMAGE/GALLERY 离线组合，使用 fake detail 输出、mock 公网 DNS/HTTP 与合成静态图片字节，贯穿 SQLite 来源、归档、Emby/Jellyfin 布局及重放。

5. **Verify and close / 验证与收尾**
   - Run focused gates, Ruff check/format, strict mypy, complete pytest, documentation checks, upstream lock verification, build, retained-artifact audit and Git diff checks. / 运行专项门禁、Ruff check/format、严格 mypy、完整 pytest、文档检查、上游锁定校验、构建、保留产物审计及 Git diff 检查。
   - Update the four execution truth documents plus README, architecture, capability matrix and roadmap without turning offline evidence into live claims. / 更新四份执行真值文档以及 README、架构、能力矩阵与路线图，不把离线证据写成真人在线结论。
   - Create and push separate bilingual plan, implementation and closeout commits; leave `.upstream` unchanged and untracked. / 分别创建并推送双语计划、实现与收尾提交；保持 `.upstream` 不修改且不纳入版本管理。

## Planned commit sequence / 计划提交序列

1. `docs: 启动小红书作者权限闭环 / start XHS creator authority pipeline`
2. `feat: 闭环小红书作者权限查找 / close XHS creator authority lookup`
3. `docs: 收尾小红书作者权限闭环 / close XHS creator authority pipeline`
