[English](verification.md) | **中文**

# 执行 0054 验证

- 状态：进行中；目前只有变更前基线
- 基线时间：2026-09-05 02:40-02:46 +08:00
- 基线：`22b5864`

## 变更前证据

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| Git 同步 | `git pull --ff-only origin main`；比较 `git rev-parse HEAD` 与 `git rev-parse origin/main` | 0 | `PASS`——两者均为 `22b58646e79b17b2d49ff803df34e976466999c3`；只有既存 `.mimosa/` 未跟踪 |
| Emby/explorer/API 专项 | `uv run --frozen pytest -q -p no:cacheprovider tests/unit/test_emby_layout.py tests/integration/test_emby_application.py tests/contract/test_emby_export_contract.py tests/unit/test_content_asset_explorer.py tests/unit/test_api_operations.py` | 0 | `PASS`——121 项通过；只有一个既有 Starlette/httpx 弃用 warning |
| Web 单元基线 | `npm --prefix web test -- --run` | 0 | `PASS`——5 个文件、50 项测试 |
| 补丁空白 | 写入本日志前运行 `git diff --check` | 0 | `PASS`——干净 |

## 计划实现证据

收尾记录将补充媒体库检查器、媒体服务器 connector、Operation/migration/API 契约、资格投影、Web 工具与路由、浏览器交互、完整 Python 套件、静态分析、生产 build、文档/上游、产物/本机路径检查、Git 提交、推送及 GitHub 对账的精确命令、退出码、数量、环境和有效结果。

## 证据政策

本基线不宣称任何真实媒体服务器或平台结果。工作区没有配置 Emby/Jellyfin URL、key 或 library ID。Mock transport 和临时导出树只能证明封闭协议与文件系统契约。真实连接/版本/library 发现、扫描完成、项目查找、抽样播放、自动扫描、Linux 主机行为、平台账户/API 与 CDN 字节，在存在操作者证据前全部保持 `NOT_RUN`。
