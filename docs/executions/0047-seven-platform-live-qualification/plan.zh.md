[English](plan.md) | **中文**

# 执行 0047 计划

- 状态：等待前置条件与操作者执行（总阶段；由 0048 重构）
- 日期：2026-09-03

## 操作者流程

**阶段 B —— Linux 基线（任何真人账户之前）**

1. `git pull && uv sync --all-groups --locked && uv run pytest -q`——记录准确数字并调查全部平台特异性分歧。当前 0055 Windows 仅浏览器确认检查点通过 `2941 passed, 22 skipped, 1 warning in 594.72s`；其中 19 项是真实 PostgreSQL 竞态因未配置 URL 而跳过（11 项 Operation 加 8 项 PlaybackEvidence）。该结果不能替代启用 PostgreSQL 的完整 Linux 主机门。
2. 任何 Compose 启动之前，先在仓库外创建专用 UTF-8 操作者凭据文件，将权限限制为 `0600`，并设置 `export MEDIA_SYNC_OPERATOR_CREDENTIAL_FILE=/absolute/private/path/operator-credential.txt`。凭据须为 16–1024 个 UTF-8 字节，不含控制字符，且不得复用平台 Cookie 或媒体服务器 key。每次重启时都要保持该绝对路径可用；示例 Compose 会把它挂载为 `/run/secrets/operator_credential`，并且只向应用传递 `file:operator_credential`。
3. `cp docker-compose.example.yml docker-compose.yml && docker compose build && docker compose up -d`；确认必需的类型化凭据在绑定端口前成功解析，配置的浏览器 origin 精确等于 `http://127.0.0.1:8632`。使用不会把凭据写入日志或 shell 历史的受审查 HTTP 客户端，证明匿名访问仅限 `GET`/`HEAD /api/v1/health`、`GET`/`HEAD /api/v1/ready`、`POST /api/v1/operator-auth/login`、`GET /api/v1/operator-auth/session` 及公开根资源；证明匿名业务路由与 `/api/docs` 被拒绝；随后证明登录 → Cookie session → 受 CSRF 保护的不安全请求 → 退出完整链路。若验证可选 Bearer 自动化，须配置与浏览器凭据不同且单独解析的凭据。记录精确状态码，但不得记录凭据、Cookie 或 CSRF 值。
4. 重启持久性：`docker compose restart`，确认账户/订阅/任务仍在，并确认进程内操作者 session 已失效；按 [`operations.zh.md`](../../operations.zh.md) 做一次备份 → 恢复到新卷的演练。
5. 进程口径：每个需要显示环境的运行中容器恰好一个受管 Xvfb（启用 supervisor profile 时两个容器各一个是正常情况）；空闲时零 Chromium、零 ffmpeg/ffprobe；不存在任务结束后遗留的孤儿进程；容器停止后相关进程全部消失。

**资格暂停点：**上述后端鉴权边界、revision `0008_playback_evidence`、append-only 持久化及防 TOCTOU 的仅浏览器确认 service/API 已实现并通过离线验证。Console v2 与 `/legacy` 仍未集成操作者 login/session/CSRF 及确认 UI，安全且有界的按作者 current/stale 投影与 qualification schema v3 也尚未实现。因此当前 schema-v2 qualification API 仍把整体 `playback_evidence` 报为 `NOT_IMPLEMENTED` 且真人状态为空。当前检查点不得启动 Web 登录、真人平台、真实媒体服务器播放或阶段 C–F 资格步骤；全部真人资格行继续保持 `NOT_RUN`。只有投影/v3 与 Web 两个检查点都完成验证收尾后，才能恢复下述流程；后端实现或本地/mock 证据本身不能授予任何真人 PASS。

**阶段 C —— 金丝雀（先 Bilibili，后小红书）**

暂停点解除后，每个金丝雀先通过已完成的 Web 登录壳完成操作者鉴权，再登录平台（优先 QR）→ 订阅样例矩阵创作者 → 立即运行 → 调度运行（双门禁）→ pipeline 运行 → 记录逐形状结果、归档字节与 Emby 目录。然后执行两行增量性验证（无变化重跑；经可控测试账号的真实增量）。再执行恢复行：下载中杀死 worker 并确认收敛；抓取中重启容器；会话过期后重认证；制造一次 CDN 主地址失败并观察备用选择。把 `/data/library` 只读挂载进真实 Emby/Jellyfin，重扫，验证元数据/海报，通过已实现的鉴权证据路径记录抽样播放，之后才可把相应真人行从 `NOT_RUN` 翻转。

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
