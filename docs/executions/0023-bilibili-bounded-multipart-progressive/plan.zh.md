[English](plan.md) | **中文**

# 执行 0023 计划

- 状态：冻结离线范围已执行
- 计划日期：2026-09-02
- 前置：`27e45c89f20e8eb6bc871ab1505fe25167b70ae3`
- 计划提交：`bd45478b28cc61a7f35b6211faf3a0fc1eb94138`
- 实现提交：`24fd41c600eb30fb2df22079e3cf52778589959e`
- 数据库迁移：计划无

## 基线与审计

Execution 0022 已在 `27e45c8` 保持干净并完成核对。当前 Bilibili 切片只输出 `<aid>:video:0`，只选择 `pages[0].cid`，只接受精确一个 progressive `durl`，并发布一个已验证 MP4。锁定 MediaCrawler 详情响应暴露 `View.pages`，其客户端接受 `(aid, cid)`，但 JSONL store 会丢失分 P 身份。锁定 bili-sync-up 以 CID/page/name/duration 建模每个 `PageInfo`，独立选择 DASH 视频/音频并用 ffmpeg 合并；该 DASH 衍生物生命周期有意不混入本次仅 progressive 执行。

## 交付顺序

1. 增加经过校验的 Bilibili 分 P 捕获 shim，用于 forward 作者/详情存储，限制为 1–64 个规范有序分 P，并只安装在 media-sync child 进程。
2. 以私有分 P 合约扩展归一化，保留精确单页兼容，输出稳定 CID 绑定的多分 P Asset，并在持久状态前移除全部私有字段。
3. 升级严格详情 child 请求版本，携带请求 CID，只解析该分 P，并以内存 JSONL 携带完整分 P 元组与一个瞬态目标 URL。
4. 扩展数据库惰性刷新与父级校验，把每个目标绑定到完整持久 VIDEO 兄弟元组，并在任何网络字节下载前拒绝结构漂移。
5. 增加 1、2、3、64 与 65 分 P、重复/畸形/重排/替换 CID、定向播放调用、签名 URL 不保留、三份归档、Emby 多 part 输出及零工作重放的源码/单元/合约/集成覆盖。
6. 运行专项与完整测试，以及 Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与保留产物审计；更新根真值文档，创建双语实现/收尾提交，推送并核对 GitHub。

## 提交序列

1. `bd45478` — `docs: 启动 Bilibili 有界多分P progressive / start bounded Bilibili multipart progressive`
2. `24fd41c` — `feat: 闭环 Bilibili 有界多分P progressive / close bounded Bilibili multipart progressive`
3. 本文档收尾提交；有意不嵌入自身 SHA — `docs: 收尾 Bilibili 有界多分P progressive / close bounded Bilibili multipart progressive`

`.upstream` 继续排除在跟踪外、保持未修改且干净。
