[English](release-checklist.md) | **中文**

# GitHub 发布清单（执行 0046）

每次公开推送或打标签前自上而下执行。除标注 `[主机]` 的两项属于 Linux 部署主机外，其余均可离线核验。

## 仓库真实性

- [ ] `git status` 干净；所有应提交内容已提交并推送（`git log origin/main..main` 为空）。
- [ ] `uv run python scripts/check_docs.py` 通过（全部 Markdown 链接可解析）。
- [ ] `uv run python scripts/check_upstreams.py` 通过（两个锁定 checkout 均干净且处于锁定 SHA）。
- [ ] 执行索引（`docs/README.md`）各行与事实一致：没有验证记录的行不声明 Complete。

## 机密与隐私

- [ ] `git grep -iE "(set-cookie|cookie:|Authorization:)" -- docs src tests` 只出现协议代码、脱敏引用、哨兵或夹具——绝无真实凭据、session、CSRF 值或 Bearer token。
- [ ] 无 `.env`、`*.sqlite3`、`browser_data/` 或运行时输出被跟踪（`.gitignore` 已覆盖；`git ls-files | grep -iE "\.env|sqlite"` 为空）。
- [ ] `THIRD_PARTY_NOTICES.md` 为最新：两个上游、许可证正确、无内嵌代码。
- [ ] 全树无个人账户数据、二维码图片或浏览器 profile。
- [ ] 操作者鉴权示例只含类型化引用与占位路径；宿主机凭据文件及可选 Bearer 值始终位于仓库与镜像之外。

## 质量门（在已同步环境中）

- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run mypy --strict src`
- [ ] `uv run pytest -q`——完整套件在部署主机通过（把数字记入最新执行的验证文件）
- [ ] `uv run python -m compileall -q src/media_sync && uv build`

## 发布机制

- [ ] 如打发布 tag，先升 `pyproject.toml` 版本；tag 附注写明包含的执行索引区间。
- [ ] README 当前状态段引用最新收尾提交。
- [ ] `[主机]` 干净 clone 演练：全新 `git clone` → 创建外部操作者凭据文件 → 导出其绝对路径 → 按 `docs/deployment.zh.md` 操作 → 公开 health/readiness 通过且匿名业务路由被拒绝 → 一次离线冒烟（`media-sync doctor`）。
- [ ] `[主机]` 执行 0055 Web 检查点收尾前，不能把“控制台可达”记录成“控制台可用”：后端鉴权边界已存在，但已检入 Web 客户端仍缺 login/session bootstrap 与 CSRF 传播。
- [ ] `[主机]` 遵守提醒：Docker 镜像内嵌非商业上游 checkout——绝不推送至任何 registry。
