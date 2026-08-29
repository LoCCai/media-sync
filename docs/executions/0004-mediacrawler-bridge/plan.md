# Execution 0004 plan / 执行 0004 计划

1. Freeze the license acknowledgement, checkout discovery, run-directory and secret-channel contracts. / 冻结许可证确认、检出发现、运行目录与密钥通道契约。
2. Add typed secret references/providers and recursive sink redaction/rejection with sentinel tests. / 添加类型化密钥引用/提供器及递归落点脱敏/拒绝，并用哨兵测试验证。
3. Implement checkout validation and a redaction-safe seven-platform bridge command builder. / 实现检出验证和安全脱敏的七平台桥接命令构造器。
4. Implement the isolated child runner, account-level browser profile, timeout/output watchdog and Zhihu creator shim without editing upstream. / 实现隔离子进程、账户级浏览器 profile、超时/输出看门狗和知乎作者兼容，不修改上游。
5. Define a versioned raw envelope and JSONL reader with truncated-tail tolerance and quarantine. / 定义版本化原始信封及支持末行截断/隔离的 JSONL 读取器。
6. Build and fixture-test normalizers for all seven platform schemas and ordered asset discovery. / 为七个平台构建归一化器及有序资产发现，并用夹具验证。
7. Separate forward watermark/known-ID state from backfill continuation; add optimistic checkpoint fencing. / 分离前向水位/已知 ID 与回填 continuation，并添加乐观检查点 fencing。
8. Refactor live ingestion into short batch transactions with no browser/network await under the SQLite writer lock. / 把真实导入重构为短批次事务，浏览器/网络等待期间不持有 SQLite 写锁。
9. Add CLI doctor/dry-run/account adapter/sync-ingest commands with fixed, secret-free output. / 添加桥接诊断、dry-run、账户适配器及同步导入 CLI，并确保固定脱敏输出。
10. Run all offline gates, record exact results and create bilingual local commits. / 运行全部离线门禁、记录准确结果并创建中英双语本地提交。

## Rollback and safety / 回退与安全

Automated tests use only temporary directories, fixture JSONL and a fake child process. They do not invoke the upstream crawler, start Playwright, contact platform endpoints, or resolve a real secret. Live execution requires an explicit license acknowledgement plus a separately authorized account workflow.

自动测试只使用临时目录、JSONL 夹具和假子进程，不调用上游爬虫、不启动 Playwright、不访问平台端点，也不解析真实密钥。真实执行必须先显式确认许可证，并另行获得账户授权。
