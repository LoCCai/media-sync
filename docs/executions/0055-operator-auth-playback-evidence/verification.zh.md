[English](verification.md) | **中文**

# 执行 0055 阶段 A 验证

- 状态：仅规划证据；尚未运行实现验证
- 日期：2026-09-05
- 基线：`d0a8cc2`
- 计划 revision：`0008_playback_evidence`

## 证据政策

规划检查只能证明下一切片范围明确、可评审且基于当前代码，不能证明鉴权、授权、播放、真实服务器兼容或 migration 行为。实现证据与获授权真人资格继续分开。

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

## 必需实现证据

退出门必须对以下内容提供精确 passing evidence：

1. 凭据解析在绑定前关闭失败，以及非回环 origin 姿态。
2. 完整路由枚举拒绝，只有冻结匿名 allowlist 可访问。
3. 浏览器 session 轮转/过期/登出、cookie flags、CSRF、Host/Origin、Bearer、限流、固定错误与零 secret 留存。
4. QR、archive GET/HEAD/Range、EventSource、docs、legacy 与 SPA 通过已鉴权 cookie 工作且无 URL token。
5. Observation fingerprint 稳定/domain separation 及每个权威上下文漂移。
6. Resolve → unique lookup → resolve 的 TOCTOU 封闭与全部失败零写入。
7. Append-only revision 0008 constraint、自然 replay、SQLite/PostgreSQL 并发、RESTRICT parent 与受保护 downgrade。
8. Qualification schema v3 真值：无证据为 `IMPLEMENTED/NOT_RUN`，当前精确 evidence 才可 PASS，stale 绝不 PASS，provider completion 与 automatic scan 保持未实现。
9. Web login/expiry/logout 与只允许 matched 的显式播放确认，包括可访问性与如实文案。
10. 完整 Python 与串行 Web 套件，以及质量、包、文档、上游、generated-output、host-path、secret、空白与 Git 发布门。

## 真人资格

尚未运行任何 0055-A 真人鉴权或真实 Emby/Jellyfin 播放。规划、mock、生成媒体、测试创建的数据库行与 item observation 都不能产生仓库中的真人 PASS。只有获授权操作者实际播放并显式确认精确当前 item 后，真人播放状态才可离开 `NOT_RUN`。

## 退出门

只有全部冻结本地要求均有精确证据、无剩余 P0/P1/P2、migration/rollback 安全、每条非公共路由默认拒绝，且保留输出不存在 credential/session/CSRF/raw selector，阶段 A 才可关闭。收尾仍须列明 0047 未执行真人行及全部排除的 0055 运维功能。
