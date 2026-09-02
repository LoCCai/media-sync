[English](plan.md) | **中文**

# 执行 0034 计划

- 状态：已执行并验证
- 计划日期：2026-09-03
- 前驱：`e9d1fcdb8970b5a10f84e3947e1570159c9f9011`
- 数据库迁移：无计划
- 计划提交：`eeff45e2d862a7615d9a74c06914310dcd9f4272`
- 实现提交：`26c2b3ea974fbba8ea41a9eb496f25738b1718be`

## 基线与审计

执行 0033 在 `e9d1fcd` 干净、已推送并对账。锁定快手 store 把 `video_item.photo` 拍平为 `video_id`/`video_cover_url`/`video_play_url` 并丢弃 `ext_params`，图集 locator 正如微博的 `page_info` 一样在 `update_kuaishou_video` 边界消失。0031 微博捕获 shim 模板（ContextVar 边界、私有字段注入、防碰撞检查）、抖音图集的归一化/刷新模式以及平台无关的静态图门与 Emby gallery 发布均已成熟。`_supported_kinds(KS)` 仅因缺省而未含 IMAGE。

实现前记录的基线门禁：0033 专项 `538 passed in 71.18s`、完整 `1984 passed, 1 skipped in 336.62s`、Ruff/格式干净、strict mypy 干净、docs（296 文件）与 upstream（2 个锁定 checkout）通过。

## 交付顺序

1. 新增 `kuaishou_media.py`：封闭 `validate_ks_image_url`、跨越精确 `update_kuaishou_video` 边界的 `_capture_atlas` 通路与 `install_kuaishou_media_capture`（checkout 校验的 `store.kuaishou` 模块、marker 安全重装、私有字段防碰撞）。
2. 在定时 handler 子进程与 detail 子进程两侧安装 shim；为 `_normalize_ks` 扩展冻结 gallery 分支（精确字符串列表形状、1–64 边界、完整重校验、可选 COVER 伴随）并把该字段加入递归移除集合。
3. 把 `AssetKind.IMAGE` 加入 KS 刷新支持集合，使通用逐资产路径绑定每个图集 position 并以 `locator_refresh_asset_mismatch` 关闭路径漂移。
4. 通过真实 store 的 fake checkout（图集 vs 普通视频 vs 漂移形状）补充契约覆盖，外加归一化关闭失败结局与刷新组合。
5. 新增一条生产级 SQLite → detail 刷新 → mock DNS/HTTP → 静态 PNG 探测 → SHA-256 归档 → Emby poster/backdrop/gallery/NFO/source 组合并零工作重放与持久不泄密。
6. 运行专项与完整套件，加上 Ruff、format、strict mypy、compileall、build、docs、upstream、diff 与仓库审计；更新四份执行文档与根事实，然后创建双语实现/收尾提交，推送并对账 GitHub。

## 计划提交顺序

1. 文档基线
2. 实现
3. 文档收尾

`.upstream` 保持排除、未修改且干净。
