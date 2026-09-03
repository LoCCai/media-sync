[English](progress.md) | **中文**

# 执行 0049 推进结果

- 状态：RC 前置修复已实现；运行时验证仍归阶段 B
- 日期：2026-09-03
- 计划提交：`dcba270`（文档基线）

## 已交付

1. Dockerfile：锁定 checkout 现物化于 `/app/.upstream/MediaCrawler`（锁文件相对解析的精确路径）且保留 `.git`；安装与运行两阶段均设 `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`；运行用户拥有浏览器缓存；构建清单以 `mediasync` 实际启动 Chromium 并记录真实版本与解析后的基底镜像；应用 venv 的 freeze 回退到 `uv pip freeze`。
2. Compose 模板：`BASE_IMAGE` 作为 build arg 透传（可 digest 钉版），bind-mount 注意事项注明必须同时应用于两个服务；部署文档新增 digest 钉版 RC 构建块与容器内 doctor 预检加真实 Chromium 启动检查作为阶段 B 门。
3. API：受阻/失败的下载以带 `error_code` 的 `failed` 状态收尾操作；控制台按钮改标「下载/校验」；全部后台线程与登录状态路径使用 `create_api_app()` 捕获的设置。
4. 测试：下载端点补齐真实 Asset 生命周期覆盖——blocked→`failed`（`locator_refresh_unsupported`）、手工标记 verified 但无归档→`failed`（`asset_download_state_invalid`，诚实的不一致信号）、完成型执行器驱动 running→`succeeded` 且使用应用捕获设置。
5. 文档：两份日志文档去重（各 156 行、单 H1、单切换器）；唯一索引载有 0043 延期、0044 吸收、0047 金丝雀重构与 0049 行；0043 计划同步为延期；0044 以被吸收方式关闭并只留指针式 progress/verification；架构说明改为已交付的 ffmpeg stream-copy 事实与当前工具链；第三方声明准确描述操作者自建镜像；状态页记录脱敏 junit 工件并在裁定前把 Windows 原生运行标为 Experimental。
6. 文档检查器现拒绝重复 H1/H2、游离或多个语言切换器与中英标题结构分歧（排除代码块），并能捕获此次日志文档重复。
7. 父进程把固定完成回执原因码带入脱敏诊断（形如 `completion_failed (unsafe_path)`），测试诊断可区分完成失败原因且不含任何路径数据。

## 验证快照

确切命令、退出码与门禁输出见 [`verification.zh.md`](verification.zh.md)。

## 未完成

Docker 构建/运行、容器内 doctor 预检与以 `mediasync` 启动 Chromium 在本机保持 `NOT_RUN`（无 Docker），是阶段 B 的第一步；全部真人验收行仍归 0047。
