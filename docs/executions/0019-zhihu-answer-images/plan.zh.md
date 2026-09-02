[English](plan.md) | **中文**

# 执行 0019 计划

- 状态：实现已交付并推送；本次变更即文档收尾
- 日期：2026-09-02
- 前置：`4fb639a`
- 计划提交：`dc1714c`
- 实现提交：`2edb9d763b4948c56cc182bcc5012914bcb644d1`

## 交付顺序

1. **审计并冻结上游边界 — complete / 已完成**
   - 锁定真实回答 `content` include、extractor → update → JSONL locator 丢失边界、默认仅回答的 creator dispatch 及缺少原生 creator 上限的事实；执行真实锁定 extractor/store 对象并保持 `.upstream` 干净。
2. **实现有界捕获与作者执行 — complete / 已完成**
   - 增加严格单图 HTML/URL 解析器、精确对象捕获绑定、嵌套 store 任务隔离及安装/冲突/来源 guard。只把校验后的知乎回答循环替换为成功受 Subscription `max_items` 约束的实现；校验短页、重复页与畸形页。
3. **归一化并刷新持久媒体 — complete / 已完成**
   - 物化 ARTICLE 加唯一 `<content_id>:image:0` IMAGE，递归移除私有/瞬态权限，从持久回答 URL 派生精确 detail 权限，并要求无凭据 DEFAULT profile 的精确刷新匹配。
4. **校验字节并组合 Emby 输出 — complete / 已完成**
   - 为知乎 IMAGE 下载自动启用有界静态结构资格校验；接受合格 JPEG/PNG/WebP，拒绝 GIF/APNG/animated WebP/AVIF，并在 normal/recovery/takeover 路径保留该标志。组合 SQLite → detail → mock HTTP → archive → Emby 输出，并审计 WAL/SHM 与保留目录；该门不会被描述为完整图片解码。
5. **验证、审查与发布 — complete for the frozen offline slice / 冻结离线切片已完成**
   - 最终扩大门通过 505 项，完整套件通过 1543 项且仅跳过 1 项 Windows 不适用用例；全部静态/类型/构建/文档/审计门通过，独立复核未发现 P0/P1/P2。双语实现提交已推送并核对。本次变更即双语文档收尾；其自引用 SHA 有意只保留在 Git 历史中，推送后的核对结果在任务交接中报告。

## 提交顺序

1. `dc1714c` — `docs: 启动知乎回答图片闭环 / start Zhihu answer-image pipeline`
2. `2edb9d763b4948c56cc182bcc5012914bcb644d1` — `feat: 闭环知乎回答图片 / close Zhihu answer-image pipeline`
3. 包含本记录的提交；有意不嵌入自身 SHA)

实现提交已在本地 `main`、`origin/main` 与 GitHub 间核对一致；`.upstream` 继续排除且干净。真人验收与更大的七平台产品目标不属于本次离线收尾范围。
