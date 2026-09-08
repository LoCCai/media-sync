[English](next-delivery.md) | **中文**

# 下一交付：推进其他平台前先在部署环境验收 XHS

## 状态

**仅完成计划，执行 0077 尚未开始。** 本文档只记录下一步获授权后的执行顺序，本身不授权部署、平台请求、supervisor 重启或新实现。

## 顺序范围

1. **精确发布与重建。** 拉取已发布的 0076 revision，备份 SQLite 数据库、托管凭据和 `/data`，验证锁定上游，再重建并强制重建 API 容器。通过正常启动应用 migration `0015_xhs_creator_notes`；最初保持 supervisor 停止。
2. **统一 API 与 supervisor 配置。** 两个服务设置完全相同的 `MEDIA_SYNC_XHS_SCAN_CONTINUATION_DELAY_SECONDS`。有界金丝雀可使用默认 `300`；`0` 只关闭快速节奏，改用普通 Subscription 周期。保持 `/data/archive`、`/data/library`、`/data/jobs`、`/data/state` 和 MediaCrawler runtime 挂载一致。
3. **执行一个低流量手动金丝雀。** 使用原生 `/crawler/` 登录，等待进程空闲，把已保存 XHS 会话认领给一个 Account，再创建一个已暂停的作者 Subscription；其受保护作者 URL 必须与选定作者相同。驻留 supervisor 停止期间只恢复该 Subscription，并使用精确执行。
4. **检查每个耐久步骤。** 确认每单元仅一个来源页、页尾进度被保留、Job/Run/pipeline ID 精确一致、API 与日志不含 token/cursor，并如实显示 partial/blocked 代码。不要主动触发封禁；若自然出现访问限制，停止自动化并确认其为 `blocked`，而非源末尾。
5. **不依赖服务器控制验证目录交付。** 通过宿主挂载检查下载字节、SHA-256 归档、XHS 平台目录、NFO 和 sidecar。无需媒体服务器 API；可选 Emby/Jellyfin 读取/扫描是独立验收，不能替代目录树检查。
6. **验收重启与调度。** 一个手动单元干净通过后，重启一次 API 并证明同一 cursor 继续。仅在该证据成立后恢复 supervisor，观察一次按配置间隔发生的调度续跑；任何范围、认证、目录或诊断证据含糊时立即停止。
7. **记录精确证据。** 新增双语验收记录，包含部署 SHA/镜像身份、脱敏 Account/Subscription ID、命令、时间、目录树事实及明确 `PASS`/`FAIL`/`NOT_RUN` 行。绝不粘贴 Cookie、作者 token、不透明 cursor 或原始平台响应。

## 验收证据

- 部署镜像报告已发布 revision，且 migration `0015` 已存在。
- API 与 supervisor 暴露完全相同的 XHS 续跑间隔。
- 至少两个有界单元连续处理同一个 Subscription，不丢页尾、不重复发布。
- 至少一条兼容笔记到达 archive 和已配置目录/NFO 树；无变化重放不写新内容字节。
- 重启保留精确 cursor 与所有权链。
- 任何 partial、empty-stalled 或 access-restricted 结果都以固定代码可见，绝不计为源末尾完成。

## 停止条件

- 遇到认证含糊、作者身份不一致、意外全历史扫描、token/cursor 泄露、migration 不一致、目录权限失败或无法解释的 Job/Run 分叉时立即停止。
- 不自动重试受限账户，也不恢复无关订阅。
- 不因一次真人响应返回 `has_more=false` 就宣称历史基线永久完整；只记录为有时间边界的来源证据。

## 后续平台

XHS 金丝雀形成文档后，先追踪钉定版抖音作者作品源码路径，再冻结其独立耐久交付执行。下一设计必须从抖音代码和 fixture 推导 `has_more`、cursor、aweme 身份、详情/媒体权限、风控与页尾行为，不能复制 B 站页码或 XHS token 语义。本文档本身不会启动任何抖音实现。
