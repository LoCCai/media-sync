# Execution 0012 verification / 执行 0012 验证

- Status / 状态：Baseline only; implementation gates not yet run / 仅完成基线；实现门禁尚未运行
- Environment / 环境：Windows, local workspace, Python environment resolved by `uv` / Windows、本地工作区、由 `uv` 解析 Python 环境
- Evidence date / 证据日期：2026-08-31

## Starting baseline / 起始基线

| Check / 检查 | Command / 命令 | Exit / 退出码 | Result / 结果 |
| --- | --- | ---: | --- |
| Existing generic hard-parent-death plus login normal timeout/cancellation / 既有通用父进程硬终止及登录正常超时/取消 | `uv run pytest -q tests/contract/test_mediacrawler_supervision.py::test_hard_parent_death_stops_real_child_tree_and_allows_safe_recovery tests/contract/test_mediacrawler_login.py::test_timeout_and_cancellation_join_the_complete_process_tree` | `0` | `PASS` — `3 passed in 8.15s` |

This baseline proves only the predecessor generic runner's hard-parent-death containment and the login runner's live-parent timeout/cancellation join. It does not prove login hard-parent-death handling, durable stale-session recovery or a resident supervisor. / 此基线只证明前置通用 runner 的父进程硬终止收容，以及登录 runner 在父进程存活时的超时/取消 join；不证明登录父进程硬终止处理、持久 stale-session 回收或常驻监督器。

## Planned focused gates / 计划中的专项门禁

| Scope / 范围 | Evidence required / 所需证据 | Status / 状态 |
| --- | --- | --- |
| Login parent control / 登录父进程控制 | Framed request, START gate, CANCEL/EOF/malformed control, setup failure and normal completion tests / 请求 framing、START gate、CANCEL/EOF/非法控制、初始化失败及正常完成测试 | `NOT_RUN` |
| True login parent death / 真实登录父进程死亡 | Windows/POSIX owned child/grandchild termination and account-lock recovery / Windows/POSIX 所属 child/grandchild 终止及账户锁恢复 | `NOT_RUN` |
| Durable recovery / 持久回收 | Deadline edge, exact CAS, drift, idempotency, concurrent contender, successor and rollback tests / 截止边界、精确 CAS、漂移、幂等、并发竞争者、继任与回滚测试 | `NOT_RUN` |
| Resident supervision / 常驻监督 | Fair sweep/tick/sync/pipeline cycles, Fake full-chain success, idle wake, bounded options, sync cancel/join and pipeline single-attempt drain / 公平 sweep/tick/sync/pipeline cycle、Fake 全链成功、空闲唤醒、有界参数、sync 取消/join 与 pipeline 单项 drain | `NOT_RUN` |
| Closed sinks / 封闭落点 | CLI/SQLite/filesystem/docs/Git secret and profile-path checks / CLI/SQLite/文件系统/文档/Git 密钥与 profile 路径检查 | `NOT_RUN` |

## Complete closeout gates / 完整收尾门禁

Full pytest, Ruff lint and format, mypy, documentation links, pinned upstream verification, package build, whitespace check and final retained-artifact/secret audit remain `NOT_RUN`. No implementation completion or live qualification is claimed by this planning record. / 完整 pytest、Ruff lint 与格式、mypy、文档链接、锁定上游验证、包构建、空白检查及最终保留产物/密钥审计仍为 `NOT_RUN`。本计划记录不宣称实现完成或真人验收通过。
