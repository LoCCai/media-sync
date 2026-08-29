# Execution 0004 verification / 执行 0004 验证

- Verification date / 验证日期：2026-08-30
- Environment / 环境：Windows, Python 3.11.8, pytest 8.4.2
- Network/account policy / 网络与账户策略：locked-checkout inspection, offline fixtures and fake subprocesses only; no platform request, browser or real account / 仅检查锁定检出、离线夹具与假子进程；不请求平台、不启动浏览器、不使用真人账户。

## Final quality gate / 最终质量门禁

| Check / 检查 | Command / 命令 | Result / 结果 |
| --- | --- | --- |
| Locked dependencies / 锁定依赖 | `uv sync --all-groups --locked` | PASS — 58 resolved, 43 audited / 通过 |
| Lint / 代码规范 | `uv run ruff check .` | PASS — all checks passed / 通过 |
| Format / 格式 | `uv run ruff format --check .` | PASS — 95 files / 通过 |
| Strict types / 严格类型 | `uv run mypy src/media_sync` | PASS — 40 source files / 通过 |
| Full offline suite + coverage / 全量离线测试与覆盖率 | `uv run pytest --cov=media_sync --cov-report=term` | PASS — 249 tests in 65.16s, 80% total / 通过 |
| Focused bridge/recovery gate / 桥接与恢复专项 | `uv run pytest tests/contract/test_mediacrawler_bridge.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_checkpoint_fencing.py tests/integration/test_mediacrawler_cli_ingest.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_secret_sinks.py tests/unit/test_security.py -q` | PASS — 142 tests in 50.55s / 通过 |
| Secret sinks / 密钥落点 | `uv run pytest tests/integration/test_secret_sinks.py tests/unit/test_security.py -q` | PASS — 33 tests in 0.62s / 通过 |
| Package / 包 | `uv build` | PASS — sdist and wheel built / 通过 |
| Packaged migrations / 随包迁移 | `uv run pytest tests/integration/test_packaged_migrations.py -q` | PASS — 2 tests in 3.61s; source and unpacked wheel reach `0002_checkpoint` / 通过 |
| Documentation / 文档 | `uv run python scripts/check_docs.py` | PASS — 32 Markdown files / 通过 |
| Upstream locks / 上游锁定 | `uv run python scripts/check_upstreams.py` | PASS — 2 exact checkouts / 通过 |
| Patch whitespace / 补丁空白 | `git diff --check` | PASS / 通过 |

All commands exited `0`. The final checks were run after the two-record final-batch rollback/replay regression and old-crawl continuation protection were added. / 所有命令退出码均为 `0`；最终门禁在加入“两条记录的末批回滚/重放”及旧爬取 continuation 保护后执行。

## Behavioral and security evidence / 行为与安全证据

- Contract tests cover all seven command policies, versioned fixture schemas, JSONL limits and normalizers. Dry-run always reports `spawned=false` and `live_qualification=NOT_RUN`.
- The real CLI-ingest integration path validates manifest v2, a cryptographic completion receipt and immutable byte snapshots before normalization; only checkout lookup is isolated for the fixture test.
- Author/account/subscription/job/revision/mode/login/item-cap fingerprints are bound. Signed creator references are resolved only in memory and compared to the manifest fingerprint. A mismatch, truncated tail or quarantined semantic record creates no run and advances no checkpoint.
- Secret provenance is explicit: signed/opaque creator inputs arrive as `SecretValue`; a plain URL with ambiguous query or fragment material is rejected. Before receipt publication the parent searches raw UTF-8 bytes and decoded JSON strings for exact known Cookie/signed-reference disclosure, including recognized signature components. A match returns fixed `completion_failed`, writes no receipt, and therefore cannot enter CLI ingestion or SQLite.
- Output validation rejects directory substitution, file replacement, symlink/reparse points, hardlinks, descriptor swaps, unlisted files and size/hash drift. Empty output is accepted only through an explicit parent-authenticated receipt.
- Checkpoint tests cover concurrent CAS, same-timestamp late IDs, independent backfill state, old-to-new partial commits, interleaved newer runs, old sealed-crawl recovery and cursor preservation.
- An injected final `succeeded` failure with two records and `batch_size=1` leaves the first committed batch intact, rolls back all final content/checkpoint/success mutations, then replays the same sealed crawl from the current revision to restore only the missing item.
- Sentinel values are absent from argv, process output, exceptions, manifests, JSON, events and SQLite bytes. Tests resolve only generated dummy secrets.

- 契约测试覆盖七个平台命令策略、版本化夹具 schema、JSONL 限制和归一化器；dry-run 始终报告 `spawned=false` 与 `live_qualification=NOT_RUN`。
- 真实 CLI 导入集成路径会在归一化前验证 manifest v2、加密完成回执与不可变字节快照；夹具测试只隔离检出定位。
- 账户/订阅/任务/revision/模式/登录/数量上限及作者指纹全部绑定；签名作者引用只在内存解析并与 manifest 指纹比较；任一不匹配、截断末行或语义隔离记录都不会创建 run，也不会推进 checkpoint。
- 密钥来源是显式的：签名/不透明作者输入以 `SecretValue` 进入桥接，普通 URL 若含含义不明的 query 或 fragment 会被拒绝。父进程在发布回执前同时扫描原始 UTF-8 字节与解码后的 JSON 字符串，寻找已知 Cookie/签名引用及已识别签名组件的精确回显；命中时固定返回 `completion_failed` 且不写回执，因此无法进入 CLI 导入或 SQLite。
- 输出验证拒绝目录替换、文件替换、符号链接/reparse、硬链接、文件描述符调换、未列出文件及大小/哈希漂移；空输出只有在父进程认证回执中显式确认才被接受。
- checkpoint 测试覆盖并发 CAS、同时间戳晚到 ID、独立回填状态、旧到新部分提交、更新运行交错、旧密封爬取恢复及游标保持。
- 两条记录且 `batch_size=1` 时注入最终 `succeeded` 故障：首批保留，末批内容/checkpoint/成功状态全部回滚；随后以当前 revision 重放同一密封爬取，只恢复缺失项。
- 哨兵值不会进入 argv、进程输出、异常、manifest、JSON、事件或 SQLite 字节；测试只解析临时生成的虚拟密钥。

## Live qualification / 线上资格验证

| Platform / 平台 | Login / 登录 | Creator scan / 作者扫描 | Media retrieval / 媒体获取 | Status / 状态 |
| --- | --- | --- | --- | --- |
| `xhs` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `dy` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `ks` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `bili` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `wb` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `tieba` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |
| `zhihu` | Not run / 未运行 | Not run / 未运行 | Not run / 未运行 | `NOT_RUN` |

Automated fixture and fake-child results prove only the local bridge contract. They do not prove that a platform currently accepts login, creator collection or media access. / 自动夹具与假子进程结果只证明本地桥接契约，不能证明平台当前接受登录、作者采集或媒体访问。
