[English](plan.md) | **中文**

# 执行 0053 计划

- 状态：进行中
- 计划日期：2026-09-05
- 基线：be26cc7
- 数据库 revision：计划不新增
- 计划提交：包含本记录的提交（不嵌入自身 SHA）

## 基线决策

执行 0052 已完成持久操作所有权与观测。下一个可独立产生价值的控制面切片，是项目计划中承诺的安全目录：操作者需要查找已采集内容、查看资产完整度、预览不可变归档中已经证明的字节，并提交既有恢复工作流，同时不能获知内部路径或签名 locator。

当前 API 只有有界数组列表，没有内容/资产详情和归档字节端点；Web 路由会一次拉取 500–1,000 行后在内存筛选，Library 还展示配置的导出宿主路径。执行 0053 将保留兼容列表形状，把选定筛选移到服务端，新增封闭详情投影，停止展示宿主路径，并保持媒体服务器控制不在本轮范围。

## 交付顺序

1. 记录已同步的 be26cc7 基线、当前端点/UI 盘点与聚焦测试结果。
2. 新增与框架无关的 explorer 投影层，提供安全内容/资产摘要和详情；集中处理 URL 规范化、有界文本/指标、归档资格和派生允许动作。
3. 新增 repository 查询，支持精确内容/资产读取、稳定有序关联，以及可选平台、类型、状态、作者、内容、完整度和有界字面文本筛选。
4. 保持既有列表数组 payload 与参数，同时增加可选筛选。限制查询文本和 limit，转义 SQL 通配符并保持确定性排序。
5. 新增精确内容/资产详情端点。返回完整正文纯 JSON 文本、有序安全资产、安全时间戳/尺寸/checksum 与聚合导出事实，不泄漏 ORM/raw/path/locator/错误正文。
6. 实现只读归档预览服务。验证状态与元数据，要求归档根下规范 digest 路径，不跟随链接地打开，比较命名路径与已打开身份，强制普通/单链接/只读状态，再从同一描述符 hash 并流式输出。
7. 实现严格单 Range 解析及 GET/HEAD 响应：200/206/416、Accept-Ranges、Content-Length、Content-Range、ETag、安全 Content-Type 和 no-store；成功、失败与断连路径都关闭描述符。
8. 将缺失、损坏、不安全归档映射为固定安全错误和既有 asset-download 恢复链接。读取过程不修改数据库，也不新增修复 executor。
9. 更新共享 Web 类型与工具，再升级 Contents：服务端筛选、纯文本详情弹窗、有序资产动作/预览。
10. 升级 Assets：服务端筛选、安全详情弹窗、预览资格、内联或新标签预览，以及既有持久下载/校验恢复提交。
11. 升级 Library：平台/搜索筛选与作者下钻链接；移除配置的宿主导出路径。继续明确延期 Emby/Jellyfin 树与控制。
12. 运行安全、路径/Range、API、Web 专项测试，再运行 Ruff、format、strict mypy、compileall、打包、文档、上游、产物与完整套件门禁。更新全部双语记录，以可评审双语切片提交，推送 main 并完成三方 SHA 核对。

## 冻结契约

- 公开 JSON 只由显式白名单构建；通用 serializer 或 ORM 对象不得跨越 API 边界。
- 搜索是字面、trim、有界并转义通配符；既有列表数组形状和旧筛选继续有效。
- 资产恢复权威保持 POST /api/v1/assets/{asset_id}/download，并产生 0052 已有的持久 asset-download Operation；读取端点绝不 reset Asset 状态。
- 预览身份是 Asset UUID；请求数据不能选择文件系统路径。必须同时满足配置归档根与持久规范元数据。
- 验证与流式读取共享一个描述符；禁止 FileResponse 或任何“校验后重新打开”的路径。
- 安全媒体类型采用 verified probe 输出的封闭集合；未知值回退 application/octet-stream，绝不成为可执行 HTML/SVG。
- UI 只以文本呈现采集正文，绝不渲染 raw HTML，也不呈现或记录 path、locator、source URL、raw record 或异常字段。
- 预计不需要数据库 migration；若实现证明必须新增，应先暂停并修订本计划。

## 验证计划

- 投影/repository：稳定排序、可选筛选、百分号/下划线转义搜索、limit 边界、精确 not-found 及禁用字段完全缺失。
- 预览：verified/exported 门、规范路径、SHA/size、同描述符身份、可写/链接/硬链接/越界拒绝、缺失/损坏恢复结果及保证关闭。
- HTTP：GET/HEAD 对齐、完整 200、前缀/开放尾部/后缀 206、畸形/多范围/不可满足 416、精确响应头及 HEAD 空正文与 MIME 回退。
- API 安全：哨兵源 URL、签名 query、本地路径、raw key、validator 与异常正文不得出现在列表/详情/错误/预览响应头或正文。
- Web：筛选构造、安全动作派生、详情呈现及预览/恢复行为，加上 format、单测、Svelte check 和生产构建。

## 提交策略

实现前先提交本双语 goal/plan/baseline。优先将 explorer/read model、归档预览与 API、Web 目录升级及收尾文档拆成独立双语提交。禁止暂存 .mimosa、.upstream、本地数据库、archive/export/job 数据、XML 报告、node_modules、web/build、.svelte-kit 或 dist。
