[English](verification.md) | **中文**

# 验证过程

状态：冻结源码的离线发布门禁通过；真人/Linux/PostgreSQL 资格明确保留如下。

## 最终证据

- 最终完整 Python 覆盖以三个隔离组执行，扣除一次有意的 8 项 helper 重复后合计 `6924 passed, 40 skipped`：unit `4604 passed, 3 skipped`、contract `1085 passed, 2 skipped`、integration `1235 passed, 35 skipped`。unit 原始命令因同时收集 8 项媒体服务器 helper，报告 `4612 passed, 3 skipped in 511.42s`；contract 用时 489.20 秒，integration 用时 422.79 秒。唯一 warning 类型是既有 Starlette/httpx 弃用提示；跳过项均为 Windows/POSIX 差异或真实 PostgreSQL 不可用。
- 较早的精确交付竞态/恢复审查套件通过 `255` 项。最终审查发现 supervisor 陈旧租约缺口后，修正源码又通过全部 17 项订阅交付 API 测试及 14 项租约聚焦选择。这些重叠选择覆盖 scheduler/pipeline 两种入队顺序、supervisor 抢占、`claimed`/`running` 过期回收、同 ID `retry_wait`、Operation 过期延后、耐久 receipt 恢复及不创建第二条链。
- 迁移/数据库/打包资源组合：`52 passed`。覆盖 SQLite 授权/拒绝降级及 PostgreSQL 语句顺序；本机没有配置真实 PostgreSQL URL。
- 修正陈旧清单后的最终专项 `112 passed`，更新了 SystemExit 语义、七个 Cookie 能力平台及 75 条鉴权路由清单。
- Web 最终门：25 个文件 / 781 项通过；Prettier 通过，Svelte 0 错误/0 警告，production build 通过。
- Ruff lint 通过；最终全仓 Ruff format 检查报告 1101 个文件已格式化；strict mypy 149 个源码文件通过；compileall 通过；`uv lock --check` 解析 62 个包；两个锁定 upstream 通过；`git diff --check` 通过。
- 修正后重建的 wheel/sdist 均含工作区全部 165 个应用 Python 文件且逐字节一致。Wheel：172 成员，SHA-256 `eaba763d84ce337027cd04cd6f0a6c7fcfad015b240e139a4c61f8e783e3a4cd`。Sdist：1222 成员，SHA-256 `bc073ab59a56f26ec114cbcedacb041b91f06144119a6e97a9827629d1cc1def`。必需迁移/Mako 资源存在；精确成员审计没有实际 `.env`、数据库、私钥、凭据、运行日志/profile/输出、构建缓存、临时文件、VCS/工具状态或链接成员。`.env.example` 及 8 个版本化 JSONL 爬虫夹具是模板/测试数据，不是运行状态。

## 如实保留的失败

- 独立审查发现四类恢复/重复链风险：supervisor 持有活动 pipeline、pipeline 入队/物化的反向交错、direct `retry_wait` 过早终结 Operation，以及 observer 只轮询已崩溃 supervisor 留下的陈旧 `claimed`/`running` 租约。各问题均先复现、再修正；最后一项回归只有重试同一个精确 Job 并在租约过期后回收才会成功。
- 审查编辑仍落地时启动的全量轮次被主动中止，不作为发布证据。随后 `-x` 在 3219 项通过后发现一个陈旧浏览器诊断断言；下一次完整轮在 6918 项通过后发现 Cookie 能力和 74 路由清单陈旧。最终租约修正后，一次单进程全量仅为缩短墙钟时间在 3% 主动停止。首次隔离 unit 命令因遗漏跨目录 helper 收集而暴露两个收集错误；显式收集该 8 项 helper 后命令通过。上述三个最终成功组覆盖完整 6964 项收集，重复项已单独扣除。
- 第一次包 denylist 把合法的 `web/src/routes/logs/+page.svelte` 误报为可疑，因为规则匹配了任意 `logs` 路径。规则收紧为仅拒绝包根运行时目录后完整审计通过；没有手工删除或忽略成员。

## 未执行

- 当前 Linux/Docker 镜像及真实 PostgreSQL 事务。
- 真人扫码、创作者采集、CDN 获取、生产下载/目录播放、Emby/Jellyfin 刷新及 supervisor 恢复。
- 没有修改生产状态、凭据、订阅或媒体文件。
