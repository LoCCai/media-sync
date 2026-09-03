[English](goal.md) | **中文**

# 执行 0049 目标

- 状态：RC 前置修复完成；运行时验证仍归阶段 B
- 日期：2026-09-03
- 前驱：执行 0048 收尾 `0eb3f895b02137cbfe231c705ba34aa1ce86a9f4`
- 范围：发布候选前置评审的修复——不新增产品功能
- 计划提交：记录于收尾索引；从不嵌入本文件
- 实现提交：记录于收尾索引；从不嵌入本文件

## 结果

1. 容器镜像把 MediaCrawler checkout 物化在锁文件相对解析的精确路径（`/app/.upstream/MediaCrawler`）且保留 `.git` 目录，使既有校验器接受它、doctor 预检能在容器内通过。
2. Playwright 浏览器安装到固定共享路径（`PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`）并归运行用户所有；构建清单记录以该用户实际启动的 Chromium 版本而非推导路径。
3. 失败或受阻的资产下载现在以带 `error_code` 的 `failed` 状态收尾后台操作，而非绿色 `succeeded`；端点与控制台按钮改标「下载/校验」，与已验证资产的 `already_verified` 语义一致。
4. 所有 API 后台线程使用 `create_api_app()` 捕获的设置而非重读全局设置读取器，测试客户端与运行时共享同一数据库；登录状态读取路径同步修改。
5. 下载端点补齐针对真实 Asset 的生命周期覆盖：running→succeeded、blocked→failed（固定错误码）、已验证资产无操作语义。
6. 项目日志文档删除意外重复的后半份；唯一索引反映 0043 延期、0044 由 0048/0049 吸收、0047 金丝雀先行重构；文档检查器额外拒绝重复 H1/H2 标题、游离语言切换器与中英标题结构分歧。
7. 0043 计划状态同步为延期；0044 补充明确的被 0048 吸收收尾记录；架构说明改为已交付的 ffmpeg stream-copy mux/remux/concat 事实；第三方声明准确描述操作者自建 Docker 镜像；部署指南记录 digest 钉版基底镜像构建与双服务 bind-mount 注意事项。
8. 父进程在脱敏诊断中保留固定的完成回执原因码（`unsafe_path`、`output_mismatch` 等），并把编写工作站失败清单捕获为脱敏的 junit 派生 node-ID 工件，供阶段 B 与 Linux 结果逐项 diff。

## 验收边界

- 无 schema 迁移、除改标签外不新增端点、不宣称任何真人行。Docker 构建/运行在本机保持 `NOT_RUN`（无 Docker），是阶段 B 的第一步。
- 全部修复均可静态检查或由本工作站的离线测试覆盖。

## 明确延期

Linux 阶段 B（digest 钉版镜像构建、容器内 doctor 预检、以运行用户启动 Chromium、重启持久性、备份恢复演练）及全部真人验收行仍归执行 0047 与发布清单。
