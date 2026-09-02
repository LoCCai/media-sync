[English](plan.md) | **中文**

# 执行 0029 计划

- 状态：已执行并验证
- 计划日期：2026-09-02
- 前驱：`2621f6a119aac60eaf89f0195d4fbe23bd5160f0`
- 数据库迁移：无计划
- 计划提交：记录于收尾索引；从不嵌入本文件
- 实现提交：记录于收尾索引；从不嵌入本文件

## 基线与审计

执行 0028 在 `2621f6a` 干净且已对账；其遗留的 Python 复核（`uv run python scripts/check_docs.py`，256 个 Markdown 文件）与 Ruff/上游/Bilibili 组合基线均在本工作站、任何 0029 变更之前通过。严格 v7 详情路径只接受精确一个 progressive `durl`；`len(durl) != 1` 关闭为不支持。`ResolvedMediaTarget` 没有多段变体，`_PartStore` 角色无法表达分段状态，`FFmpegStreamCopyMuxer` 只能双输入 mux 或单输入 remux，不能拼接有序分段元组。

锁定的 MediaCrawler 下载器仍只选取一个 `durl` 条目并按 `.mp4` 写出；锁定的 bili-sync-up 分析器也只取 `durl[0]`。两个 checkout 保持只读设计证据。实现前记录的基线门禁：Bilibili 组合 `4 passed in 6.95s`、`ruff check` 与 `ruff format --check` 干净、`check_docs.py`（256 文件）与 `check_upstreams.py`（2 个锁定 checkout）通过。

## 交付顺序

1. 新增 repr-safe 瞬态 `ResolvedSegmentsLocator`，持有 2–64 个有序、主地址两两互异的 Bilibili-profile 分段 locator；扩展封闭运行时联合类型、导出与惰性刷新校验，不改变持久 locator v1。
2. 把详情协议升级到 v8：接受有界有序 `durl` 元组、校验每段主/备用地址、保持 DASH 优先、保持精确一段行为不变，并把多段 FLV 关闭为不支持。
3. 通过一个新的私有字段（形状为 `{"cid", "segments": [{"url", "backup_urls"}...]}`）桥接多段目标；与全部既有私有字段严格防碰撞，持久化前递归移除，重建时对漂移关闭失败，并要求 payload CID 与所选分 P 匹配。
4. 扩展 `_PartStore` 支持有界分段角色，把 concat 列表文件作为受控的尝试内状态，并让清理可丢弃全部分段 store 与列表文件。
5. 新增类型化下载分支：共享字节上限与截止时间下的逐段有序下载、每段精确 MP4 结构探测、必须返回相同分段数的一次全鉴权刷新（漂移关闭失败）、一次固定 concat-demuxer `ffmpeg -c copy` 调用、精确 MP4 成品门、不可变归档发布、已备成品恢复与安全失败保留。
6. 为 locator 校验、协议 v8 解析、桥接碰撞/移除、刷新重建、concat argv/列表转义/身份/失败行为、逐段故障切换/鉴权/预算/探测语义、失败保留、恢复、清理与向后兼容补充单元/契约覆盖。
7. 新增生产 ffmpeg/ffprobe 的 SQLite → 主地址失败 → 备用 → 双段拼接 → SHA-256 归档 → Emby 组合并零工作重放；不保留签名 URL、原始分段或私有标记。
8. 运行专项与完整套件，加上 Ruff、format、strict mypy、compileall、build、docs、upstream、diff 与仓库审计；更新四份执行文档与根事实，然后创建双语实现/收尾提交。

## 计划提交顺序

1. 文档基线
2. 实现
3. 文档收尾

`.upstream` 保持排除、未修改且干净。
