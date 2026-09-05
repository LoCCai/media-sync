[English](progress.md) | **中文**

# 登录诊断推进

- 状态：已实现并通过本地验证，正在发布收尾

冻结计划 `488ce20` 已实现：仅登录在真实 Chromium launch await 边界启用 `browser_launch_failed`，作者/详情保持异常身份。严格 v1 双字段协议接受旧帧及新增闭合状态，旧读端会安全拒绝新状态，不冒称前向兼容；父取消/超时/整树清理优先级不变。

API/CLI 现从至多两条精确会话候选 Operation、至多两条 execution subject 投影可选四字段诊断。规范身份、唯一 execution 关联、经验证摘要、终态以及 runner/error/auth/session 一致性须全部匹配；非法持久 JSON 或歧义/畸形数据返回 null。不迁移、不补写历史、不解析原始日志；缺少原 disposition 的重启恢复仍为通用失败。

账户页将最新会话说明与预检分开持久展示，Jobs 使用相同固定说明。Operation/QR 独立通道防止图片失败或悬挂掩盖已观察终态；所有终态停止轮询、清理/撤销旧二维码且不显示活动转圈，不自动重试登录写入。

独立审查关闭了额外 execution 类型及矛盾完成组合两项投影问题；主代理运行/Web 审查未发现本范围剩余阻断问题。实际命令、首轮失败、重跑与剩余限制见[验证](verification.zh.md)。新的部署失败及后续 Node/二维码遗漏由[运行后续](../login-runtime-followup/progress.zh.md)处理。粘贴 Cookie 登录已接受但未实现，见[计划草案](../cookie-login/plan.zh.md)。
