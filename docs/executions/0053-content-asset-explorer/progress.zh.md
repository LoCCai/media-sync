[English](progress.md) | **中文**

# 执行 0053 推进结果

- 状态：已完成；实现、冻结验证与发布核对均通过
- 收尾日期：2026-09-05
- 基线：`be26cc7`
- 计划提交：`66e18ff`
- 数据库 migration：无

## 已交付

1. 已 fetch 并通过 `--ff-only` pull `origin/main`。GitHub 在 `be26cc7` 之后没有待合入提交；本地分支只包含已提交的 0053 计划与保留的实现工作树。
2. 新增与框架无关的 `ContentAssetExplorer`，支持有界字面搜索、稳定旧排序及可选的平台/类型/状态/作者/内容/归档/导出筛选。既有内容与资产列表响应继续保持数组。
3. 新增显式安全的内容/资产投影及精确详情端点。它们提供目录、生命周期、完整性、归档与聚合导出事实，同时排除 raw、locator、源 URL、本地/导出路径、validator 和异常正文。规范链接会移除 userinfo、query 与 fragment，拒绝本地/私网目标，并只允许与内容平台匹配的官方域名边界。
4. 新增只接受 UUID 的归档 GET/HEAD。预览要求 verified/exported 状态、完整 SHA-256 与 size 元数据、精确 `archive/sha256/<前缀>/<摘要>.<扩展名>` 路径，以及普通、非链接、单硬链接、只读且摘要匹配的文件。
5. 验证与流式读取始终持有同一个描述符。Windows 使用允许读共享但拒绝写/删除共享的原生只读句柄；POSIX 保持 no-follow 打开与身份检查。两条路径都在任何字节 yield 前复核身份、大小、权限和时间戳，正常、错误、消费者中止和 ASGI 断连路径都会关闭所有权。
6. 新增纯读取的 existing-root 文件系统原语，因此 GET/HEAD 不会创建缺失的归档目录。归档根移除竞态会关闭失败，既不修复文件系统也不修改数据库。
7. 新增仅用于 GET 的严格单 byte range：支持 200/206/416、ASCII 大小写不敏感的 `bytes`、前缀/开放尾部/后缀格式及精确响应头。只有完整验证表示后才评估 Range。`If-Range` 仅在精确强当前 ETag 匹配时允许 206；过期、弱、日期或畸形 validator 均回退完整 200。RFC 9110 要求 HEAD 忽略 Range，因此 HEAD 验证完整表示、返回与完整 GET 对齐的元数据且不含正文。
8. 缺失、损坏、不安全及未就绪归档会返回固定安全的 409 结果和既有 `POST /api/v1/assets/{asset_id}/download` 持久 `asset-download` 恢复链接。本轮未新增 reset 快捷路径、Operation kind 或预览侧持久写入。
9. Contents、Assets 与 Library 已升级为有界服务端筛选、请求竞态保护、纯文本详情弹窗、有序资产动作、安全内联/新标签预览、持久恢复提交及作者下钻。Library 不再请求或显示配置的宿主 export path。
10. 公开 verified MIME 边界已与归档白名单统一，保留 PDF/SRT/VTT 值，未知值不会进入 JSON；Web 内联渲染进一步限制为更小的精确浏览器安全集合。

## 审查加固

独立后端首轮审查发现六项 P1 与四项 P2：Windows 同长度改写绕过、断连清理、MIME 分叉、Range 优先级、错误的 ranged HEAD、缺失 `If-Range`、Range token 大小写、读取侧目录创建、旧排序变化及 ASGI 层 HEAD 正文。十项均已修复，第二轮审查未发现剩余 P0/P1/P2。

独立 Web 审查随后发现两项 P1——同路由 query 导航遗留旧筛选、详情弹窗未管理键盘焦点——以及一项 P2 动作门控问题。现已通过 `afterNavigate` 状态同步、弹窗初始/约束/恢复焦点加嵌套 inert 所有权，以及严格 `allowed_actions` 恢复门控修复。审查补充的浏览器导航 P2 观察促成本轮增加上述官方域名 canonical-link 边界。

## 当前验证

- 安全、归档、explorer 与 API 回归选择：228 项通过，只有一项既有 Starlette/httpx 弃用 warning。
- 全仓 Ruff 与格式检查覆盖 199 个 Python 文件并通过；strict mypy 对 96 个源码文件通过。
- Web Prettier 通过；5 个文件的 50 项 Vitest 通过；Svelte/TypeScript 为 0 error、0 warning；adapter-static 生产构建通过。
- 本地静态构建浏览器 smoke 证明 Assets/Contents 同路由 query 清理与浏览器后退恢复、弹窗初始焦点、正反向 Tab 环、背景 inert、Escape 关闭及触发器焦点恢复。该 UI-only smoke 刻意未启动 API，因此不授予任何后端或真人资格。
- 冻结完整 Python 套件通过 2456 项，3 项 Windows 不适用测试跳过，另有一项既有 warning，耗时 479.63 秒。compileall、wheel/sdist、474 份文档、两个上游、tracked-output、本机路径与空白门均通过。专项选择存在重叠，不相加。

## 延期范围与外部门

媒体库树浏览、Emby/Jellyfin 连接配置、扫描触发与资格继续归 0054。鉴权、破坏性删除、保留和孤儿清理继续归 0055；最终迁移/发布归 0056。

执行 0047 仍是 P0。Linux 持久性/备份/进程证据、全部真人平台登录/抓取/CDN 行及真实 Emby/Jellyfin 重扫/播放继续保持 `NOT_RUN`；任何本地目录测试都不会改变这些资格。
