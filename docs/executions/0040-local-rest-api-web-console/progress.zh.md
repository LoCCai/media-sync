[English](progress.md) | **中文**

# 执行 0040 推进结果

- 状态：实现完成；运行验证限定在 Linux 部署主机
- 日期：2026-09-03

## 已完成

- `api.py`：完整 `/api/v1` 面（health/ready/settings、账户、登录状态、login-qr.png、后台登录、订阅 + 暂停/恢复/立即运行、调度 tick/run、pipeline run、任务、资产、Emby 导出、操作），带独占键操作注册表与逐请求数据库会话。
- `console.html`：中文单页控制台，扫码登录弹窗实时轮询中继二维码与操作状态。
- `media-sync serve` 命令把 uvicorn 接到 `MEDIA_SYNC_API_HOST/PORT`。
- 登录子进程 QR 中继：在既有账户根内原子写 `login-qr.png` 并随尝试删除；子进程环境白名单本就包含 `DISPLAY`/`XAUTHORITY`，无需协议变更。
- `tests/unit/test_api_server.py`：覆盖健康/控制台、账户生命周期与登录门禁、订阅/调度面与后台操作门禁。

## 偏差与决策

- 账户创建端点有意硬编码 `mediacrawler` 适配器（唯一真实适配器），并按 CLI 的 mediacrawler 分支用 `_MEDIACRAWLER_LOGIN_METHODS` 校验。
- 本工作站仅静态门（操作者指示）；`pytest --collect-only` 确认所有涉及文件可导入可收集（385 项测试）。

## 待完成

- Linux 部署验证期间执行 API 测试与完整套件。
