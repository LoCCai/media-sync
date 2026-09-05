[English](verification.md) | **中文**

# 执行 0055 阶段 A 验证

- 状态：投影／资格 v3 已发布为 `2e1949f`；当前安全控制台／迁移前预检已实现且本地合成浏览器门禁已通过，准确当前门见 secure-console 子记录
- 日期：2026-09-05
- 规划基线：`d0a8cc2`；鉴权实现基线：`4564b2a`
- 已发布鉴权提交：`f19bfaa`
- 已发布持久化提交：`1d5b448`
- 已发布确认提交：`13de3b7`；投影冻结规划提交：`9fd74de`
- 已发布投影提交：`2e1949f`；当前安全控制台冻结计划：`714c849`
- 当前 revision：`0008_playback_evidence`

## 证据政策

本父记录保留各历史提交的验证，含 `2e1949f` 投影的 2999 项完整门；这些不替代当前安全控制台版本。当前 login/session／内存 CSRF／QR／SSE 与迁移前预检已实现，已通过[本地合成浏览器验证](secure-console/verification.zh.md)。当前 Python 完整套件为 3155 项通过、22 项跳过、1 个既有 warning，670.16 秒；Web 9 文件／114 项及 check/build、本地合成浏览器门已通过，视频仅加载／解码、未点击播放；其后仅 fixture 只读增强专项 4 项通过（1.76 秒），不是新的全量数量。发布证据以子记录为准。历史审查“无 P0/P1/P2”不关闭新交付核查问题；实现、当前镜像验证与真人资格分开，全部未执行平台／媒体服务器真人行仍为 NOT_RUN。

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

本节保留 `1d5b448` 的历史证据和后续确认拆分时的能力边界；其中“当前”指当时检查点，不代表本次投影版本。最新结果见下方投影检查点。

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
| 当时端到端能力边界 | 确认拆分时的 service/API/qualification/Web 表面 | 历史 `PARTIAL`——当时确认 service/API 已存在，而投影、qualification v3 与 Web 登录／确认尚缺；schema v2 当时将整体播放证据标为 `NOT_IMPLEMENTED`。本次投影已更新该后端状态，Web 与真人验收仍未完成 |

## 确认 service 与仅浏览器 POST 检查点证据

本节为已发布 `13de3b7` 的历史证据，包括 2941 项／594.72 秒结果；不替代当前投影回归。该检查点当时有意拆分冻结 commit boundary 4，使安全敏感的写入路径可独立审查，并完成交付项 10 与交付项 11 的 POST 半项。当时后续的按作者投影与 qualification v3 现已实现，最新证据见下节。

| 检查 | 命令或来源 | 状态 |
| --- | --- | --- |
| 确认权威 | `PlaybackEvidenceService.confirm`；service 单元与组合回归 | `PASS`——强制规范请求身份、一个不超过 120 秒的绝对 deadline、resolve A → 一次完整唯一 lookup → resolve B、精确 target/profile/observation 重校验与失败零写入 |
| 锁与事务顺序 | 确定性 event/lock 测试；service 只读审查 | `PASS`——外部工作完成后总是先释放 authority lock，再打开短数据库事务；create/replay 提交后才发送成功审计 |
| 仅浏览器端点 | `POST /api/v1/media-server/playback-evidence`；API/auth 测试 | `PASS`——要求精确 Cookie/Origin/CSRF；Bearer-only 与 Cookie 搭配任意 Authorization 均在 handler/读取 body 前固定 403 拒绝 |
| 严格请求与最小响应 | endpoint/parser/OpenAPI 测试 | `PASS`——唯一 JSON Content-Type、最大 1 KiB、member 唯一、精确规范 UUID/小写 digest 字段且禁止 `Idempotency-Key`；create/replay 都返回 201 与精确六个安全字段，不含 fingerprint/context selector |
| 固定失败边界 | service/API 失败矩阵 | `PASS`——invalid、not-confirmable、identity-conflict、confirmation-unavailable 与 store-unavailable 路径只使用固定且不反射的 code；authority/store 失败不发送成功审计 |
| Service/API 专项门 | 专用测试选择 | `PASS`——service 单元 18、SQLite 组合 2、endpoint 51、service/API/auth 并集 108、media-server API 47，以及较宽并集 289 项通过、8 项 PostgreSQL 预期跳过 |
| 路由清单 | 精确 `app.routes` 枚举 | `PASS`——58 个 route object；匿名 allowlist 不变，新 mutation 只允许浏览器 |
| 独立审查 | service/transaction、API/auth 与最终发布门审查 | `PASS`——前两次审查未发现 P0/P1/P2；最终门发现 1 个默认运行时审计可见性 P2，现已通过复制 Uvicorn 应用日志配置及无 socket subprocess 回归关闭。该确认写入审查范围内没有遗留问题；后续交付核查中的 P0 仍待解决 |
| 应用与 migration 日志 | 复制 Uvicorn log config；无 socket 审计 subprocess；embedded-Alembic root 继承 subprocess | `PASS`——默认 `serve` 会为 `media_sync` 配置 stderr handler，同时保留 Uvicorn 默认配置；固定 playback 与 operator-auth INFO 码可见且不反射私有 sentinel。Programmatic Alembic INI 运行不会替换调用方 root level/handler 或继承 INFO logging |
| 当前 Web 与静态门 | `pnpm format:check`；`pnpm test`；`pnpm check`；`pnpm build`；Ruff/format；strict mypy；compileall | `PASS`——Web 7 文件/69 项测试、Svelte 0 error/0 warning 与 production build；731 个格式文件、106 个类型检查源文件及字节编译通过 |
| 文档/上游/Distribution | docs/upstream 检查；隔离 `uv build` 检查 | `PASS`——498 份 Markdown 与两个干净锁定上游通过；显式忽略 `.mimosa/` 后，一个 124 项 wheel 与一个 810 项 sdist 包含 service/repository/revision，且不含运行时/工具历史/数据库输出 |
| Docker 与 PostgreSQL 执行 | executable/environment 检查 | `NOT_RUN`——Docker executable 不可用且未设置 `MEDIA_SYNC_TEST_POSTGRESQL_URL`；源码/测试不能替代执行 |
| 全部日志修复后的完整 Python 回归 | `uv run --frozen pytest -q` | `PASS`——594.72 秒（`0:09:54`）内 2941 项通过、22 项跳过、1 个既有 Starlette/httpx warning。3 项 skip 为 Windows/POSIX 差异；11 项 Operation 与 8 项 PlaybackEvidence PostgreSQL 用例因未设置测试 URL 继续为 `NOT_RUN` |

## 已发布作者投影与资格 v3 历史证据

本节对应 `2e1949f`；“当前”指当时投影版本。最新安全控制台结果见[当前验证](secure-console/verification.zh.md)。

完整命令、尝试记录与最终文档／包／Git 门见[投影验证](evidence-projection/verification.zh.md)。以下摘要只涵盖本次实际已运行的门。

| 检查 | 命令或来源 | 状态 |
| --- | --- | --- |
| 有界读取与资格范围 | query service/API／SQLite／qualification 回归 | `PASS`——Cookie/Bearer 读取、严格 UUID/query、默认 20／最多 50 条历史、最多 `limit + 2` 物化行、精确当前行独立查询、59 路由鉴权清单；无作者不查账本／远端 |
| 当前权威与截断 | authority／deadline／事务顺序／真实 SQLite SQL 捕获 | `PASS`——完整稳定远端权威与不可变字段精确匹配的持久行才可 scoped PASS；远端 lookup 截断不能 PASS，历史页截断不否定独立当前行；不确定历史为 unknown，完整不存在为 stale；全部外部工作先于短读取事务，无 COUNT 或写入 |
| 最终专项并集 | 投影／确认／API／鉴权／资格／SQLite 测试选择 | `PASS`——220 项通过、1 个既有 warning，51.09 秒 |
| 完整 Python 回归 | `uv run --frozen pytest -q` | `PASS`——2999 项通过、22 项跳过、1 个既有 Starlette/httpx warning，613.66 秒；3 项 Windows/POSIX 差异，11 项 Operation 与 8 项 PlaybackEvidence PostgreSQL 用例未配置而跳过，不声明真实 PostgreSQL 已运行 |
| Web 与已确认静态门 | `pnpm test`、`pnpm format:check`、`pnpm check`、`pnpm build`；strict mypy／format | `PASS`——7 文件／69 项 Web 测试、零 Svelte error/warning、production build；107 个源文件 mypy、743 文件 format。只更新响应类型，不声明新增登录或确认 UI |
| 真人与部署边界 | 当前工作站能力及仓库资格记录 | `NOT_RUN`——Docker／真实 PostgreSQL／当前镜像浏览器组合／平台及媒体服务器真人流程；测试行或 scoped PASS 夹具不改变真人资格 |

## 验证尝试记录

1. 首次 `git fetch --prune origin` 因 GitHub TLS unexpected EOF 瞬断失败；立即重试成功，分叉检查保持干净。
2. `docker compose ... config --quiet` 因本 Windows 工作站没有 Docker executable 而无法启动；备用 PyYAML parser 同样不可用。策略与 manifest 接线已有单元测试和只读检查，但真实 Compose 解析/启动仍明确为 `NOT_RUN`。
3. 隔离 `uv build` 首次即构建成功。第一版 wrapper assertion 把 uv 生成的 `.gitignore` 也计为 package，因而非零退出；修正过滤后验证为精确一个 wheel + 一个 sdist。第一版内容断言误以为 standalone wheel 会包含只在 Docker build 中复制的 Console v2；修正后的 distribution 契约验证 wheel 中的 legacy console，而独立 Web production build 已验证 Console v2。
4. 第一版 tracked-output denylist 过宽，把合法文档目录 `docs/archive/` 与 Web 路由 `routes/jobs/` 错判成 runtime root。修正为根路径感知后检查 800 个 index 文件，禁止的 generated/runtime 输出为零。独立 staged-diff 扫描中，工作站路径、私钥、GitHub/OpenAI/AWS token 及已赋值 production operator secret 匹配均为零。
5. Commit-3 的 migration/repository 选择发现了全部 8 项专用 PostgreSQL 竞态测试，但因未设置 `MEDIA_SYNC_TEST_POSTGRESQL_URL` 而跳过。测试已存在并被收集不等于已执行，因此 PostgreSQL 继续为 `NOT_RUN`。
6. 当前 commit-3 工作树的完整 Python 套件在 558.19 秒（`0:09:18`）内完成：2868 项通过、22 项跳过、1 个既有 warning。该结果与历史 `f19bfaa` 的 2811 项通过分开记录。3 项 Windows/POSIX skip 与两组未配置 PostgreSQL 用例——11 项既有 Operation 加 8 项新增 PlaybackEvidence 竞态——均被显式保留；不声明 PostgreSQL 已执行。
7. 当前 Ruff format 首次检查发现 1 个纯格式差异。格式化该源码后，复跑对 727 个文件通过；Ruff check、105 个源文件 strict mypy 与 compileall 也均通过。不从这次纯格式修正推导额外行为通过声明。
8. 首次 distribution wrapper 在当前 PowerShell 环境中向 `New-Item` 传入了不支持的 `-LiteralPath` 参数。`uv build` 仍自行创建隔离输出目录并成功；修正后的内容检查验证精确 1 个 wheel 与 1 个 sdist，且产物和文档均未嵌入工作站路径。
9. 首轮确认检查点完整套件达到 2938 项通过与 22 项预期跳过，但一项审计日志断言失败。该失败与顺序相关：较早的 Alembic INI migration 使用标准库默认值禁用了已创建的 logger。持久 service 结果正确，但静默丢失固定审计事件不可接受。
10. 第一版缓解保留了既有命名 logger，并得到一次完整的 `2940 passed, 22 skipped, 1 warning in 578.68s` 运行。独立复审随后发现嵌入式 Alembic 仍可能把调用方 root logger 降到 `WARNING`；该通过结果作为中间证据保留，不作为发布结果。
11. 确认残余 root-logger 风险后，后续完整套件在约 7% 处被主动中止，避免让过时实现继续消耗完整门禁。Alembic 日志配置现仅用于 standalone CLI（存在 `cmd_opts`）；嵌入式 programmatic `Config(alembic.ini)` 会保留调用方日志。Subprocess 回归证明 root handler identity、继承 INFO enablement 与实际固定审计记录，且不污染父测试进程。随后 frozen-environment 复跑在 588.32 秒（`0:09:48`）内完成 2940 项通过、22 项预期跳过与 1 个既有 warning；它是下一版发布候选，后来由第 14 项结果取代。
12. 第一版新制品内容断言把有意随附的 `.env.example` 错当成 secret `.env`。修正后的精确文件名检查通过，同时继续拒绝真实 `.env`、SQLite 文件与运行时根目录。
13. 扩展 package denylist 随后发现 Hatch 因 `.mimosa/` 未被忽略而把这棵未跟踪 finding/history 树收入 sdist。`.mimosa/` 现已明确写入 `.gitignore` 与 `.dockerignore`；全新隔离构建把 sdist 从 841 项降至 810 项，严格 wheel/sdist 扫描与 ignore 检查证明工具历史根目录不会进入 distribution 或 build context。
14. 最终发布审查随后证明默认 Uvicorn 日志不会让 `media_sync.*` INFO 审计可见。`serve` 现会传入复制后的日志配置，按已校验级别为该命名空间增加独立 stderr handler，同时保留 Uvicorn 默认配置并继续关闭 access log。无 socket 审计回归通过；修复后的最终完整套件在 594.72 秒（`0:09:54`）内通过 2941 项、按预期跳过 22 项，并保留 1 个既有 warning。这一次才是发布结果。

## 已关闭审查问题

1. Login 现会在与 credential rotation 相同的锁内读取并比较 browser digest。确定性并发回归证明以旧凭据开始的 login 在轮转完成后不能留下有效 session；Bearer 读取同样加锁。
2. 显式 wildcard/container bind 不再仅因内部 bind 非回环而强制 HTTPS。每个浏览器 origin 仍独立规范化：HTTP 仅允许 loopback，非 loopback HTTP 被拒，混合 scheme 被拒，Secure cookie 跟随唯一接受的 scheme。
3. Login 会捕获有界深层 JSON 递归并返回固定 400；手工解析的请求在 OpenAPI 中保留为一个 required、禁止额外字段且 write-only 的 credential 字段。
4. 最外层边界清空所有 downstream HEAD body 并保留 representation header；自身拒绝的 HEAD 保留对应 GET representation 长度且不发 body。Health、readiness 与 archive 的 GET/HEAD 分离注册，不再产生重复 OpenAPI operation ID。
5. 共享 authenticated client 不再给安全方法附加 CSRF header，消除了无法设置自定义 header 的浏览器原语上的假证据。
6. 最终发布审查证明 Uvicorn 默认配置会让 `media_sync.*` INFO 审计低于 root 的有效阈值。`serve` 现会深复制而不修改 Uvicorn 默认配置，按已校验应用级别增加一个不向上传播的 `media_sync` stderr handler，并继续关闭 access log。无 socket subprocess 会输出两个固定 playback/operator-auth 审计码，且不含私有 sentinel。

## 剩余实现证据

当前检查点已关闭本地 fingerprint、revision/model、受保护 downgrade、自然重放、SQLite、确认权威、仅浏览器 POST、有界作者投影与资格 v3 的离线部分；P0 顺序见[交付优先级补充计划](delivery-priorities.zh.md)。剩余工作仍须提供精确 passing evidence：

1. 迁移前配置检查已实现；仍须在最终 Linux 镜像／实际映射 UID 下执行凭据可读性与失败先于迁移验证。Windows／替身进程结果不等于真实 Docker，配置预检也不证明 DNS／端口或运行就绪。
2. 当前[本地合成浏览器验证](secure-console/verification.zh.md)已在修复／复验后通过，覆盖 session／CSRF、QR／SSE、跨标签退出与自然过期；视频证据仅为加载／解码，未点击播放。P1 当前／历史证据与 matched-only 确认 UI 仍待实现，但不阻塞获授权 CLI 金丝雀。
3. 在安装 Docker 的 Linux 主机验证精确当前提交／镜像的配置、运行用户 secret 读取、迁移边界、启动、重启持久性与备份恢复，然后优先完成 Bilibili／小红书获授权金丝雀。历史镜像 PASS 不替代当前版本。
4. 在已配置主机上运行 8 项 PlaybackEvidence PostgreSQL 竞态并重跑此前跳过的 PostgreSQL 覆盖；源码检查不能替代执行。
5. 通过最终仓库、包与发布扫描继续保证 credential/session/CSRF/reference/raw selector 零保留。
6. 剩余实现完成后重跑完整 Python/Web 及全部质量/包/文档/上游/generated-output/host-path/secret/空白门，再完成 Git 发布门。

## 真人资格

尚未运行获授权真人平台账户登录或真实 Emby/Jellyfin 播放。当前真实本地浏览器鉴权使用可丢弃合成夹具，记录于[安全控制台验证](secure-console/verification.zh.md)，不授予平台、CDN 或媒体服务器资格。规划、mock、生成媒体、测试创建的数据库行与 item observation 都不能产生仓库中的真人 PASS。只有获授权操作者实际播放并显式确认精确当前 item 后，真人播放状态才可离开 `NOT_RUN`。

## 退出门

只有全部冻结本地要求均有精确证据、无剩余 P0/P1/P2、migration/rollback 安全、每条非公共路由默认拒绝，且保留输出不存在 credential/session/CSRF/raw selector，阶段 A 才可关闭。收尾仍须列明 0047 未执行真人行及全部排除的 0055 运维功能。
