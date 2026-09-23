[English](plan.md) | **中文**

# 执行 0078 计划

- 状态：进行中
- 日期：2026-09-23

## 交付顺序

1. 先行 Track A（操作者赋能）：从 0077 handoff 提炼双语 `docs/handoff-checklist.md`/`.zh.md`，附排查速查表；加入日志导航。
2. 前端二维码面板：账户区新 Svelte 组件，激活期间每 2 秒轮询 `/crawler/api/crawler/qrcode`；状态机 等待 → 显示（digest 变化触发无感刷新）→ 过期/失败并给平台指引；默认关闭，由显式「显示登录二维码」开关启动。用 mock fetch 序列做组件测试。
3. 后端日志桥接：扩展 WebUI manager 的 `push_log` 路径，把每行已脱敏输出同时追加进既有滚动日志中心（专用来源标记）；遵守分段/总量预算与 512 条内存界；用夹具行做单元测试并断言脱敏。
4. 产物总览卡：settings/library 页信息卡，从 `GET /api/v1/settings` 渲染三个已配置根（另加固定运行时层路径）；UI 测试。
5. 文档债：`docs/status.md`(+zh) 表格刷新到 0077 边界；`docs/README.md`(+zh) 按状态叙事回填 0059–0068 索引行；导航链接。
6. 门禁：ruff/format/mypy strict/compileall/check_docs；vitest；焦点 pytest；编写工作站完整套件取新数字；双语 progress/verification；启动/实现/收尾三段式提交；推送并核对。

## 风险与回退

- 仅前端面板与只读日志桥接：回退即删除组件、桥接调用与文档编辑；不触碰 schema、权限或平台逻辑。二维码面板绝不表现为“保证登录成功”——它只是既有中继的查看器，空态/错误态必须如实。
