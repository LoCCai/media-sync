[English](release-checklist.md) | **中文**

# GitHub 发布清单（执行 0046）

每次公开推送或打标签前自上而下执行。除标注 `[主机]` 的两项属于 Linux 部署主机外，其余均可离线核验。

## 仓库真实性

- [ ] `git status` 干净；所有应提交内容已提交并推送（`git log origin/main..main` 为空）。
- [ ] `uv run python scripts/check_docs.py` 通过（全部 Markdown 链接可解析）。
- [ ] `uv run python scripts/check_upstreams.py` 通过（两个锁定 checkout 均干净且处于锁定 SHA）。
- [ ] 执行索引（`docs/README.md`）各行与事实一致：没有验证记录的行不声明 Complete。
- [ ] 资格 v3 中无作者为 `not_requested`；PASS 只适用于具有精确当前持久确认的单个作者，仓库真人行保持基于实际证据的状态。

## 机密与隐私

- [ ] `git grep -iE "(set-cookie|cookie:|Authorization:)" -- docs src tests` 只出现协议代码、脱敏引用、哨兵或夹具——绝无真实凭据、session、CSRF 值或 Bearer token。
- [ ] 精确 `.env`、数据库、浏览器 profile、`.mimosa/` 或运行时输出均未被跟踪或打包。使用根路径感知的精确路径/扩展名扫描，不能误伤合法 `.env.example`；同时确认 `.gitignore` 与 `.dockerignore` 都覆盖 `.mimosa/`。
- [ ] `THIRD_PARTY_NOTICES.md` 为最新：两个上游、许可证正确、无内嵌代码。
- [ ] 全树无个人账户数据、二维码图片或浏览器 profile。
- [ ] 操作者鉴权示例只含类型化引用与占位路径；宿主机凭据文件及可选 Bearer 值始终位于仓库与镜像之外。

## 质量门（在已同步环境中）

- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run mypy --strict src`
- [ ] `uv run pytest -q`——完整套件在部署主机通过（把数字记入最新执行的验证文件）
- [ ] `uv run python -m compileall -q src/media_sync && uv build`；检查全新 wheel/sdist 含必需应用/migration 文件，并拒绝运行时根目录、`.mimosa/`、secret、数据库、日志、partial 文件与工作站路径。

## 发布机制

- [ ] 如打发布 tag，先升 `pyproject.toml` 版本；tag 附注写明包含的执行索引区间。
- [ ] README 当前状态段引用最新收尾提交。
- [ ] `[主机]` 干净 clone 演练：全新 `git clone` → 创建外部操作者凭据文件 → 导出其绝对路径 → 按 `docs/deployment.zh.md` 操作 → 公开 health/readiness 通过且匿名业务路由被拒绝 → 一次离线冒烟（`media-sync doctor`）。
- [ ] `[主机]` 当前安全控制台已实现且已通过[本地合成浏览器验证](executions/0055-operator-auth-playback-evidence/secure-console/verification.zh.md)；不能把根 HTML 或 health 可达写成完整控制台／真人可用。逐项记录 login→session、CSRF 修改、QR／直接媒体／SSE、退出／过期；P1 确认 UI 不前置于 CLI 金丝雀。
- [ ] `[主机]` 对精确当前镜像按[部署指南](deployment.zh.md)覆盖 entrypoint 运行 `serve --check-config`，核实真实运行 UID 下凭据可读且非法配置先于迁移失败；命令不证明 DNS／端口或完整就绪。当前 Linux／Docker 门未执行时保持 NOT_RUN，不复用 0050 历史 PASS。
- [ ] `[主机]` 遵守提醒：Docker 镜像内嵌非商业上游 checkout——绝不推送至任何 registry。
