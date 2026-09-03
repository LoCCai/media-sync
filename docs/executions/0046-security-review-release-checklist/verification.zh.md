[English](verification.md) | **中文**

# 执行 0046 验证

- 状态：文档范围通过全部适用门禁；外部审计与 `[主机]` 清单行仍为操作者项
- 日期：2026-09-03

## 已实现证据

| 检查 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 文档链接 | `uv run python scripts/check_docs.py` | 0 | 安全审查、发布清单与执行记录链接检查通过 |
| 声明抽查审计 | 逐条审查声明对照当前代码（机密分类、`MEDIA_SYNC_API_HOST` 默认值、compose 端口映射、桥接环境开关） | 0 | 引用的机制均如描述存在 |
| Notices 时效 | `THIRD_PARTY_NOTICES.md` 对照 `upstreams.lock.json` | 0 | 两个上游、许可证与 SHA 一致；文件未变 |
| 源码未动 | 暂存集 | 0 | 仅 `docs/**` |

## 操作者行

| 验收行 | 结果 |
| --- | --- |
| 外部安全审计 | `NOT_RUN`——可选，由操作者委托 |
| `[主机]` 干净 clone 发布演练 | 本机 `NOT_RUN`；首次执行在 Linux |
