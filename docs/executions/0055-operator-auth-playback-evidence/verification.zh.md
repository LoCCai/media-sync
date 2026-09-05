[English](verification.md) | **中文**

# 执行 0055 阶段 A 验证

- 状态：后端鉴权与观察身份/持久账本检查点均已发布；确认 service/API 尚未实现
- 日期：2026-09-05
- 规划基线：`d0a8cc2`；鉴权实现基线：`4564b2a`
- 已发布鉴权提交：`f19bfaa`
- 已发布持久化提交：`1d5b448`
- 当前 revision：`0008_playback_evidence`

## 证据政策

规划检查只能证明切片范围明确且基于当前代码。下方已发布证据证明 `f19bfaa` 的后端鉴权契约；较新的专项证据只证明已在 `1d5b448` 发布的 observation identity 与持久化原语。它尚不能证明 confirmation service/API、Web 登录/确认表面、qualification schema v3、真实服务器兼容或获授权真人播放。实现证据与真人资格继续分开。

## 规划基线证据

| 检查 | 命令或来源 | 状态 |
| --- | --- | --- |
| Git 同步 | `git fetch --prune origin`；比较 `HEAD...origin/main` | `PASS`——规划修改前两者均为 `d0a8cc2`，分叉 `0 0` |
| 初始工作树 | `git status --short` | `PASS`——0054-B 收尾后只剩既有未跟踪 `.mimosa/` |
| 前一冻结门 | 执行 0054-B verification | `PASS`——Python 2763 项通过、3 项跳过、1 个既有 warning，其中含 11 项真实 PostgreSQL Operation 竞态；Web 69 项及记录的全部质量门通过 |
| 路由清单 | 检查 `create_api_app` 与 `app.routes` | `PASS`——51 条基线路由；没有 auth dependency/middleware；goal/plan 已记录敏感路由类别 |
| Secret/脱敏复用 | `config.py`、`security/secrets.py`、`security/redaction.py` | `PASS`——已有类型化 env/file/keyring reference 与安全 value wrapper；没有 operator auth setting |
| Publication/evidence 复用 | Publication resolver、observation service、qualification schema v2、DB models/migrations | `PASS`——已有完整 publication 权威与安全 item fingerprint；没有经鉴权播放账本 |
| 范围复核 | 0053/0054 待办记录与 security review | `PASS`——操作者鉴权和 playback evidence 归 0055；破坏性/可写运维尚未另行冻结 |
| 双语规划集 | 复核 goal、plan、progress、verification 四组中英文配对 | `PASS`——八份文件保持相同冻结范围，并明确写明实现尚未开始 |
| 文档与上游 | `uv run --frozen python scripts/check_docs.py`；`uv run --frozen python scripts/check_upstreams.py` | `PASS`——498 份 Markdown 链接有效，两个锁定上游 checkout 均匹配 pin |
| 预期跟踪集合 | 对当前 787 个跟踪文件与八份新执行文档执行仓库根级 generated/runtime denylist | `PASS`——提交后预期为 795 个跟踪文件；未选择禁止产物，既有 `.mimosa/` 保持未跟踪 |
| 机密性与工作站路径 | 扫描 14 个预期修改/新增文件中的工作站路径、私钥/token 形状及已赋值 secret | `PASS`——零匹配 |
| 空白 | `git diff --check` | `PASS` |

## 已发布后端鉴权证据

本节所有结果均作为已推送提交 `f19bfaa` 的历史证据保留，不能解读成较新 commit-3 工作树已完成完整回归。

| 检查 | 命令或来源 | 状态 |
| --- | --- | --- |
| 远端刷新 | `git fetch --prune origin`；实现提交前比较 | `PASS`——首次 GitHub TLS EOF 瞬断后重试成功；规划提交继续是共同基线 |
| Auth/config/API 专项并集 | 对 config、三个 operator-auth 模块及七个既有 API 模块运行 `uv run --frozen pytest -q` | `PASS`——190 项通过（41.99 秒）；只有一个既有 Starlette/httpx 弃用 warning |
| Runtime/origin 回归 | `tests/unit/test_operator_auth.py` | `PASS`——包含旧凭据登录与轮转的确定性竞态、精确 loopback/non-loopback origin 姿态、Host/auth/CSRF/Bearer 优先级、限流、过期/登出、严格提取及进入 handler 前拒绝 |
| API 边界回归 | `tests/unit/test_operator_auth_api.py` | `PASS`——枚举 57 个 route object；仅精确匿名 method/path 表、含递归 JSON 的严格 login body、write-only OpenAPI 输入、cookie flags、仅浏览器路由及原始 ASGI legacy HEAD body 清空 |
| 符合浏览器现实的 API helper | `tests/unit/_api_client.py` 与七个既有 API 模块 | `PASS`——只为不安全方法注入 Origin/CSRF；直接 QR/archive GET/HEAD/Range 与 SSE 依赖同源 session cookie，不带 Authorization 或 URL token |
| 绑定前失败/Compose 拓扑 | `tests/unit/test_operator_auth_cli.py`；检查 `docker-compose.example.yml` | 代码为 `PASS`——缺失/无法解析/弱凭据及 wildcard bind 缺 origin 均在绑定前停止；显式 `0.0.0.0` + 宿主 loopback HTTP origin 成功。Compose 现挂载 credential secret 并声明该 origin |
| Docker Compose 可执行检查 | `docker compose -f docker-compose.example.yml config --quiet` | `NOT_RUN`——本工作站未安装 Docker CLI；不声明容器已启动 |
| 静态类型 | `uv run --frozen mypy --strict src/media_sync` | `PASS`——104 个源文件零错误 |
| 完整 Python 回归 | `uv run --frozen pytest -q` | `PASS`——2811 项通过、14 项跳过、1 个 warning，耗时 561.43 秒。3 项 skip 是 Windows 不适用的 POSIX launcher/mode 用例；11 项是因未设置 `MEDIA_SYNC_TEST_POSTGRESQL_URL` 而跳过的既有真实 PostgreSQL Operation 竞态；warning 是既有 Starlette/httpx 弃用 |
| Web 回归与构建 | 在 `web/` 运行 `npm run format:check`、`npm test -- --run`、`npm run check`、`npm run build` | `PASS`——格式干净，7 个文件/69 项测试通过，Svelte 零 error/warning，静态生产构建完成。这些既有测试不声明尚未实现的 Web 登录客户端 |
| 全仓质量 | `uv run --frozen ruff check .`、`ruff format --check .`、strict mypy、`python -m compileall -q src tests` | `PASS`——全部检查通过，722 个文件格式正确，104 个类型检查源文件干净，字节编译干净 |
| 文档与锁定上游 | `scripts/check_docs.py`；`scripts/check_upstreams.py` | `PASS`——498 份 Markdown 与两个锁定 checkout 均验证通过 |
| Distribution | 隔离目录 `uv build --out-dir ...`；用 `zipfile`/`tarfile` 检查 wheel/sdist | `PASS`——生成一个 wheel 与一个 sdist；wheel 共 121 项且包含 auth、legacy console 与 migration template，sdist 共 832 项；两者都没有 `.env`/SQLite 输出 |
| 提交前仓库门 | 显式 46 文件 index；`git ls-files`；generated/runtime 与敏感模式扫描；冻结 goal/plan diff；`git diff --cached --check`；比较 `HEAD...origin/main` | `PASS`——800 个 index 文件，禁止输出与敏感匹配均为零，冻结 goal/plan 未变化，分叉 `0 0`，无未暂存 tracked 改动，且只剩既有 `.mimosa/` 未跟踪 |

## 观察身份与持久账本检查点证据

| 检查 | 命令或来源 | 状态 |
| --- | --- | --- |
| 鉴权发布基线 | `git log`；已发布仓库状态 | `PASS`——commit-3 开始前，关闭失败的单操作者鉴权已提交并推送为 `f19bfaa` |
| 持久化发布 | 最终 fetch、暂存集合审计、commit、push 与 `HEAD...origin/main` 比较 | `PASS`——38 个预期文件已提交并推送为 `1d5b448`；分叉为 `0 0`，`.mimosa/` 保持未跟踪，且没有已暂存或未暂存 tracked 变更 |
| 只为 matched 生成的观察身份 | `media_server_observation_fingerprint`；`MediaServerAuthorLookupResult`；Web `MediaServerAuthorLookup` discriminated type；observation 单元/API 回归 | `PASS`——带域分隔的 v1 digest 仅为唯一 `matched` 结果绑定规范 author ID 与 profile/publication/selector/item digest；`not_found` 不暴露 item 或 observation fingerprint，也不保留原始 item ID；Web 类型同步该区分但不声明 confirmation UI 已实现 |
| Revision 与 ORM 契约 | `0008_playback_evidence.py`；`PlaybackEvidence`；migration/model 回归 | `PASS`——migration 与 model metadata 均强制 schema version、规范 UUID、小写 SHA-256、时间戳顺序、唯一 observation identity、author/time 索引及 Author/Job `RESTRICT` constraint |
| 受保护 downgrade | revision 0008 migration 回归 | `PASS`——拒绝 offline downgrade，含行账本会阻止 downgrade，只有在线审计确认的空账本可被移除 |
| 自然重放 | `PlaybackEvidenceRepository`；SQLite repository 回归 | `PASS`——不可变自然身份会重放首个持久行及其时间戳；冲突复用 observation fingerprint 返回固定冲突码，validation/FK/check 失败不会变成重放成功 |
| SQLite transaction 与竞态 | repository statement/rollback/concurrency 回归 | `PASS`——首个自然键读取受 `BEGIN IMMEDIATE` 保护，insert 局限于 savepoint 且不提交调用方 transaction；不安全的既有 deferred writer transaction 被拒；并发相同/冲突请求只留下一个持久胜出行 |
| PostgreSQL repository 语义 | repository 实现与 8 项专用 PostgreSQL 竞态测试 | `NOT_RUN`——实现使用 unique constraint、savepoint rollback 与 `READ COMMITTED` 下的胜出行重读，但因未设置 `MEDIA_SYNC_TEST_POSTGRESQL_URL`，8 项可执行竞态全部跳过 |
| Migration/repository 子集 | migration、SQLite repository 与 PostgreSQL-race 专项选择 | `PASS`——42 项通过、8 项跳过；所有 skip 均为上述未配置 PostgreSQL 用例 |
| Commit-3 专项并集 | observation/API/migration/repository/PostgreSQL-race 专项回归选择 | `PASS`——129 项通过、8 项跳过、1 个既有 Starlette/httpx 弃用 warning |
| 检查点文档 | `uv run --frozen python scripts/check_docs.py`；对四份可变 0055 progress/verification 文件运行 `git diff --check` | `PASS`——498 份 Markdown 链接有效，检查点文档无空白错误 |
| 当前完整 Python 回归 | `uv run --frozen pytest -q` | `PASS`——2868 项通过、22 项跳过、1 个既有 Starlette/httpx warning，耗时 558.19 秒（`0:09:18`）。Skip 分为 3 项 Windows/POSIX 差异、11 项既有 Operation PostgreSQL 用例与 8 项新增 PlaybackEvidence PostgreSQL 竞态；因未设置 `MEDIA_SYNC_TEST_POSTGRESQL_URL`，19 项 PostgreSQL 用例继续为 `NOT_RUN` |
| 当前 Web 回归与构建 | 在 `web/` 运行 `npm run format:check`、`npm test -- --run`、`npm run check`、`npm run build` | `PASS`——格式干净，7 个文件/69 项测试通过，Svelte 为 0 error/0 warning，production build 完成；不声明尚未实现的登录/确认表面 |
| 当前代码质量 | `uv run --frozen ruff check .`、`ruff format --check .`、`uv run --frozen mypy --strict src/media_sync`、`python -m compileall -q src tests` | `PASS`——Ruff check 通过，修正 1 个纯格式差异后 727 个文件全部通过 format，strict mypy 对 105 个源文件通过，字节编译干净 |
| 当前 Distribution | 在系统临时目录隔离执行 `uv build`；用 `zipfile`/`tarfile` 检查 wheel/sdist | `PASS`——精确生成 1 个含 123 项的 wheel 与 1 个含 837 项的 sdist；两者均包含 `playback_evidence_repository.py` 和 `0008_playback_evidence.py`，且 `.env` 或 SQLite 输出为零 |
| 端到端能力边界 | 检查当前 service/API/qualification/Web 表面 | `NOT_IMPLEMENTED`——confirmation service/API、双重 resolve TOCTOU 封闭、qualification schema v3、Web 登录生命周期与只允许 matched 的 Web 确认均尚不存在；真人播放仍为 `NOT_RUN` |

## 验证尝试记录

1. 首次 `git fetch --prune origin` 因 GitHub TLS unexpected EOF 瞬断失败；立即重试成功，分叉检查保持干净。
2. `docker compose ... config --quiet` 因本 Windows 工作站没有 Docker executable 而无法启动；备用 PyYAML parser 同样不可用。策略与 manifest 接线已有单元测试和只读检查，但真实 Compose 解析/启动仍明确为 `NOT_RUN`。
3. 隔离 `uv build` 首次即构建成功。第一版 wrapper assertion 把 uv 生成的 `.gitignore` 也计为 package，因而非零退出；修正过滤后验证为精确一个 wheel + 一个 sdist。第一版内容断言误以为 standalone wheel 会包含只在 Docker build 中复制的 Console v2；修正后的 distribution 契约验证 wheel 中的 legacy console，而独立 Web production build 已验证 Console v2。
4. 第一版 tracked-output denylist 过宽，把合法文档目录 `docs/archive/` 与 Web 路由 `routes/jobs/` 错判成 runtime root。修正为根路径感知后检查 800 个 index 文件，禁止的 generated/runtime 输出为零。独立 staged-diff 扫描中，工作站路径、私钥、GitHub/OpenAI/AWS token 及已赋值 production operator secret 匹配均为零。
5. Commit-3 的 migration/repository 选择发现了全部 8 项专用 PostgreSQL 竞态测试，但因未设置 `MEDIA_SYNC_TEST_POSTGRESQL_URL` 而跳过。测试已存在并被收集不等于已执行，因此 PostgreSQL 继续为 `NOT_RUN`。
6. 当前 commit-3 工作树的完整 Python 套件在 558.19 秒（`0:09:18`）内完成：2868 项通过、22 项跳过、1 个既有 warning。该结果与历史 `f19bfaa` 的 2811 项通过分开记录。3 项 Windows/POSIX skip 与两组未配置 PostgreSQL 用例——11 项既有 Operation 加 8 项新增 PlaybackEvidence 竞态——均被显式保留；不声明 PostgreSQL 已执行。
7. 当前 Ruff format 首次检查发现 1 个纯格式差异。格式化该源码后，复跑对 727 个文件通过；Ruff check、105 个源文件 strict mypy 与 compileall 也均通过。不从这次纯格式修正推导额外行为通过声明。
8. 首次 distribution wrapper 在当前 PowerShell 环境中向 `New-Item` 传入了不支持的 `-LiteralPath` 参数。`uv build` 仍自行创建隔离输出目录并成功；修正后的内容检查验证精确 1 个 wheel 与 1 个 sdist，且产物和文档均未嵌入工作站路径。

## 已关闭审查问题

1. Login 现会在与 credential rotation 相同的锁内读取并比较 browser digest。确定性并发回归证明以旧凭据开始的 login 在轮转完成后不能留下有效 session；Bearer 读取同样加锁。
2. 显式 wildcard/container bind 不再仅因内部 bind 非回环而强制 HTTPS。每个浏览器 origin 仍独立规范化：HTTP 仅允许 loopback，非 loopback HTTP 被拒，混合 scheme 被拒，Secure cookie 跟随唯一接受的 scheme。
3. Login 会捕获有界深层 JSON 递归并返回固定 400；手工解析的请求在 OpenAPI 中保留为一个 required、禁止额外字段且 write-only 的 credential 字段。
4. 最外层边界清空所有 downstream HEAD body 并保留 representation header；自身拒绝的 HEAD 保留对应 GET representation 长度且不发 body。Health、readiness 与 archive 的 GET/HEAD 分离注册，不再产生重复 OpenAPI operation ID。
5. 共享 authenticated client 不再给安全方法附加 CSRF header，消除了无法设置自定义 header 的浏览器原语上的假证据。

## 剩余实现证据

当前检查点已关闭冻结退出门中的本地 fingerprint、revision/model、受保护 downgrade、自然重放与 SQLite 部分。剩余工作仍须为以下内容提供精确 passing evidence：

1. 实现 resolve → unique lookup → resolve 的 TOCTOU 封闭、经鉴权 confirmation service/API 与全部失败零写入路径。
2. 实现 qualification schema v3 真值：无证据为 `IMPLEMENTED/NOT_RUN`，只有精确当前 evidence 可 PASS，stale 绝不 PASS，provider completion/automatic scan 保持未实现。
3. 实现并验证 Web login/session/logout/expiry 生命周期、内存 CSRF 注入、集中 401 reset、cookie-only EventSource/直接媒体行为，以及可访问且只允许 matched 的播放确认交互。
4. 在安装 Docker 的主机上完成真实 Docker/Compose 配置与启动检查。
5. 在已配置主机上运行 8 项 PlaybackEvidence PostgreSQL 竞态并重跑此前跳过的 PostgreSQL 覆盖；源码检查不能替代执行。
6. 通过最终仓库、包与发布扫描继续保证 credential/session/CSRF/reference/raw selector 零保留。
7. 剩余实现完成后重跑完整 Python/Web 及全部质量/包/文档/上游/generated-output/host-path/secret/空白门，再完成 Git 发布门。

## 真人资格

尚未运行任何 0055-A 真人鉴权或真实 Emby/Jellyfin 播放。规划、mock、生成媒体、测试创建的数据库行与 item observation 都不能产生仓库中的真人 PASS。只有获授权操作者实际播放并显式确认精确当前 item 后，真人播放状态才可离开 `NOT_RUN`。

## 退出门

只有全部冻结本地要求均有精确证据、无剩余 P0/P1/P2、migration/rollback 安全、每条非公共路由默认拒绝，且保留输出不存在 credential/session/CSRF/raw selector，阶段 A 才可关闭。收尾仍须列明 0047 未执行真人行及全部排除的 0055 运维功能。
