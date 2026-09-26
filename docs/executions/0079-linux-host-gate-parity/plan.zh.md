[English](plan.md) | **中文**

# 执行 0079 计划

- 状态：已完成
- 日期：2026-09-26

## 步骤

1. 服务器 checkout fast-forward 到远端 `main`，先 stash 再恢复未提交的 2026-09-12 部署记录文档，随后作为独立记录提交并推送。
2. 安装宿主工具链（uv、Node 22 与钉定 pnpm）并在拉取后的树上运行全部本地门禁，取得基线失败清单。
3. 通过在原始树上重跑失败集合，把每个失败归因到根因，确保既有的宿主失败不会被误判为回归。
4. 让 strict mypy 门禁与平台无关：把包裹错误的 `os.name` 守卫换成 mypy 可收窄的 `sys.platform` 守卫（运行时等价），仅在 Windows 辅助函数必须在 POSIX mock 原生契约下保持可调用处使用成对 `attr-defined, unused-ignore` 注释。
5. 修复测试侧可移植性：把 `Path(sys.executable).resolve()` 夹具值替换为生产 `normalize_python_executable` 语义；POSIX 启动器测试的 subprocess mock 只拦截启动器探测；放宽一个负载敏感的截停断言但保持远小于被截停子进程的生命周期。
6. 用 BEGIN IMMEDIATE 加有界重试修复 Emby 失败记录的 WAL busy-snapshot 竞态，镜像 operation coordinator 的耐久写模式。
7. 在最终树上复跑完整门禁集合，用精确源码 revision 重建部署镜像，重建容器并验证健康、deep doctor 与 UI 可达性。

## 偏差

- 无：每个计划步骤都已执行；一个负载敏感的取消类测试在 26 分钟完整套件中失败一次，隔离重跑 3/3 通过（记录于验证文档）。
