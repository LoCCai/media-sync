[English](plan.md) | **中文**

# 执行 0008 计划

- 状态：已计划 — 实现前冻结
- 计划日期：2026-08-30
- 前置执行：Execution 0007 implementation commit `d071618`
- 网络策略：仅离线夹具与仓库自有本地辅助进程

## 冻结设计

### 封闭证据模型

- 执行 0008 是验收收口，不是功能捆绑；它只关闭执行 0007 的 AC6 与 AC13，并保留全部真人 `NOT_RUN` 及延期实现边界。
- 必需失败行在测试中冻结为 11 值封闭枚举：`known_secret_echo`、`nonzero_exit`、`timeout`、`output_bytes`、`output_items`、`output_files`、`output_line_bytes`、`output_tree`、`receipt_rejected`、`cancellation` 与 `lease_loss`。
- 每一行拥有一个只在运行时生成的哨兵，并记录三项显式断言：文件系统、SQLite 与运维输出。独立 completeness 测试把实际 cell key 与精确笛卡尔积比较；不接受抽样或隐含覆盖。

### 确定性取消 barrier

- child-exit/pre-seal 契约在既有最终检查/receipt 边界使用 event 或 pipe。测试先观察真实 helper 退出及整树 join，在 receipt 发布前阻塞，发出取消，再释放 barrier；不得用纯 sleep 建立 verdict。
- Runner 必须在最终输出检查之后、receipt 发布之前立刻复核取消；若已取消，则返回固定 cancelled 结果，外层清理会在释放账户/profile 锁前安全收口精确 attempt。
- post-seal/pre-ingest 契约在有效 receipt 可见后阻塞注入的 normalizer。一次或重复 task 取消必须记录取消、join 受保护的 offload task、安全收口 attempt，并在不执行 `_set_ingesting` 或导入写入的情况下 unwind。

### 失败矩阵与落点

- 使用仓库自有 helper 与有界 watchdog 设置生成真实的非零、timeout 及每一种输出超限 verdict。Receipt 与已知密钥拒绝走真实父进程密封/校验路径；取消与 lease 丢失穿过真实 scheduler handler 与精确 ownership 边界。
- 每一行不得把哨兵放入 pytest 参数 ID、断言消息、JUnit 属性或计划内运维字符串；哨兵只在 collection 后生成，并且只按值扫描。
- 文件系统证据扫描精确返回/保留的安全根，包括隐藏/忽略文件及 SQLite sidecar。普通失败根必须不存在或已删除；故意 quarantine/unresolved/profile case 属于单独枚举的负向集合。
- SQLite 证据同时执行保留数据库文件的精确字节扫描、全部文本/JSON 值的逻辑检查，以及 Job/SyncRun 权限检查。取消竞态可以保留丢失前已提交状态，但之后不得有旧 owner 变更或终态成功。
- 运维证据覆盖序列化 scheduler 结果、CLI/捕获的 stdout/stderr，以及异常/结果 `str`/`repr`；拒绝哨兵、lease owner/token、本地根、quarantine 位置及原始清理异常。

### 可能携带凭据的负向边界

- 保持执行 0007 的四状态清理契约不变。`ABSENT` 与 `REMOVED` 可用于安全树零匹配证据；`QUARANTINED` 只可在已忽略且受限的存储下保留故意字节；`UNRESOLVED` 尝试记录固定脱敏 marker，并且即使 marker 持久化本身失败也必须硬 fence 账户。
- 留存产物 allowlist 必须逐项命名所有排除的负向测试；不得为了扫描通过而删除 quarantine/unresolved 证据，也不得在运维输出中暴露留存路径。

### 恢复、兼容与下一执行

- 不重写执行 0007 的记录；由执行 0008 的 progress 与 verification 说明继任门禁是否关闭两项 partial。
- Legacy manifest v2/receipt v1 继续不可变、逐字节精确，并且只被共享归一化/手工导入接受；定时重启/reclaim 仍只信任 v3。
- 成功密封的 v3 输出在本执行仍是 crash-recovery 产物。由于它可能包含未知签名 query，因此明确属于可能携带凭据边界。执行 0009 必须把终态清理/隔离作为 signed refresh 的一部分实现；执行 0008 不会把零匹配声明静默扩大到该根。

### Schema 与迁移决定

- 不计划新增 Alembic revision。本次收口应新增确定性测试，并且只在必要时最小修复 runner/handler 竞态。若需要持久关系状态，必须停止实现、先修订本冻结计划，再新增真实迁移。

## 实现顺序

1. 先新增 child-exit/pre-seal 红测，再增加使其通过的最小取消检查。
2. 新增重复 post-seal/pre-ingest 取消测试；仅在当前 handler 失败时修复 join/cleanup。
3. 使用生成哨兵构建 11 行、3 落点安全矩阵及 completeness 元测试。
4. 重跑既有 quarantine/unresolved/profile、父死亡、重试/重启、v3/v2 及不可变 v2/v1 套件，防止边界退化。
5. 运行完整质量门禁，并在 `.media-sync/verification/0008-closeout-sentinel-root` 下执行全新的安全留存产物哨兵。
6. 用准确结果更新执行记录与项目索引，再创建一个不推送的双语本地实现提交。

## 必需离线测试

- 精确 child 退出/整树 join → 最终检查 → 取消 → 无 receipt barrier。
- 精确已密封 receipt → 阻塞归一化 → 重复取消 → join 清理 → 零导入 barrier。
- 11 个失败行，每行同时包含文件系统 + SQLite + 运维落点断言，并验证 33-cell 集合相等。
- 固定状态映射、取消/lease 丢失后无写入、旧 owner 不成功收尾。
- 四种清理状态、marker 持久化失败、quarantine 固定输出、profile 隔离及同根 alias 检查。
- 既有七平台离线协议、legacy 读取兼容及打包/迁移测试。

## 留存哨兵规则

- `.media-sync/verification/0008-closeout-sentinel-root` 在唯一权威运行前必须不存在，之后不得删除或重建；0007 哨兵根是只读证据，不复用。
- Allowlist 只包含安全产物测试；每个留存负向函数都要明确列出，不接受宽泛模块入口或脆弱的负向 `-k` 表达式。
- 扫描隐藏/忽略的真实文件、SQLite/WAL/SHM、pytest/JUnit 及运维输出。Windows pytest `current` alias 必须解析到留存根内同父现存目标，并独立扫描真实目标。
- 记录准确 case 数、33 个矩阵 cell、哨兵数、SQLite 数、alias、文件、目录、字节与耗时。

## 回退与安全

- 不修改或内嵌上游源码；不授权真人凭据、browser profile、账户、平台/CDN 端点、媒体服务器或 Git 远端操作。
- Helper 终止只针对仓库创建的精确进程身份；破坏性清理继续限定在已验证 attempt 根，并且绝不跟随链接。
- 既有 0007 哨兵证据绝不删除；新的临时及留存根保持忽略且不跟踪。

## 明确延期

- 签名 locator refresh，以及已实现的成功/恢复 attempt 终态清理/隔离：执行 0009。
- 持久自动 `sync → download → Emby` DAG：执行 0010。
- 七平台真人登录/作者流量/CDN 验收及真实 Emby/Jellyfin 扫描/播放。
- 平台衍生物、逐 HTTP 请求间隔、真人分页有界性、二维码/challenge 展示 UX、REST、常驻监督、Docker、公网部署及 HA/PostgreSQL。
