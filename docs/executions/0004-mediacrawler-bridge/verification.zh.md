[English](verification.md) | **中文**

# 执行 0004 验证

- 验证日期：2026-08-30
- 环境：Windows, Python 3.11.8, pytest 8.4.2
- 网络与账户策略：仅检查锁定检出、离线夹具与假子进程；不请求平台、不启动浏览器、不使用真人账户。

## 最终质量门禁

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 锁定依赖 | `uv sync --all-groups --locked` | 通过 |
| 代码规范 | `uv run ruff check .` | 通过 |
| 格式 | `uv run ruff format --check .` | 通过 |
| 严格类型 | `uv run mypy src/media_sync` | 通过 |
| 全量离线测试与覆盖率 | `uv run pytest --cov=media_sync --cov-report=term` | 通过 |
| 桥接与恢复专项 | `uv run pytest tests/contract/test_mediacrawler_bridge.py tests/contract/test_mediacrawler_ingestion.py tests/integration/test_checkpoint_fencing.py tests/integration/test_mediacrawler_cli_ingest.py tests/integration/test_mediacrawler_db_ingestion.py tests/integration/test_secret_sinks.py tests/unit/test_security.py -q` | 通过 |
| 密钥落点 | `uv run pytest tests/integration/test_secret_sinks.py tests/unit/test_security.py -q` | 通过 |
| 包 | `uv build` | 通过 |
| 随包迁移 | `uv run pytest tests/integration/test_packaged_migrations.py -q` | 通过 |
| 文档 | `uv run python scripts/check_docs.py` | 通过 |
| 上游锁定 | `uv run python scripts/check_upstreams.py` | 通过 |
| 补丁空白 | `git diff --check` | 通过 |

所有命令退出码均为 `0`；最终门禁在加入“两条记录的末批回滚/重放”及旧爬取 continuation 保护后执行。

## 行为与安全证据

- 契约测试覆盖七个平台命令策略、版本化夹具 schema、JSONL 限制和归一化器；dry-run 始终报告 `spawned=false` 与 `live_qualification=NOT_RUN`。
- 真实 CLI 导入集成路径会在归一化前验证 manifest v2、加密完成回执与不可变字节快照；夹具测试只隔离检出定位。
- 账户/订阅/任务/revision/模式/登录/数量上限及作者指纹全部绑定；签名作者引用只在内存解析并与 manifest 指纹比较；任一不匹配、截断末行或语义隔离记录都不会创建 run，也不会推进 checkpoint。
- 密钥来源是显式的：签名/不透明作者输入以 `SecretValue` 进入桥接，普通 URL 若含含义不明的 query 或 fragment 会被拒绝。父进程在发布回执前同时扫描原始 UTF-8 字节与解码后的 JSON 字符串，寻找已知 Cookie/签名引用及已识别签名组件的精确回显；命中时固定返回 `completion_failed` 且不写回执，因此无法进入 CLI 导入或 SQLite。
- 输出验证拒绝目录替换、文件替换、符号链接/reparse、硬链接、文件描述符调换、未列出文件及大小/哈希漂移；空输出只有在父进程认证回执中显式确认才被接受。
- checkpoint 测试覆盖并发 CAS、同时间戳晚到 ID、独立回填状态、旧到新部分提交、更新运行交错、旧密封爬取恢复及游标保持。
- 两条记录且 `batch_size=1` 时注入最终 `succeeded` 故障：首批保留，末批内容/checkpoint/成功状态全部回滚；随后以当前 revision 重放同一密封爬取，只恢复缺失项。
- 哨兵值不会进入 argv、进程输出、异常、manifest、JSON、事件或 SQLite 字节；测试只解析临时生成的虚拟密钥。

## 线上资格验证

| 平台 | 登录 | 作者扫描 | 媒体获取 | 状态 |
| --- | --- | --- | --- | --- |
| `xhs` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `dy` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `ks` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `bili` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `wb` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `tieba` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |
| `zhihu` | 未运行 | 未运行 | 未运行 | `NOT_RUN` |

自动夹具与假子进程结果只证明本地桥接契约，不能证明平台当前接受登录、作者采集或媒体访问。
