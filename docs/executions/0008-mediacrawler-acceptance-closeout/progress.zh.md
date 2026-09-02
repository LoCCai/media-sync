[English](progress.md) | **中文**

# 执行 0008 推进结果

- 状态：离线验收范围已完成
- 开始时间：2026-08-30 15:48 +08:00
- 完成时间：2026-08-30
- 计划提交：`f0c6015`
- 实现提交：本次提交
- 前置执行：Execution 0007 implementation commit `d071618`
- 网络边界：仅离线夹具与仓库自有本地辅助进程

## 推进结论

执行 0008 以离线继任验收结果关闭执行 0007 的 AC6 与 AC13。它补齐两个剩余取消窗口的确定性证据、封闭的“11 种失败 × 3 类落点”矩阵、fail-closed 的留存文件系统/SQLite 扫描器，以及权威留存产物门禁。唯一生产代码变更是在发布完成回执前立即执行最终取消检查。

执行 0007 的四份历史记录继续保持当时的 `PARTIAL` 结论；本记录只报告继任收口，不改写先前证据。

## 已交付实现

| 交付项 | 结果 |
| --- | --- |
| Child 退出后、密封前取消 | 真实仓库自有 child 返回 `0` 且完整进程树 join；在发布回执前观察取消，不进入回执 writer，安全收口 attempt，并可重新获取账户/profile 锁 |
| Handler 密封前边界 | runner 得到取消结论后，归一化与导入 spy 均保持零进入 |
| 密封后、导入前取消 | 单次与重复取消都会在 unwind 前 join 受保护 normalizer；不提交 Content/Asset、checkpoint 推进或成功 SyncRun |
| 封闭安全矩阵 | 精确 11 行失败枚举 × `filesystem`、`sqlite`、`operator` = 33 个显式断言 cell |
| 调度权限 | 每行按固定终态或 fencing 状态检查 Job、SyncRun、checkpoint、Content、Asset、平台/账户 lane 及 Job/worker/lane CLI 投影 |
| 扫描器契约 | 留存文件系统遍历、路径名、SQLite 数据库文件及 sidecar 均以 fail-closed 方式检查 |
| 兼容性 | Manifest v2/receipt v1 继续逐字节精确、不可变且只用于手工导入/共享归一化；定时恢复仍只信任 v3 |

## 测试先行与加固过程

1. 先新增 child-exit/pre-seal 回归；它因取消后仍进入 `write_completion_receipt()` 而失败。随后增加 7 行生产修复执行最终取消检查，回归通过。
2. Handler 的 seal 后单次/重复取消 case 首次运行即通过，既有“先 join 再 unwind”实现无需生产改动。
3. 初版矩阵即使未实际注入本行哨兵也可能通过；新增 runner/handler 清理观察器后，11 行均证明生成哨兵在清理前确实存在。
4. `0.5s` timeout 会在 helper 写入哨兵前触发；改为有界 `4.0s` 后，既保留真实 timeout，又使注入证据确定。
5. 运行中轮询与最终留存扫描分离：轮询允许 SQLite 暂时被锁，最终扫描则 fail-closed。
6. 审计发现默认 `os.walk` 可能吞掉遍历错误且未扫描路径名，`Path.is_file()` 也可能隐藏 SQLite sidecar 检查错误；扫描器现会拒绝这些情况，并有两个独立契约覆盖修复。

普通矩阵检查固定脱敏清理结果。原始 cleanup error 不进入落点的强证据来自单独选择的 quarantine/unresolved 负向测试；不会把普通矩阵中的 `.quarantine` 与 `Traceback` 检查夸大成独立证明。

## 验证结果

| 门禁 | 结果 |
| --- | --- |
| 精确取消与矩阵核心 | `16 passed in 29.08s` |
| 含扫描器契约的矩阵模块 | `14 passed in 24.29s` |
| 相关契约与集成模块 | `151 passed, 1 skipped` |
| 可能携带凭据负向边界门禁 | `13 passed, 1 skipped in 7.31s` |
| 完整分支感知套件 | 分支感知覆盖率 |
| 权威留存产物门禁 | 33 个矩阵 cell 与 12 项精确密钥扫描 |
| 依赖、规范、格式、类型、构建与仓库检查 | `PASS`；准确结果记录于 `verification.md` |

完整套件唯一 skip 是 Windows 不适用的 POSIX mode-bit 边界。

## 当前验收状态

| 范围 | 状态 | 真实性说明 |
| --- | --- | --- |
| 执行 0007 AC6 继任收口 | `PASS` | 两个剩余确定性取消窗口均已离线执行 |
| 执行 0007 AC13 继任收口 | `PASS` | 精确“11 种失败 × 3 类落点”矩阵与 fail-closed 扫描器通过 |
| 签名 locator refresh | 未实现 | 执行 0009 范围 |
| 自动 `sync → download → Emby` DAG | 未实现 | refresh 后的执行 0010 范围 |
| 真人登录、作者流量与定时运行 | `NOT_RUN` | 未提供授权账户或交互挑战 |
| 真人 CDN 与真实 Emby/Jellyfin | `NOT_RUN` | 未提供可刷新授权环境或媒体服务器 |

## 如实延期

- 成功密封的 v3 输出仍可能含父进程无法预先登记的未知签名 query；在执行 0009 把签名 locator refresh 与成功/恢复终态清理或隔离一并实现前，它继续作为明确的可能携带凭据临时边界。
- 持久自动 `sync → download → Emby` 规划仍属于执行 0010；执行 0008 不创建 blocked 下游 Job。
- 七个平台的真人二维码/Cookie/保存会话登录、作者流量、平台分页/速率行为、CDN 获取及 Emby/Jellyfin 扫描/播放均保持 `NOT_RUN`；手机号登录仍不支持。
- `wb`、`tieba`、`zhihu` 可下载资产、平台特有衍生物、REST、二维码/challenge 展示、常驻监督、Docker、公网部署及 HA/PostgreSQL 仍未实现或延期。
