[English](verification.md) | **中文**

# 执行 0051 验证

- 状态：离线实现门全部通过；真人资格仍为 `NOT_RUN`
- 日期：2026-09-04
- 基线：`38e0ebe`
- 数据库迁移：无

## 自动化门

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| Python 完整套件 | `uv run pytest -q` | `PASS` — 2135 passed, 3 skipped |
| 前端格式 | `pnpm format:check` | `PASS` |
| Svelte/TypeScript | `pnpm check` | `PASS` — 0 errors, 0 warnings |
| 前端单元测试 | `pnpm test` | `PASS` — 7 tests |
| 静态生产包 | `pnpm build` | `PASS` — adapter-static 构建完成 |
| Ruff | `uv run ruff check . --no-cache` | `PASS` |
| Ruff 格式 | `uv run ruff format --check .` | `PASS` |
| strict mypy | `uv run mypy --strict --no-incremental src` | `PASS` — 90 个源码文件 |
| 字节码编译 | `uv run python -m compileall -q src` | `PASS` |
| 分发包构建 | `uv build` | `PASS` — sdist 与 wheel |
| 文档 | `uv run python scripts/check_docs.py` | `PASS` — 458 个 Markdown 文件 |
| 锁定上游 | `uv run python scripts/check_upstreams.py` | `PASS` — 2 项 SHA/remote 检查及 2 个干净 checkout |

锁定 checkout 仍为 MediaCrawler `d6f7c5bb906b6dac40ddf343ef9e26438a3de092` 与 bili-sync-up `dcb5bb73b56ac45b2525da14b389e185b0ea6dbd`。实现和收尾过程均未修改这两个 checkout。

## 需求证据

| 需求 | 已验证证据 |
| --- | --- |
| 稳定七平台能力契约 | 端点/序列化契约断言 v1 形状及精确顺序 `xhs`、`dy`、`ks`、`bili`、`wb`、`tieba`、`zhihu` |
| 保守作者权限边界 | 聚焦 application 与 API 测试强制 `[A-Za-z0-9._-]{1,255}`、仅 XHS secret reference，并验证写入前拒绝 |
| 显式全历史确认 | Bilibili、抖音、快手和微博的等价 CLI/API 草稿在缺少 `allow_full_history=true` 时拒绝，且不写入 Author 或 Subscription |
| CLI/REST 共用 workbench | 契约测试验证等价预览/创建规则，并保留 CLI 旧有 JSON 投影 |
| 并发幂等创建 | SQLite 同草稿竞态在 workbench 范围的 immediate writer reservation 下收敛为唯一 Account 或 Subscription |
| 登录专用预检 | 数据库/账户/许可证/checkout/运行时/浏览器/profile/锁的强制失败不分配新的进程内 Operation 或 LoginSession；ffmpeg/ffprobe 不参与 |
| 精确 session 二维码权限 | 测试覆盖活动所有权、非 QR 拒绝、放弃态协调、旧材料清理、2 MiB 普通文件边界、inode/大小校验、读取后持久化复验和终态不泄露 |
| 能力驱动 Web 工作台 | Svelte 状态/单元覆盖验证账户组合状态、预检/session QR 轮询及订阅三阶段预览/确认流程 |
| 安全响应投影 | preview/result/detail 响应不含 secret、凭据、签名 URL、路径和 cursor 哨兵；422 校验不回显恶意输入 |

## 残余风险

成功的预检是一份时间点快照。从该结果到进程内 Operation、再到后台 application service 的交接并非跨 API 进程的原子事务。因此两个 API 进程可能都先通过预检，再由持久化登录边界选出胜者。持久化 `LoginSession` compare-and-set 与账户 OS 锁仍是权威边界，落败者会按失败关闭。

这是归入 Execution 0052 持久化 Operations 与跨进程幂等工作的非阻塞协调/UX 残余。它不是二维码文件读取/读取后复验间隙，也不会授予凭据或二维码权限。

## 证据口径

本轮未使用真人浏览器登录、作者端点、平台 API/CDN、下载的作者媒体或 Emby/Jellyfin 服务。本地 fixture、模拟运行时与浏览器/单元测试仅属于离线证据。真人账户、抓取、下载、扫描或播放行均未从 `NOT_RUN` 改变；这些声明仍由 Execution 0047 操作者证据把关。
