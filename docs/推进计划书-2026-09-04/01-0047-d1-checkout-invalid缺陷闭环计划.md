# 执行 0047-d1：`checkout_invalid` 缺陷闭环计划

## 1. 现场结论

已经确认：

- FastAPI 服务正常；
- SQLite 正常；
- Chromium 可以在运行容器内由默认用户启动；
- `mediacrawler doctor` 在 checkout 阶段失败；
- 登录服务因此返回 `account_login_configuration_invalid`；
- 登录子进程没有真正开始，所以二维码文件不存在，前端轮询得到 404。

因此当前故障链是：

```text
verify_mediacrawler_checkout()
  → CheckoutValidationError
  → doctor: checkout_invalid
  → login runner: CONFIGURATION_INVALID
  → account login service: account_login_configuration_invalid
  → QR 未生成
```

`chromium: launch-failed` 不是本次登录失败的直接原因，因为运行时手工启动已经成功。它说明构建清单的浏览器探针环境与运行容器不同，需要在 d2 中修正其真实性语义。

## 2. 第一动作：取得精确异常

现有 doctor 把所有 checkout 异常压缩成 `checkout_invalid`。先在容器内直接调用验证器：

```bash
docker-compose exec -T media-sync /app/.venv/bin/python - <<'PY'
from pathlib import Path
from media_sync.integrations.mediacrawler.checkout import verify_mediacrawler_checkout

try:
    result = verify_mediacrawler_checkout(
        Path("/app/upstreams.lock.json"),
        license_acknowledged=True,
    )
    print("CHECKOUT_OK")
    print(result)
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")
    raise
PY
```

仓库同时提供了本计划附带的诊断脚本：

```bash
chmod +x diagnose_mediacrawler_checkout.sh
./diagnose_mediacrawler_checkout.sh
```

## 3. 验证器的全部条件

当前验证器要求：

1. `/app/upstreams.lock.json` 存在、格式正确；
2. MediaCrawler 条目唯一；
3. repository、license 名称与内置资格值完全一致；
4. checkout 路径解析为 `/app/.upstream/MediaCrawler`；
5. checkout 是 Git 仓库根；
6. `main.py`、`config/__init__.py` 和 `LICENSE` 存在；
7. LICENSE 首行完全一致；
8. LICENSE SHA-256 完全一致；
9. Git HEAD 等于锁定 SHA；
10. 三个关键文件都是普通 tracked blob；
11. 三个工作树文件内容与 HEAD blob 完全一致；
12. 以 `core.autocrlf=input` 检查时工作树无修改和未跟踪文件。

只要任一项失败，当前 doctor 都只返回 `checkout_invalid`。

## 4. 高概率根因树

### 4.1 工作树换行或 blob 不一致

宿主机预取脚本目前主要验证 HEAD 和普通 `git status`；生产验证器还会用 `core.autocrlf=input` 重算 blob。

诊断：

```bash
docker-compose exec -T media-sync sh -lc '
c=/app/.upstream/MediaCrawler
git -C "$c" config --show-origin --get core.autocrlf || true
git -C "$c" status --porcelain --untracked-files=all
git -C "$c" -c core.autocrlf=input status --porcelain --untracked-files=all
'
```

若第二条为空而第三条非空，说明预取与运行时的换行资格规则不一致。

修复原则：

- 宿主机预取时显式 `core.autocrlf=false`；
- checkout 后执行 `git reset --hard`；
- 预取脚本使用与生产相同的 tracked-blob 计算；
- 构建前失败，而不是运行时才失败。

建议宿主机重建：

```bash
rm -rf .mediacrawler-local

git -c core.autocrlf=false init --quiet .mediacrawler-local
git -C .mediacrawler-local remote add origin \
  https://github.com/NanmiCoder/MediaCrawler.git
git -c core.autocrlf=false -c http.version=HTTP/1.1 \
  -C .mediacrawler-local fetch --depth 1 origin \
  d6f7c5bb906b6dac40ddf343ef9e26438a3de092
git -c core.autocrlf=false -C .mediacrawler-local checkout --force FETCH_HEAD
git -c core.autocrlf=input -C .mediacrawler-local status \
  --porcelain --untracked-files=all
```

### 4.2 LICENSE 摘要不一致

诊断：

```bash
docker-compose exec -T media-sync sh -lc '
c=/app/.upstream/MediaCrawler
head -n1 "$c/LICENSE"
sha256sum "$c/LICENSE"
'
```

期望资格摘要（先将 `CRLF` 规范化为 `LF`，拒绝裸 `CR`）：

```text
aeff21de8609bec9d6e939bbbba7c2914ae0a6e7c9470ea7945c03f7d17a2a33
```

原始文件摘要会因 Windows `CRLF` checkout 与 Linux `LF` checkout 不同，不能直接作为跨平台资格值。资格检查只规范化换行；随后仍以 Git tracked blob 和干净工作树证明文件与锁定提交一致。若规范化摘要不一致，不得绕过，应重新从锁定提交建立 checkout。

### 4.3 Git 仓库身份或权限问题

诊断：

```bash
docker-compose exec -T media-sync sh -lc '
set -x
id
c=/app/.upstream/MediaCrawler
ls -ld /app /app/.upstream "$c" "$c/.git"
git -C "$c" rev-parse --show-toplevel
git -C "$c" rev-parse HEAD
git -C "$c" status --porcelain --untracked-files=all
'
```

若 Git 报 dubious ownership：

- 首选修复目录所有权；
- 不要先用 `safe.directory=*` 全局放宽；
- 确认容器运行用户拥有 `/app/.upstream/MediaCrawler`。

### 4.4 `.git` 或关键文件被构建上下文过滤

当前构建会先检查 `.git`，理论上缺失应在 build 阶段失败，但仍应实测：

```bash
docker-compose exec -T media-sync sh -lc '
test -d /app/.upstream/MediaCrawler/.git
test -f /app/.upstream/MediaCrawler/main.py
test -f /app/.upstream/MediaCrawler/config/__init__.py
'
```

为消除 `.dockerignore` 语义歧义，建议显式加入：

```dockerignore
!.mediacrawler-local/
!.mediacrawler-local/**
!.mediacrawler-local/.git/
!.mediacrawler-local/.git/**
```

更稳妥的长期方案是把预取 checkout 作为 BuildKit named context 或校验后的 tar 工件传入，而不是依赖普通 context 中的嵌套 `.git`。

### 4.5 容器使用了旧镜像

检查：

```bash
git rev-parse HEAD
docker-compose images
docker inspect media-sync:local \
  --format '{{.Id}} {{.Created}}'
docker-compose exec -T media-sync \
  sed -n '1,80p' /opt/BUILD-MANIFEST.txt
```

建议将以下内容写入构建清单和 OCI labels：

- media-sync Git SHA；
- upstream Git SHA；
- base image digest；
- uv.lock SHA-256；
- MediaCrawler requirements lock SHA-256；
- 构建时间仅作为元数据，不参与可复现内容判断。

## 5. 代码修复设计

### 5.1 引入稳定错误枚举

```python
class CheckoutValidationCode(StrEnum):
    LOCK_MISSING = "lock_missing"
    LOCK_INVALID = "lock_invalid"
    CHECKOUT_MISSING = "checkout_missing"
    NOT_REPOSITORY_ROOT = "not_repository_root"
    LICENSE_HEADER_MISMATCH = "license_header_mismatch"
    LICENSE_DIGEST_MISMATCH = "license_digest_mismatch"
    REVISION_MISMATCH = "revision_mismatch"
    REQUIRED_FILE_MISSING = "required_file_missing"
    TRACKED_BLOB_MISMATCH = "tracked_blob_mismatch"
    WORKTREE_DIRTY = "worktree_dirty"
    GIT_INSPECTION_FAILED = "git_inspection_failed"
```

`CheckoutValidationError` 携带固定 code，但不携带本地路径、Git stderr 或文件内容到普通 API。

### 5.2 doctor 返回分层结果

```json
{
  "ok": false,
  "code": "checkout_invalid",
  "detail_code": "tracked_blob_mismatch",
  "checks": {
    "lock": "pass",
    "checkout_path": "pass",
    "repository_root": "pass",
    "license": "pass",
    "revision": "pass",
    "tracked_files": "fail",
    "worktree_clean": "not_run"
  }
}
```

Web 后台据此显示：

- 哪一层失败；
- 是否可以自动修复；
- 相关运维文档；
- 最近检查时间；
- 不显示 checkout 绝对宿主路径或敏感环境。

### 5.3 预取和运行时复用同一资格代码

新增：

```bash
uv run python scripts/verify_prefetched_mediacrawler.py \
  --lock upstreams.lock.json \
  --checkout .mediacrawler-local
```

它应复用生产验证器的核心纯函数，而不是用一组近似的 shell 条件。

### 5.4 增加深度就绪端点

- `/api/v1/health`：只证明服务活着；
- `/api/v1/ready`：证明数据库可用；
- `/api/v1/readiness/deep`：显式执行工具链、checkout、浏览器、路径写入和 ffmpeg/ffprobe 检查。

深度检查不得作为 30 秒一次的 Docker healthcheck，以免不断启动 Chromium；应由操作者手动触发并缓存结果。

## 6. 验收标准

必须全部满足：

- direct verifier 输出 `CHECKOUT_OK`；
- doctor 返回 `ok=true`、正确 upstream SHA；
- Chromium 运行时探针通过；
- Bilibili 登录操作不再返回 configuration invalid；
- 二维码文件在限定时间内出现；
- 关闭登录弹窗或超时后子进程和二维码材料被清理；
- 小红书同样通过启动边界；
- 日志和 API 中没有 Cookie、二维码内容、签名 URL 或完整 profile 路径；
- 修复后的完整离线套件全绿；
- 更新 `0047-d1` 四件套并保留真实阶段 B 证据。

## 7. 回退

本执行不得放宽以下安全条件：

- 不取消 LICENSE 摘要检查；
- 不取消 exact SHA；
- 不允许 dirty checkout；
- 不把任意目录加入全局 safe.directory；
- 不在失败时继续启动上游。

回退仅允许撤销诊断展示和预取实现，不得以跳过校验作为临时上线手段。
