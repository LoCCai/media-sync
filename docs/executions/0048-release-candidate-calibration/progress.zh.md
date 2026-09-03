[English](progress.md) | **中文**

# 执行 0048 推进结果

- 状态：校准范围已完成
- 日期：2026-09-03

## 已完成

- 阶段 A：双语 README 状态页重写；`docs/status.md`/`.zh.md` 单一事实来源；架构文档状态修正（REST API、控制台、Docker、监督器）；0043 延期至 0.2；0044 改范围；0047 重写为金丝雀先行的验收总阶段。
- 构建可复现：钉版 `uv==0.12.9`；`BASE_IMAGE` ARG 附 digest 流程；`docker/mediacrawler-requirements.lock`（78 个带哈希钉定，playwright 1.62.0）；构建时写 `/opt/BUILD-MANIFEST.txt`；compose 内 Emby bind-mount 示例。
- 0044 最小集实现：三个端点、共享 `_execute_asset_download`（CLI 主体抽取；CLI 行为逐字节等价——编排套件 38 项通过）、控制台抽屉 + 重下载、API 测试扩展（5 项通过）。
- 工作站环境补齐：安装 ffmpeg/ffprobe（静态构建）并按锁定 SHA 克隆两个 `.upstream` checkout——`check_upstreams.py` 本地通过，钉定源码契约套件可运行。
- **缺陷修复**：JSONL 读取层 tuple 冻结与 0039 v2 `isinstance(list)` 检查冲突，导致所有真实多实况记录被隔离；修复为 `(list, tuple)`；28 项实况 gallery 测试全部通过。根因：这些测试提交时只收集未执行（正是评审指出的缺口）。
- Python 矩阵已执行（每版本同步+完整套件）——数字与如实分歧清单见验证文件。

## 偏差与决策

- 一组调度 handler 进程协议测试（约 11 项）在本工作站干净 checkout 上同样失败（经 stash 验证）——记录为工作站存疑而非产品回归；阶段 B 的 Linux 主机复跑裁定，任何真实缺陷进入 0047 缺陷循环。
- 本网络无法访问 Docker Hub API，基础镜像 digest 无法在此解析；交付机制为 ARG + 文档化 `docker buildx imagetools inspect` 流程，由操作者在构建主机钉定 digest。

## 待完成

- 操作者按重构后的 0047 执行：阶段 B（Linux 基线）→ 阶段 C 金丝雀 → … → 阶段 F RC 标签。
