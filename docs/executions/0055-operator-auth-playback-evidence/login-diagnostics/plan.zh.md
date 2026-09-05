[English](plan.md) | **中文**

# 可操作登录诊断计划

- 日期：2026-09-05
- 状态：实现前冻结

1. 代码前先提交双语目标/计划/推进/验证，保留所有此前冻结计划。
2. 增加闭合 runner 状态 `browser_launch_failed`，保留 v1 双字段帧。新读端接受旧帧，旧读端安全拒绝新状态（不冒称前向兼容）。共用浏览器策略默认保持异常身份；登录仅在两种真实 Chromium launch await 边界选择启用分类。保留 BaseException/取消与父超时/无效结果/整树清理优先级；同模式幂等，冲突模式安全拒绝。
3. 扩展固定 Operation 摘要状态白名单，映射 `operation_login_browser_launch_failed`。不增加结果字段或 DB 列；重启恢复不知道原 runner 结果时仍保留通用失败。
4. API/CLI login-status 增加可选 `diagnostic`：`{operation_id, operation_state, runner_status, error_code}` 或 null。按最新精确会话查询至多两条 Operation，要求唯一、账户主目标正确、唯一匹配 execution subject、结果 account/session ID 一致。未知/缺失/歧义/畸形数据关闭失败，仅固定状态/码白名单，不输出任意持久字符串。不退回账户级最近操作、不补写历史、不解析日志。
5. 共用固定中文界面解释，明确区分预检与认证，刷新后保留最新会话说明。Operation 读取独立于二维码传递，所有终态不显示转圈；一旦观察终态就停止轮询并清除旧二维码，不自动重放写操作或新建登录。
6. 测运行分类、旧帧/恢复、精确身份/竞态/脱敏、API/CLI 和 UI 状态；扩大相关 Python 回归，顺序执行 Web format/test/check/build。适合时使用本地合成浏览器夹具，不用生产凭据测试补丁。
7. 保存实测结果和待跑真人门槛，独立审查、双语本地提交、推送并核实 GitHub 身份/清洁状态。总体目标保持开放，部署镜像/平台结果需操作者证据才确认。
