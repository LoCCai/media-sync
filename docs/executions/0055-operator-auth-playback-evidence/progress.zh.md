[English](progress.md) | **中文**

# 执行 0055 阶段 A 进展

- 状态：规划基线已准备；尚未开始实现
- 日期：2026-09-05
- 基线：`d0a8cc2`
- 计划 revision：`0008_playback_evidence`

## 规划检查点已完成

1. 已 fetch `origin/main`；本地与远端 `main` 均为 `d0a8cc2`，没有待合并提交。
2. 已阅读 0053/0054 交接、roadmap、status、architecture、deployment、operations、security review 与 qualification 源码。原始产品目标不变：七平台登录/订阅/抓取及 Emby/Jellyfin 兼容输出。
3. 已盘点当前 FastAPI 表面：51 条路由全部匿名，包括业务读写、QR/归档字节、SSE、支持/深度就绪、docs/OpenAPI、`/legacy` 与 SPA fallback。
4. 已确认浏览器兼容约束：EventSource 与直接 QR/archive/media/navigation 请求无法安全携带 Authorization header，且 token 绝不能进入 URL。因此冻结浏览器方案为 HttpOnly 同源 session + CSRF；可选自动化另用独立 Bearer header。
5. 复用既有类型化 secret reference/脱敏、publication 权威、selector/item fingerprint、SQLite writer reservation 与 PostgreSQL unique-lock 行为，不建立平行权威。
6. 已冻结单表 append-only playback evidence 以及服务端 resolve → lookup → resolve 确认流；accepted refresh、item observation、provider completion 与真人播放继续是四个不同事实。
7. 已明确排除可写设置、多 profile、保留/删除/修复、自动扫描联动、多用户鉴权及真人资格。

## 尚未实现

- 尚无 auth setting、middleware、login/session/logout endpoint、cookie、CSRF、Bearer、rate limiter 或 Web 登录壳。
- Revision 0008、evidence repository/service/API、observation fingerprint、qualification schema v3 与 Web 确认 UI 均尚不存在。
- 尚未运行任何 0055-A 实现测试或真人 credential/server 流程。规划基线上的 playback 仍为 `NOT_IMPLEMENTED`，真人状态仍为 `NOT_RUN`。

## 下一检查点

先提交中英双语规划基线，再实现鉴权配置/runtime 与 deny-by-default 路由边界；控制面完成鉴权后才开始 evidence persistence。

既有 `.mimosa/` 目录保持未跟踪并排除。
