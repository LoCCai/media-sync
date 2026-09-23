# 研判结论

**GitHub 最新 = `3c31dce`，与本地一致，0077 之后无新执行。** 关键事实：

1. **离线侧全绿且已冻结**：Python 7140 通过/42 跳过、Web 825 测试、静态门全过。持久投递覆盖只有 B 站（0074）与小红书（0076）。
2. **项目自治理定的唯一授权链**（0077 收尾 + README 头部明文）：部署 handoff（重建带 SHA 溯源的镜像 → 验证 OCI 标签 → 迁移 0015 → API/supervisor 一致性）→ 一次有界 XHS 金丝雀 → 记录结果 → 之后才允许抖音 source-first 设计。**「XHS 金丝雀结果记录前，不得开始任何 XHS/抖音工作」**。
3. **线上镜像已被证明早于 0077**（2026-09-09 观察记录：Diagnostics 缺 source-revision/migration/continuation 三行）→ XHS 金丝雀被阻塞在「镜像身份不明」。
4. 你本轮的三个痛点是**操作者体验缺口**，不是产品缺陷：二维码只在上游 `/crawler/` 页、180 秒时效、无自动轮询（media-sync 前端零引用该端点）；crawler 运行日志只在上游页内存队列（512 条，不落盘、不进 media-sync 日志中心）；产物位置只在文档里。
5. 文档债：`docs/status.md` 的里程碑/验证矩阵/阻塞项表**冻结在 0075 边界**（叙事已到 0077）；执行索引表**缺 0059–0068 行**。

# 推进计划

## Track A — 部署 handoff 中文操作单（本会话交付）

新增 `docs/handoff-checklist.md` + `.zh.md`（双档），从 0077 handoff 文档浓缩为逐步可勾选清单：
- **A1 重建与身份**：备份 /data 与凭据 → `git pull --ff-only` → `export MEDIA_SYNC_SOURCE_REVISION=$(git rev-parse HEAD)` → `sh scripts/fetch_mediacrawler.sh` + `uv run python scripts/check_upstreams.py` → 双服务重建 → `docker image inspect` 的 `org.opencontainers.image.revision` 必须等于该 SHA → `media-sync doctor --deep --accept-mediacrawler-license --json` 在 API 与 supervisor 两种服务定义下各跑一次比对。
- **A2 配置**：许可证变量需 **force-recreate**（plain restart 不换环境）；`MEDIA_SYNC_XHS_SCAN_CONTINUATION_DELAY_SECONDS` 两个服务同值。
- **A3 金丝雀流程**：supervisor 保持停止 → `/crawler/` XHS 扫码/Cookie → 账户页认领 → 建暂停的低量订阅 → 恢复并跑一个精确手动单元 → 检查每步耐久证据 → 重启 API 证明续跑 → 恢复 supervisor 观察一次调度续跑。
- **A4 排查速查表**：二维码 404 三种成因（未生成/已过期/平台选择器失败）与抖音 Cookie 粘贴指引；crawler 日志去哪看；三层产物路径表。

## Track B — 执行 0078「操作者控制台体验」（现在启动，已授权）

**边界**：不触碰 XHS/抖音投递逻辑（遵守冻结）；不新增权限面；QR 轮询只读。

- **B1 执行记录**：`docs/executions/0078-operator-console-experience/` goal/plan 双语启动记录，收尾补 progress/verification。
- **B2 内嵌实时二维码面板**：`web/src/routes/accounts/` 新组件轮询已鉴权的 `/crawler/api/crawler/qrcode`（2 秒间隔，200 显示图片，404 区分「等待生成 / 已过期（180s） / 平台选择器失败」并给平台特定指引——抖音提示改走 Cookie 粘贴）。vitest 组件测试（mock fetch 状态序列）。
- **B3 crawler 日志接入日志中心**：`src/media_sync/integrations/mediacrawler/webui.py` 的 `push_log` 链路加有界桥接，把已脱敏的 crawler 行写入既有 observability 日志中心（JSONL 分段，source 标记 crawler-webui，512 条界保持）；`/logs` 页新增来源过滤值。单元测试用夹具行验证桥接与脱敏。
- **B4 产物路径展示**：library 或 settings 页加信息卡（webui-output 原始层 / archive SHA-256 正本层 / library Emby 层），数据取自既有 `GET /api/v1/settings`。前端改动 + 测试。
- **B5 文档债清理**：`docs/status.md`(+zh) 里程碑表/验证矩阵/阻塞块从 0075 冻结刷新到 0077 边界；`docs/README.md`(+zh) 索引补 0059–0068 行（内容取自 status 叙事）。
- **B6 门禁与记录**：ruff/format/mypy strict/compileall/check_docs + vitest + 焦点 pytest；本工作站（ffmpeg+upstream 就绪）跑完整套件拿新数字；按「启动/实现/收尾」三段式提交推送。

## Track C — 金丝雀后解锁（本会话不做，仅记录顺序）

XHS 金丝雀结果记录 → 0079 抖音 source-first 设计（仅设计文档）→ 知乎头像 CDN 形状扩展 → 播放确认 UI（P1）→ 0.2 弹幕/字幕。

# 交付物清单

1. `docs/handoff-checklist.md` + `.zh.md`
2. `docs/executions/0078-operator-console-experience/` 四件套双语
3. QR 面板组件 + vitest 测试
4. webui→日志中心桥接 + 单元测试 + `/logs` 过滤
5. 路径信息卡 + 测试
6. status 矩阵刷新至 0077 + 索引补行
7. 全部静态门绿 + 完整套件新数字 + 提交推送（约 4–6 个提交）