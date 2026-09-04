[English](goal.md) | **中文**

# 执行 0050 目标

- 状态：Web Console v2 基础已实现并完成离线验证；操作者 Docker/真人门仍开启
- 日期：2026-09-04
- 前驱：`6d68768`（MediaCrawler 深度就绪诊断与控制台门禁）
- 范围：可跨平台的 MediaCrawler 许可证资格检查，加首个完整 Console v2 迁移切片
- 数据库迁移：无
- 实现与收尾提交：包含本记录的提交（不嵌入自身 SHA）

## 结果

1. 用规范化 LF 的内容身份替代依赖平台的原始 LICENSE 摘要。LF 与 CRLF checkout 得到相同资格结果，裸 CR 关闭失败；锁定 SHA、Git tracked blob 与干净工作树仍全部强制。
2. 交付 SvelteKit 5 + TypeScript + Tailwind 静态 SPA，以紧凑的 bili-sync 风格壳层提供仪表盘、账户、订阅、任务、内容、资产/归档、媒体库、诊断与设置分页面板。
3. 把每次操作时的重复勾选改成每个浏览器一次、不可跳过的首次确认，并存入 `localStorage`。之后登录与 Worker 请求自动携带两个门禁字段；后端仍在每次操作中强制许可证与 checkout 边界。
4. FastAPI 在 `/` 同源提供 SPA，旧控制台保留于 `/legacy`，历史路由可回退；指纹资源长期缓存，并应用 CSP、防 iframe、`nosniff`、Referrer 与 API no-store 响应头。
5. 为新只读页面新增有界、脱敏的内容与按作者媒体库投影，不暴露签名 locator、Cookie 或宿主归档路径。
6. Docker 在隔离 Node/pnpm 阶段构建前端，只把静态产物复制进 Python 包；构建清单记录 Node/pnpm/锁身份，最终镜像不含 Node。

## 验收边界

- SPA 复用已有 application service 与 `/api/v1`，不直接访问 SQLite，也不增加第二个业务运行时。
- 现有内存 Operation 历史明确标为进程内。持久化、SSE 与结构化日志不属于本基础交付声明。
- 浏览器 QA 只用本地夹具数据；真人平台登录、采集、CDN 字节、Emby 扫描或播放行均不从 `NOT_RUN` 翻转。
- 不宣称在本 Windows 工作站构建 0050 镜像；操作者 Linux 重建与容器内 doctor/Chromium 检查仍是阶段 B 门。

## 明确延期

持久操作/事件/日志（0052）、更丰富的内容/资产恢复（0053）、媒体服务器扫描资格（0054）、操作者鉴权与备份/升级 UI（0055），以及最终 0.2 迁移并移除 `/legacy`（0056）仍归独立执行。
