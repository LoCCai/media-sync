# Execution 0024 plan / 执行 0024 计划

- Status / 状态：Frozen and ready to execute / 已冻结并可执行
- Plan date / 计划日期：2026-09-02
- Predecessor / 前置：`d4c9941d2d5fb1206cd9b1a60ce2cc344a9e66e3`
- Database migration / 数据库迁移：None planned / 计划无

## Baseline and audit / 基线与审计

Execution 0023 is clean and reconciled at `d4c9941`. Its protocol v4 resolves exactly one progressive `durl` per current CID, downloader lifecycle owns one resumable file per Asset generation, finalization recovers an already-published immutable blob, and Emby already publishes ordered VIDEO siblings as primary/part files. The pinned MediaCrawler client currently asks for `fnval=1`; the pinned bili-sync-up requests `fnval=4048`, models separate DASH video/audio streams including silent video, chooses quality before codec preference, and merges with ffmpeg `-c copy -strict unofficial`. Production media-sync wires ffprobe but not ffmpeg. / Execution 0023 在 `d4c9941` 保持干净并已核对。其协议 v4 为每个当前 CID 解析精确一个 progressive `durl`，下载生命周期为每个 Asset generation 持有一个可恢复文件，收尾可恢复已发布的不可变 blob，Emby 已把有序 VIDEO 兄弟项发布为主媒体/part 文件。锁定 MediaCrawler 客户端当前请求 `fnval=1`；锁定 bili-sync-up 请求 `fnval=4048`，建模独立 DASH 视频/音频及无声视频，先按质量、再按编码偏好选择，并用 ffmpeg `-c copy -strict unofficial` 合并。生产 media-sync 已接线 ffprobe，但尚未接线 ffmpeg。

## Delivery sequence / 交付顺序

1. Add closed ephemeral single-or-DASH media target types and a strict Bilibili DASH parser/selector. Carry one private target through detail JSONL normalization only in memory and recursively strip it from durable raw. / 增加闭合的瞬态 single-or-DASH 媒体目标类型及严格 Bilibili DASH 解析/选择器；仅在内存中通过详情 JSONL 归一化携带一个私有目标，并从持久 raw 递归移除。
2. Version the detail child protocol, issue the exact WBI DASH request, preserve progressive fallback, validate page/CID binding and return one typed runtime target from parent refresh. / 升级详情 child 协议，发起精确 WBI DASH 请求，保留 progressive 回退，校验分 P/CID 绑定，并从父级刷新返回一个类型化运行目标。
3. Add a bounded ffmpeg stream-copy mux port/implementation and extend the downloader with generation-scoped video/audio/final stores, component/final probing, combined-size limits, deterministic cleanup and published-result recovery. / 增加有界 ffmpeg stream-copy 合并端口/实现，并以 generation-scoped 视频/音频/最终 store、组件/最终探测、总大小上限、确定性清理及已发布结果恢复扩展下载器。
4. Wire ffmpeg into pipeline and standalone asset-download composition. Fail capability preflight before durable child work when a pending Bilibili refresh VIDEO may require muxing and ffmpeg is unavailable. / 把 ffmpeg 接入 pipeline 与独立 Asset 下载组合；当待处理 Bilibili refresh VIDEO 可能需要合并且 ffmpeg 不可用时，在持久 child 工作前由能力预检失败。
5. Add source/unit/contract/integration coverage for quality/codec/audio selection, malformed responses, signed-target non-retention, audio-present and silent DASH, progressive compatibility, interrupted components, failed mux, archive-finalization recovery and deterministic Emby output. / 增加画质/编码/音频选择、畸形响应、签名目标不保留、带音频与无声 DASH、progressive 兼容、组件中断、合并失败、归档收尾恢复及确定性 Emby 输出的源码/单元/合约/集成覆盖。
6. Run focused and complete tests plus Ruff, format, strict mypy, compileall, build, docs, upstream, diff and retained-artifact audits; update root truth documents, create bilingual implementation/closeout commits, push and reconcile GitHub. / 运行专项与完整测试，以及 Ruff、格式、严格 mypy、compileall、构建、文档、上游、diff 与保留产物审计；更新根真值文档，创建双语实现/收尾提交，推送并核对 GitHub。

## Planned commit sequence / 计划提交序列

1. Documentation baseline / 文档基线 — `docs: 启动 Bilibili DASH 音视频合并 / start Bilibili DASH audio-video mux`
2. Implementation / 实现 — `feat: 闭环 Bilibili DASH 音视频合并 / close Bilibili DASH audio-video mux`
3. Documentation closeout / 文档收尾 — `docs: 收尾 Bilibili DASH 音视频合并 / close Bilibili DASH audio-video mux`

`.upstream` remains excluded, unmodified and clean. / `.upstream` 继续排除在跟踪外、保持未修改且干净。
