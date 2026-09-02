[English](plan.md) | **中文**

# 执行 0015 计划

- 状态：已在冻结的离线边界内执行完成
- 计划日期：2026-08-31
- 完成日期：2026-08-31
- 前置：Execution 0014 closeout commit `6098923`
- 计划提交：`76b1973`
- 实现提交：`95d314d`

## 交付顺序

1. **冻结范围与基线**
   - 在源码编辑前创建四份双语执行记录及日志/路线图条目；保持两个锁定上游提交与外部 runtime/许可证边界。
   - 记录覆盖导入、detail、refresh/runtime、下载器/网络、Emby application/layout 及两个既有可播放平台组合的 269 项前置基线。

2. **封闭抖音持久媒体 raw**
   - 增加真实 normalize→SQLite 红测，以动态已知/未知 query、fragment、userinfo 与嵌套形状哨兵覆盖全部四个抖音媒体字段。
   - 泛化既有平台媒体字段 sanitizer，但不改变 AssetSnapshot URL。对字符串 `note_download_url` 镜像 `_url_list` 的逗号拆分，逐项独立净化，并对不透明形状关闭失败。
   - 保持快手行为并重跑其 raw/pipeline 回归。

3. **组合抖音平台流水线**
   - 只按冻结的纯 ID/配置/清理声明强化既有真实 fake-checkout 契约。
   - 新增 SQLite 绑定 E2E：一个 numeric aweme 视频与可选封面、精确 AssetRefreshSource 来源、惰性 runtime 构造、确定性签名 detail 输出、公网 DNS mock HTTP、受控 MP4 probe、归档及 Emby 发布。
   - 断言 `DEFAULT` profile 及无 Cookie/Auth/Referer/Origin；音乐字段保持为空，不宣称外挂音轨语义。

4. **证明重放、失败与落点**
   - 通过既有与新增专项 case 证明精确缺失/漂移/重复/错误来源失败。
   - 轮换 forward query 值，重放后重新读取实时 runner/network/probe 计数；扫描 ORM、SQLite/sidecar、runtime/work/archive/library、repr 及 Git 可见/build 文件中的构造 marker。
   - 获取独立只读审查，并在最终门禁前关闭全部可执行问题。

5. **验证、记录并提交**
   - 运行执行专项、完整 pytest、Ruff lint/格式、mypy、文档/上游检查、构建、补丁及保留 marker 审计。
   - 在四份记录、README、路线图、能力矩阵与架构中更新已实现/待实现真值；全部真人行保持 `NOT_RUN`。
   - 分别创建双语实现与收尾提交，推送 `main`，并验证本地/tracking/GitHub SHA 一致。

## 风险与回退点

- `note_download_url` 是上游逗号拼接字段；把它当作单个 URL 净化可能把后续项 query 留在 path 中，必须镜像 discovery 拆分并测试多项。
- 关联 `music_download_url` 是背景音乐，不是已经证明的视频外挂音轨；即使领域可保存 audio Asset，它仍不属于本切片。
- 抖音继续使用 `MediaRequestProfile.DEFAULT`；没有锁定源码或真人证据时不得增加专用 header。
- 若组合暴露产品缺陷，只修复最小共享契约并重跑 Bilibili/快手回归；不得扩张到图集或真人验收。
