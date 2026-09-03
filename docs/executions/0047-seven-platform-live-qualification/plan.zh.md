[English](plan.md) | **中文**

# 执行 0047 计划

- 状态：等待操作者执行（总阶段；由 0048 重构）
- 日期：2026-09-03

## 操作者流程

**阶段 B —— Linux 基线（任何真人账户之前）**

1. `git pull && uv sync --all-groups --locked && uv run pytest -q`——记录准确数字；与执行 0048 的工作站记录对照，任何平台特异性分歧都要调查。
2. `cp docker-compose.example.yml docker-compose.yml && docker compose build && docker compose up -d`；验证 `/api/v1/health` + `/api/v1/ready`、控制台可达、重启后 `db init` 幂等。
3. 重启持久性：`docker compose restart`，确认账户/订阅/任务仍在；按 [`operations.zh.md`](../../operations.zh.md) 做一次备份 → 恢复到新卷的演练。
4. 确认运行后无残留 Chromium/Xvfb/ffmpeg 子进程。

**阶段 C —— 金丝雀（先 Bilibili，后小红书）**

每个金丝雀：登录（优先 QR）→ 订阅样例矩阵创作者 → 立即运行 → 调度运行（双门禁）→ pipeline 运行 → 记录逐形状结果、归档字节、Emby 目录。然后两行增量性验证（无变化重跑；经可控测试账号的真实增量）。再是恢复行：下载中杀死 worker 并确认收敛；抓取中重启容器；会话过期后重认证；制造一次 CDN 主地址失败并观察备用选择。把 `/data/library` 只读挂载进真实 Emby/Jellyfin，重扫，验证元数据/海报并抽样播放。

**阶段 D —— 其余平台按媒体类别分批**

抖音/快手/微博（视频/图集/封面/签名 CDN），然后贴吧/知乎（文章/正文/图集/分页），各自对照样例矩阵。

**阶段 E —— 稳定性**

supervisor 跨多个调度周期；无持续增长的 Chrome/Xvfb 进程；无永久 claimed/running 的 Job；SQLite + 归档备份恢复；Emby 重扫 + 抽样播放。

**阶段 F —— 收尾**

用逐平台等级更新平台能力矩阵与 [`docs/status.zh.md`](../../status.zh.md)；翻转完成度归档真人行；两个金丝雀均为 Supported 且全部平台已分级时，打 `v0.1.0-rc1`。

## 缺陷循环

任何真人失败 → 编号修复子执行（`0047-dN`）→ 改代码 → 主机全量自动回归 → 重跑受影响平台 → 重跑受影响同类平台 → 之后才更新本记录。

## 回退

本执行自身不改产品代码；修复子执行携带各自的回退记录。
