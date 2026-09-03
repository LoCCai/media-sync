[English](goal.md) | **中文**

# 执行 0048 目标

- 状态：发布候选校准范围已完成（文档、加固、0044 最小实现、离线数字刷新）
- 日期：2026-09-03
- 前置：执行 0047 启动记录（0042–0047 系列）
- 范围：按外部评审把项目从功能扩张模式切换到发布候选验证模式：校准仓库事实、加固构建可复现性、交付改范围后的 0044 运维切片、把 0047 重构为金丝雀先行的验收总阶段，并在当前 HEAD 重建新鲜的离线验证数字

## 目标结果

1. **仓库事实**：双语 README 重写为精简状态页（版本/状态/最新验证/真人状态/阻塞项）并指向新的单一事实来源 `docs/status.md`（+`.zh.md`）；架构文档中 REST API/控制台/Docker/监督器的声明与事实对齐；0042–0047 的执行索引行已由前一系列交付。
2. **范围校准**：0043（弹幕/字幕）显式延期至 0.2；0044 改范围为最小运维恢复切片并实现；0047 重写为操作者验收总阶段（支持等级、金丝雀顺序（Bilibili + 小红书）、逐平台样例矩阵、幂等与真实增量拆分、Emby 强制项、允许的缺陷修复循环）。
3. **0044 最小集交付**：`GET /api/v1/subscriptions/{id}`（调度 + 近期运行 + 近期任务）、`GET /api/v1/scheduler/jobs/{id}`、`POST /api/v1/assets/{id}/download`（受控后台操作）；CLI `asset download` 主体抽取为共享 `_execute_asset_download`，CLI 与 API 驱动同一门禁；控制台新增订阅详情抽屉与逐资产重下载；离线 API 测试扩展并通过。
4. **构建可复现**：钉版 uv（`uv==0.12.9`）；`BASE_IMAGE` ARG 附 digest 钉定流程；从锁定上游 requirements 为 linux/Python 3.13 编译带哈希的 `docker/mediacrawler-requirements.lock`（78 包，playwright 钉 1.62.0 进而钉 Chromium revision）；镜像构建写入 `/opt/BUILD-MANIFEST.txt`（Python/uv/ffmpeg/playwright/Chromium 版本 + 双 venv pip freeze）；compose 文档化 Emby bind-mount 模式。
5. **Python 支持以执行澄清而非注释**：3.11/3.12/3.13 同步+测试矩阵已在编写工作站运行；按结果 `requires-python` 维持 `>=3.11,<3.14`。
6. **新数字发现并修复真实缺陷**：JSONL 读取层会把内层 list 冻结为 tuple，0039 多实况 v2 分支（`isinstance(..., list)`）因此隔离了所有真实记录——已修复为接受 `(list, tuple)`；受影响测试（此前只收集未执行）现已通过。

## 验收边界

- 任何编写机都不执行部署或真人平台验证（操作者指示）：Docker 构建/运行与全部真人行保持为阶段 B+/0047 的操作者项（Linux）。
- 少量调度 handler 进程协议测试在本工作站干净 checkout 上同样失败；记录为工作站存疑，以 Linux 主机套件复跑为权威裁定（阶段 B 第 1 步）。
- 无 schema migration；除 0044 走服务的端点外不新增权限。

## 明确延期

弹幕/字幕（0043 → 0.2）、运维 UI 强化（0.2）、Debian apt 快照钉定、完整 SBOM 工具链、CI 依赖扫描、外部安全审计。
