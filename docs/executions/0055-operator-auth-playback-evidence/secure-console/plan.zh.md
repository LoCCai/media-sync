[English](plan.md) | **中文**

# 安全后台与启动计划

- 日期：2026-09-05
- 基线：`2e1949f`
- 状态：实现前冻结

## 实现顺序

1. 实现前单独提交本双语八文件基线；保持父级与此前子级冻结文件不变。
2. 增加 `serve --check-config`，复用真实有界 secret/origin 校验与 host/port 覆盖。成功只输出固定安全配置状态；凭据缺失／不可读／无效、settings／origin 错误均在 app、数据库、目录和 socket 工作前失败，不反射值或引用。
3. 容器 `serve` 在 Xvfb 与 `db init` 前先预检；显式仅检查／help 不迁移。既有非 serve CLI 流程保持兼容。部署说明对应实际运行用户所有权、rootless 映射和备份，不用全局可读权限或递归 chown。
4. 增加串行／single-flight 的 auth bootstrap/login/session/logout。Login 200 不含 CSRF，必须再取得有效 session 才授予访问。鉴权响应会设置／删除 Cookie，不能不安全地重叠。凭据／CSRF 只驻内存，不保留到 URL／localStorage／sessionStorage／service worker。
5. 全部私有组件树与 onboarding 由 authenticated 状态控制；提供登录、重试／配置错误与退出。过期／重置时清私有状态并取消请求。业务迟到响应使用发起时 session epoch，不能使新登录失效。不自动重放写入（包括 CSRF 失败）；退出失败明确为尚未确认。
6. 客户端规范化 header、限制同源请求、仅给非安全方法注入当前 CSRF，正确处理 204。二维码 fetch 纳入会话边界，销毁时撤销 Blob URL，防止卸载后迟到创建。SSE 错误关闭流，并先做一次 session 检查再 fallback／重连；直接媒体保持 Cookie 路径。
7. 保留精确匿名资源白名单。Middleware 对未登录 HTML GET/HEAD 且路径精确为 `/accounts`、`/subscriptions`、`/contents`、`/assets`、`/library`、`/jobs`、`/settings`、`/diagnostics` 时只返回到根登录入口的 303，携带固定白名单返回路径并丢弃任意 query。Host 仍最先检查，API／未知路径仍固定拒绝，重定向不调用下游 handler。前端只接受同一固定返回路径集合。
8. 把 legacy／fallback 交互 HTML 替换为受保护迁移／构建提示，并纠正 onboarding 的“无鉴权”旧文案；不得公开 legacy 或撤销后端保护。
9. 增加状态机／客户端与后端专项，再串行运行 Web format/test/check/build，并用可丢弃的合成账户／任务／媒体夹具完成真实本地后端＋已构建浏览器 smoke。逐项记录夹具证明范围，不能授予真人平台／播放资格。
10. 执行相称的完整 Python／静态／文档／上游／打包门，独立复核鉴权竞态与迁移前顺序。没有真实 Docker 主机时最终镜像／运行 UID 检查为 NOT_RUN。显式暂存已审查路径、双语提交、推送并验证远端分叉和干净状态。

## 验证边界

覆盖未登录门、login 后 session 顺序、鉴权串行、写入 CSRF 与安全方法 header、退出／过期、旧响应、不重放写入、204、二维码取消、SSE 会话失效、深链接 GET/HEAD 与 Host/API 拒绝。证明仅配置检查对全新及既有数据库／状态均无修改（含不可读凭据），验证 entrypoint 顺序，但不把静态检查冒充 Linux 执行。

用既有本地浏览器工具完成组合流程；截图／日志不得保留凭据、CSRF、Cookie、原始二维码或私有 locator。不需要用户平台凭据或真人远端操作。当前镜像、真实 PostgreSQL、重启／恢复与真人金丝雀状态保持如实。
