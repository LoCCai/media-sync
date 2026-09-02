[English](progress.md) | **中文**

# 执行 0022 推进记录

- 状态：冻结离线范围与文档收尾完成
- 最近更新：2026-09-02
- 前置：`817875bdd1902f54c72397fa7da46359fbe33207`
- 计划提交：`fbcb7cf5c642fc9da210faa5d92b6886b350a9b8`
- 实现提交：`b6d03aa1c6705e52c2e47c63086a5b7200c208e7`

## 已完成

- 已以干净的本地/tracking/GitHub `main` 核对 Execution 0021。
- 已审计 512 项首楼上限、4,096 字符 URL 上限、4 MiB 常规 JSONL 限制与 1 MiB child watchdog 行限制。
- 已把 v3 冻结为 3–64 张有序互异静态图片，并保留 v1/v2 精确语义。
- 已增加互斥 v3 字段与共享 64 图上限，同时保留精确 v1/v2 捕获、对象绑定、安装 marker 与并发隔离。
- 已归一化 3–64 项有序 IMAGE Asset，递归移除三个私有字段，并只持久化互异无 query hint。
- 已把每个惰性刷新 position 绑定到完整 1–64 项兄弟身份元组；缺失、新增、重排、替换、重复与多版本详情均关闭失败。
- 已通过源码/单元/进程/入库/刷新合约证明 3 与 64 图、拒绝 65 图并保留 v1/v2 兼容。
- 已证明三次 DEFAULT-profile JPEG/PNG/WebP 下载、三个 SHA-256 归档、Emby poster/backdrop/三项 gallery/body/NFO/source 及 query-only 零工作重放。
- 专项回归通过 `433 passed in 48.91s`；完整套件通过 `1688 passed, 1 skipped in 321.22s`；全部质量/构建/文档/上游/审计门通过。
- 已推送实现 `b6d03aa`；本地、tracking 与 GitHub `main` 已核对一致。

## 本执行外待实现

首楼混合/富媒体、回复/评论媒体、64 张以上图片、替换语义及全部登录/现网平台/CDN/Emby/Jellyfin 行继续延期或保持 `NOT_RUN`；更大的目标保持进行中。
