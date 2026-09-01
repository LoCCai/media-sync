# Execution 0018 plan / 执行 0018 计划

- Status / 状态：Executed and closed offline / 已执行并完成离线收口
- Plan date / 计划日期：2026-09-01
- Predecessor / 前置：Execution 0017 closeout commit `00add11`
- Plan commit / 计划提交：`c9d3586`
- Implementation commit / 实现提交：`356e254`
- Database migration / 数据库迁移：None / 无

## Baseline / 前置基线

Before source edits, the seven-file gate passed `167 passed in 46.50s`: MediaCrawler detail-refresh contracts, Asset download orchestration, database ingestion, download runtime, pipeline runtime, the XHS creator-authority composition and refresh units. The branch was clean at `00add11`; local `main`, `origin/main` and GitHub were reconciled. / 源码修改前，七文件门禁通过 `167 passed in 46.50s`：MediaCrawler detail-refresh 合约、Asset 下载编排、数据库导入、下载运行时、pipeline 运行时、小红书作者权限组合及刷新单元测试。分支在 `00add11` 保持干净，本地 `main`、`origin/main` 与 GitHub 已核对一致。

## Executed delivery sequence / 已执行交付顺序

1. **Freeze the upstream video shape / 冻结上游视频形状 — complete / 已完成**
   - Add one integration-owned XHS media-locator validator for ordinary HTTP/HTTPS `xhscdn.com` initial paths, excluding userinfo, mismatched/non-default ports, fragments and root paths while preserving transient signed queries. Normalize host case, IDNA and one trailing dot; allow explicit scheme-default ports. / 增加一个由集成拥有的小红书媒体 locator 校验器，只接受普通 HTTP/HTTPS `xhscdn.com` 初始路径，排除 userinfo、与 scheme 不匹配/非默认 port、fragment 与根路径，同时保留瞬态签名 query；规范化 host 大小写、IDNA 与一个尾点，并允许显式 scheme 默认端口。
   - Split the existing XHS creator target gate into static `type="normal"` IMAGE/GALLERY and playable `type="video"` VIDEO-or-MIXED branches. Before normalized Asset checks, strictly parse the locked upstream scalar raw fields: exactly one non-empty `video_url` and zero or one `image_list`, with no whitespace, empty segment, duplicate, invalid candidate or container drift. Then require a one-to-one mapping to exactly one position-zero VIDEO and at most one IMAGE. / 把现有小红书作者目标门拆成静态 `type="normal"` IMAGE/GALLERY 分支，以及可播放 `type="video"` VIDEO 或 MIXED 分支。在检查归一化 Asset 前，严格解析锁定上游的原始标量字段：`video_url` 精确一个非空候选，`image_list` 零或一个候选，禁止空白、空分段、重复、无效候选及容器漂移；随后要求其与唯一 position 0 VIDEO 及最多一张 IMAGE 一一对应。

2. **Preserve exact refresh behavior / 保持精确刷新行为 — complete / 已完成**
   - Reuse exact Account/Subscription provenance, creator-secret fallback, explicit note override, `max_items` watchdog projection and unique content/Asset selection. No new authority frame or migration is needed. / 复用精确 Account/Subscription 来源、作者 secret fallback、显式 note 覆盖、`max_items` watchdog 投影及唯一 content/Asset 选择；无需新增权限 frame 或 migration。
   - Validate the selected creator-fallback video URL again after normalization and before creating `ResolvedLocator`; return `MediaRequestProfile.DEFAULT`, matching the locked upstream's header-free media GET. Keep the historical explicit-note video path compatible and outside this new creator-video claim. / 在归一化后、创建 `ResolvedLocator` 前再次校验选中的 creator-fallback 视频 URL；返回 `MediaRequestProfile.DEFAULT`，与锁定上游不带 header 的媒体 GET 一致。保留历史显式 note 视频路径兼容性，且不把它纳入本次新增作者视频声明。
   - Retain field-specific XHS durable-raw cleanup for `note_url`, `image_list`, `video_url`, `xsec_token` and `xsec_source`; prove signed video queries do not persist. / 保留针对 `note_url`、`image_list`、`video_url`、`xsec_token` 与 `xsec_source` 的小红书持久 raw 清理，并证明签名视频 query 不会持久化。

3. **Prove process and refresh contracts / 证明进程与刷新合约 — complete / 已完成**
   - Extend the real isolated fake-checkout creator contract with a video row and confirm bounded creator mode, exact URL selection, DEFAULT profile, cleanup and repr-safe authority handling. / 用视频行扩展真实隔离 fake-checkout 作者合约，确认有界 creator 模式、精确 URL 选择、DEFAULT profile、清理及 repr-safe 权限处理。
   - Add unit matrices for video-only, optional-cover, malformed+valid and duplicate raw candidates, empty/whitespace segments, container drift, foreign/false-suffix/IPv6 hosts, case/trailing-dot/IDNA handling, default/custom ports, root path/fragment, duplicate matching rows and explicit note compatibility. / 增加单元矩阵，覆盖纯视频、可选封面、畸形+有效及重复原始候选、空/空白分段、容器漂移、外部/伪后缀/IPv6 host、大小写/尾点/IDNA 处理、默认/自定义 port、根路径/fragment、重复匹配行及显式 note 兼容。

4. **Compose download, archive and Emby / 组合下载、归档与 Emby — complete / 已完成**
   - Add an offline end-to-end XHS creator-video test using exact SQLite provenance, a fake detail runner, mock DNS/HTTP, controlled MP4/PNG and a recording video probe; independently validate an embedded real H.264 MP4 through production `FFprobeMediaProbe`. / 增加小红书作者视频离线端到端测试，使用精确 SQLite 来源、fake detail runner、mock DNS/HTTP、受控 MP4/PNG 及记录型视频 probe；另让内嵌真实 H.264 MP4 独立通过生产 `FFprobeMediaProbe`。
   - Assert immutable archive paths/checksums, Emby primary `.mp4`, optional poster/NFO/source output, generation stability and zero-work replay. / 断言不可变归档路径/校验和、Emby 主 `.mp4`、可选 poster/NFO/source 输出、generation 稳定及零工作重放。

5. **Verify and close / 验证与收尾 — complete except self-referential closeout push / 除无法自引用的收尾推送外均已完成**
   - Run focused pytest, Ruff check/format, strict mypy, complete pytest, compileall, upstream locks, build, documentation, retained-artifact and Git diff gates. / 运行专项 pytest、Ruff check/format、严格 mypy、完整 pytest、compileall、上游锁、构建、文档、保留产物及 Git diff 门禁。
   - Update all four execution documents plus README, architecture, platform-capability and roadmap truth without promoting offline evidence to live qualification. / 更新四份执行文档以及 README、架构、平台能力与路线图真值，不把离线证据提升为真人验收。
   - Create and push separate bilingual plan, implementation and closeout commits; reconcile local, tracking and GitHub SHAs after every push. / 分别创建并推送双语计划、实现与收尾提交；每次推送后核对本地、跟踪与 GitHub SHA。

## Commit sequence / 提交序列

1. `c9d3586` — `docs: 启动小红书可播放视频闭环 / start XHS playable-video pipeline` — pushed / 已推送
2. `356e254` — `feat: 闭环小红书可播放视频 / close XHS playable-video pipeline` — pushed / 已推送
3. `docs: 收尾小红书可播放视频闭环 / close XHS playable-video pipeline` — ready to commit/push; its SHA cannot be self-referenced / 已可提交/推送；其 SHA 不能自引用

`.upstream` remains excluded and both pinned checkouts remain clean. / `.upstream` 继续排除在跟踪外，两个锁定 checkout 均保持干净。
