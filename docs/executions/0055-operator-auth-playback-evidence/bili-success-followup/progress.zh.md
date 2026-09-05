[English](progress.md) | **中文**

# 推进结果

- 状态：登录及 Worker 展示修正已实施，本地门禁通过；获授权真人采集失败。

生产浏览器只读观察：B 站账户为 saved_session/authenticated，最近 Operation、LoginSession、runner 均成功（18:42:03–18:42:48）；同一账户页却显示 account_login_ineligible 已阻塞。共有九个操作（一成功、八个历史失败），零 Job、零订阅。本次核查未发起登录、提取 Cookie 或修改生产数据。

独立合成复现：原 pong 始终 False，update_cookies 后仍认证成功；未用真实凭据或访问平台。这证明代码路径缺陷，不证明用户此次是假成功。依据冻结计划 b018979，已实施仅 BILI 的更新后远程确认和已认证账户的中性预检展示。后端重复登录资格未放宽，前端旧预检不能重新授权登录。

## 获授权真人采集

用户指定作者 UID 252671524，明确接受可能遍历完整历史，并确认停止常驻 supervisor。浏览器执行仅本地的作者预览，创建一个测试订阅，物化一个 Job，再使用既有保存会话启动一次同步 Worker。表单设置 max_items=1、请求间隔 5 秒，但 B 站上游作者路径在采集及最终元数据入库均不遵守这一条数上限，不能宣称只采一条。代理未代替用户接受许可证、提取凭据、重新登录、重试 Job 或启动下载/导出。

这次尝试运行于 18:53:18–18:57:14（约 236 秒），终态 failed_terminal、零内容入库。Worker Operation 的成功只代表处理完一个 Job，其摘要为 processed_count=1、status_counts.failed_terminal=1。测试订阅已暂停，队列无待处理 Job 或活动 Operation，账户仍为 authenticated/saved_session。supervisor 按用户操作保持停止，没有观察到 pipeline Job。

用户执行的两次只读查询分别记录：首次查询 SyncRun 错误返回 not_available，不能区分记录缺失和错误码为空；之后精确 Job→Run JOIN 确认 Job 存在、job_error=schema_invalid、Run 存在、run_status=running、run_error=none。这不能证明 Cookie 无效、作者不存在或某个具体平台异常。调度层存在只终止 Job 而未同步更新 Run 错误的路径，heartbeat/结果/收尾异常还需更精确的安全诊断。不能手工改写历史 Run、把资格改为 PASS 或自动重试掩盖结果。

Worker 成功/Job 失败的误导展示促成独立提交的补充计划 9602246；控制台现区分 Worker 完成与严格校验的 Job 结果，不改持久 Operation 语义。原页没有完成 toast，因此没有新增通知生命周期。最终 Web 269 项及静态构建门禁通过。真人采集为 FAILED，新会话认证证明仍未达标，下载及 Emby/Jellyfin 播放继续 NOT_RUN。粘贴 Cookie 校验/保存/复用仍是已接受但未实现的需求，独立 vault 与严格远程证明方案还需实施前冻结；七平台范围不变。

## 下一执行顺序

1. 冻结 heartbeat/存储/结果/收尾异常的精确调度诊断，保留已成功 Run 真相、租约隔离及进程清理；不靠猜测或改写历史数据解释 schema_invalid。
2. 在用户控制的部署后验证明确有界的作者路径和失败测试，不静默重试当前已暂停订阅。
3. 完成独立规划的粘贴 Cookie 校验/私密保存/复用增量，再建立其他平台契约及归档/播放验收；当前 UI 修正不等于实现 Cookie 输入。
