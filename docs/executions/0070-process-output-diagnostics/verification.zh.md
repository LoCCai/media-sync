[English](verification.md) | **中文**

# 验证过程

状态：最终冻结源码的离线发布门禁通过。

## 已通过证据

- 最终完整 Python 覆盖以三个隔离组执行，扣除一次有意的 8 项 helper 重复后合计 `6924 passed, 40 skipped`：unit `4604 passed, 3 skipped`、contract `1085 passed, 2 skipped`、integration `1235 passed, 35 skipped`。unit 原始命令报告 `4612 passed, 3 skipped in 511.42s`；contract 用时 489.20 秒，integration 用时 422.79 秒。唯一 warning 类型是既有 Starlette/httpx 弃用提示。
- 最终进程输出/登录专项：`255 passed, 1 skipped`。output-capture 单独 51 项通过，两条锁定版 MediaCrawler 格式跨进程用例也独立通过；skip 是 Windows 不适用的 POSIX venv launcher。
- 较早的精确交付竞态/恢复专项通过 255 项；最终修正 supervisor 陈旧租约后，全部 17 项交付 API 测试及 14 项租约选择也通过。迁移/数据库/打包资源专项 52 项通过。这些选择与完整覆盖重叠，不累加总数。
- Web 最终门：25 个文件 / 781 项；Prettier 通过，Svelte 0 错误/0 警告，production build 通过。
- Ruff lint 通过；最终全仓 Ruff format 检查报告 1101 个文件已格式化；strict mypy 149 个源码文件通过；compileall 通过；`uv lock --check` 解析 62 个包；两个锁定 upstream 通过；`git diff --check` 通过。
- 修正后重建的 wheel/sdist 均含工作区全部 165 个应用 Python 文件且逐字节一致，必需迁移/Mako 资源存在，实际 `.env`、数据库、私钥、凭据、运行日志/profile/输出、构建缓存、临时文件、VCS/工具状态或链接成员均为零。`.env.example` 及 8 个版本化 JSONL 爬虫夹具是模板/测试数据。Wheel SHA-256：`eaba763d84ce337027cd04cd6f0a6c7fcfad015b240e139a4c61f8e783e3a4cd`；sdist SHA-256：`bc073ab59a56f26ec114cbcedacb041b91f06144119a6e97a9827629d1cc1def`。

跨进程契约证明：结果/事件 framing 仍可解析；环境中伪造的 Operation ID 被拒绝；精确 Operation 与 LoginSession 筛选能读取受管扫码事件；secret、QR、URL、正文、DOM 与私有路径哨兵均未出现在已校验事件或受管分片原始字节；丢弃计数仍然可见。

## 已发现并修正的失败

- 首次仓库全量在 138 项通过后暴露 `test_browser_policy_wiring.py` 的 14 项隔离 fixture 失败；假运行时现显式提供平台登录模块及 `tools.utils`，完整文件随后 38 项通过。
- 审查仍修改代码时启动的两轮全量被判定失效并主动中止。首个冻结 `-x` 在 3219 项通过后发现 SystemExit 预期陈旧及合成进程缺少新版必需 stderr pipe；下一次完整轮在 6918 项通过后发现五平台 Cookie 能力和 74 路由清单陈旧。修正专项 112 项通过，随后上述最终完整轮通过。
- 独立日志审查复现发布阻断问题：真实锁定版 MediaCrawler 前缀只产生 `policy_filtered`。共享规范化器修复后，51 项捕获测试及真实进程扫码/作者用例通过，同时敌对 JSON、HTML、正文、Cookie、Authorization、storage、QR、签名 URL 和私有路径哨兵未进入事件或原始分片。
- 首次包成员 denylist 误报合法 Web `/logs` 路由。规则收紧为包根运行时目录后完整审计干净；没有手工删除或豁免归档成员。
- 最终跨功能审查发现，精确交付 observer 可能永远轮询已崩溃 supervisor 留下的陈旧 `claimed`/`running` 租约。现在 observer 只重试该精确 Job，保留未过期租约，并回收过期租约。发现/交付 × claimed/running 四组回归在旧循环失败、修正源码通过。一次最终单进程全量在 3% 主动停止以改为并行；首次隔离 unit 命令又因遗漏跨目录 helper 而收集失败。显式收集该 8 项 helper 后得到上述成功最终组，唯一总数已扣除重复。

## 未执行

- 当前 Linux/Docker 镜像资格。
- 任何真人扫码登录或旧失败记录恢复。
- 真人作者采集、CDN 获取、归档播放、Emby/Jellyfin 刷新或 supervisor 恢复。
- 未配置测试数据库 URL 时的 PostgreSQL 运行测试。
