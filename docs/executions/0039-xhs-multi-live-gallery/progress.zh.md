[English](progress.md) | **中文**

# 执行 0039 推进结果

- 状态：实现完成；完整套件验证移交 Linux 部署主机执行
- 日期：2026-09-03

## 已完成

- `xhs_live.py`：v2 列表捕获新增 `XHS_LIVE_VIDEO_LIST_FIELD` 与 `XHS_LIVE_MAX_PAIRS = 16`；2–16 全实况笔记捕获有序 URL 元组，部分实况捕获为空，单图 v1 形状保持字节兼容；公开 `capture_xhs_live_fields` 供测试覆盖捕获矩阵。
- `normalizers.py`：成对 gallery 分支物化为 `MIXED`，产出有序 `{note}:image/video:{position}` 资产；要求图片与 URL 数量相等、`video_url` 为空且全部为合法 XHS-CDN URL；两个私有字段递归剥离，同时携带两个版本关闭失败。
- `refresh.py`：creator-fallback `normal` 分支从仅单对扩展为绑定 1–16 对有序 IMAGE+VIDEO，并逐对重校验实况 URL。
- 测试：捕获矩阵（`tests/unit/test_xhs_live_capture.py`）、契约漂移矩阵（ingestion）、按 position 的刷新解析与 URL 漂移拒绝、以及完整的 SQLite → detail → 4 资产下载 → 归档 → 双集 Emby 组合与零工作重放。

## 偏差与决策

- 按操作者指示，产品验证从 Windows 工作站迁移到 Linux Docker 部署；本工作站仅执行静态门、涉及文件的 `pytest --collect-only`，以及（在指示变更前）0038 焦点回归与新捕获矩阵——捕获矩阵 9 项通过、0038 ingestion 子集 8 项通过、refresh 子集 3 项通过、0038 集成 1 项通过。完整套件（含新的多实况测试）必须在 Linux 运行后，本记录才能作为最终收尾推送。

## 待完成

- 在 Linux 主机运行完整套件、Ruff/format、mypy、compileall、build、docs 与 upstream 门，并在最终推送前记录准确数字。
