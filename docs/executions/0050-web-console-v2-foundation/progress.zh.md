[English](progress.md) | **中文**

# 执行 0050 推进结果

- 状态：离线基础已交付；首个 Linux 镜像已构建，运行时启动器修复待操作者重建
- 日期：2026-09-04
- 基线提交：`6d68768`

## 已交付

1. MediaCrawler 资格现把 CRLF 规范化为 LF 后使用摘要 `aeff21de8609bec9d6e939bbbba7c2914ae0a6e7c9470ea7945c03f7d17a2a33`，并拒绝任何残留裸 CR。操作者诊断脚本与缺陷计划使用同一规则。
2. `web/` 现包含锁定依赖的 SvelteKit 5 应用、共享壳层/组件/store/类型及九个运维页面。视觉系统采用浅灰固定侧栏、真白画布、克制边框/阴影、紧凑控件与表格优先的信息密度。
3. 首次使用只打开一次确认弹窗。确认以带版本的浏览器本地状态持久化；后续刷新没有勾选或弹窗，设置页提供主动重置入口。
4. 账户、订阅、任务、scheduler/pipeline 操作、扫码轮询、资产下载/校验和 Emby 导出复用已有 REST application service。内容与按作者媒体库读模型补齐其余导航面。
5. FastAPI 安全提供静态 SPA 与不可变指纹资源，保留 `/legacy`，未知 API 路径返回 404，并返回与诊断 UI 一致的完整网络边界对象。
6. Docker 在 Python 打包前构建并测试前端，支持中国大陆 npm registry 覆盖，记录 Node/pnpm/前端锁事实，且最终镜像不含 Node 运行时。
7. README、部署指南、状态页、日志索引和本执行记录现准确描述一次性确认、重建要求、当前资格摘要与剩余 Linux/真人门。
8. 操作者首次真实构建并启动了 0050 Linux 镜像。构建清单证明 Chromium `151.0.7922.34`、Node `v24.20.0`、pnpm `11.19.0` 与前端锁摘要 `dc9a47134060f185a3942bac5262b0ca55e0457a4dcddade81803e069b9bf3a0`；以运行用户直接启动 Chromium 也成功。
9. 该镜像的 doctor 已通过许可证、精确 SHA、tracked blob 与干净工作树门，但失败于 `runtime_invalid / runtime_imports_missing`。根因是 `Path.resolve()` 把 `/opt/mediacrawler-venv/bin/python` 解引用到基础解释器，从而绕过 venv 的 site-packages。现在 doctor、manifest、登录、详情刷新和调度 worker 的全部启动路径都会保留 venv launcher；Docker 构建还会以 `mediasync` 身份运行应用 doctor，使此类漂移直接中止构建。

## 浏览器与设计结果

实现保留 bili-sync 可识别的骨架——固定分组侧栏、紧凑顶栏、开放白色工作区、克制面板、表格型运维视图及底部任务/设置导航——同时把 Bilibili 单平台图表与视频源语义替换为 media-sync 的七平台账户、订阅、归档和 Emby 工作流。桌面 1440×900 与手机 390×844 截图均无主体裁切或页面横向溢出；密集表格在窄屏内局部横向滚动。

## 剩余工作

Operation 持久化、SSE/日志、更丰富详情/恢复控件、媒体服务器扫描/播放证据、操作者鉴权和移除旧控制台仍归后续计划。操作者需拉取启动器修复并无缓存重建，取得全绿 doctor 与 Chromium 深度预检后，再继续 0047 的 Bilibili/XHS 金丝雀；本执行不翻转任何真人行。
