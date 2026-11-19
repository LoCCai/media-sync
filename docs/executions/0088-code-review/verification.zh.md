[English](verification.md) | **中文**

# 验证：六方向独立代码审查

## 方法

六个只读审查者并行审计 `830b4d0` 的代码树，各自范围互不重叠：耐久创作者状态机（0084–0086）、迁移与摄取边界、媒体下载/网络层、API/CLI 操作者契约、Svelte 控制台、密钥与隐私。每个审查者都被要求通过阅读生产代码与运行定向探针来核实，只报告已确认的问题，并把"已核实缺陷"与"无法确认"分开。

下列每一条都在改代码前于本会话内重新核实过。有两条审查结论在核实后被驳回，单独列出。

## 修复后的最终门禁

| 门禁 | 结果 |
| --- | --- |
| Python 完整套件 | `7331 passed, 62 skipped, 108 warnings in 1817.38s` |
| Ruff lint / format | `All checks passed!`；`466 files already formatted` |
| strict mypy | `Success: no issues found in 182 source files` |
| 文档链接 | `Documentation links OK (866 Markdown files checked)` |
| 钉定上游 | `Upstreams OK (2 locked checkouts verified)` |
| Web `svelte-check` | `0 errors and 0 warnings` |
| Web `vitest` | `846 passed (846)`——比 843 多三个平台用例 |
| Web Prettier / build | 干净；`✓ built in 11.73s` |
| `git diff --check` | 退出码 0 |

## 已修缺陷

### 功能性——0085/0086 连一个单元都无法完成

1. **知乎页尾回放中止整个单元。** shim 用 `for content in contents` 按位置遍历。单元在页中途停下时保留同一 offset，于是回放把已交付回答再喂给状态机，被当作契约漂移拒绝——行写进去了，覆盖见证却没封。已改为由 `unit.next_action()` 驱动。回归测试 `test_partial_page_replays_only_the_missing_answer` 在没有该修复时失败。
2. **贴吧/知乎调用了上游 store 回调。** 上游传入 `batch_update_tieba_notes` / `batch_update_zhihu_contents`，其全部函数体就是再走一遍受守卫的 store；第二次写入时身份 ContextVar 已重置并抛错。shim 自己已经持久化了每一项，因此回调被刻意不调用（代码内已写明理由）。两个回归测试固定该行为。
3. **`NormalizedMediaCrawlerOutput` 丢掉了 `tieba_coverage` / `zhihu_coverage`。** 两者被解析、校验后即被丢弃，于是 handler 的 `(manifest_scan is None) != (output_coverage is None)` 检查必然失败，每次 0085/0086 运行都以 `output_security_failed` 结束。
4. **管线 worker 从不发布知乎进度。** `zhihu_delivery_policy` 构造了，但 `ZhihuDeliveryProgressRepository` 从未被调用，行永远停在 `backfill`。已补两个迁移点，并新增 `tests/unit/test_pipeline_worker_wiring.py`，枚举七个平台，任一 publisher 缺失即失败。

### 功能性——耐久链永远无法推进

5. **只有 B 站投稿与 XHS 传了 `source_run_id`。** 缺它时交付回执停在 schema 1，而七个 `publish_success` 实现都对 schema-1 回执 `return None`——于是微博/贴吧/知乎（以及抖音/快手）的进度行建了却永不推进。现对每个有界创作者平台都派生 Run 身份。
6. **微博把"未推进的页"算作已消费页。** `pages_consumed` 在停滞判断之前自增，算术 `total` 镜像可能据一个被重放的页报告**假源末**，把行推进 `incremental`，而大部分历史尚未抓取。
7. **贴吧越过停滞页继续前进。** 重复页时 `page + 1` 会把该页主题永久丢弃，且下一个正常页会清零停滞计数、掩盖丢失。现保持页码不变并由有界停滞计数阻塞。
8. **贴吧把 `has_more=1` 的空页当作源末。** 这正是限流响应被解析出的形状；它会发布**空头部边界**，而空边界与任何值对账都相等，让行进入增量而全部积压未抓。现改为有界停滞，且空页在三个平台上都不再建立头部边界。
9. **知乎把任何部分窗口重叠当作停滞。** 由于 `offset` 是 page\*limit 乘积，出现一条新回答会合法地重复上一页尾部；把它当停滞会让订阅在第一条新回答处永久卡死。现部分重叠是正常漂移并继续推进，只有完全相同的页才停滞。
10. **知乎对"空但未结束"的响应体抛错。** 限流下的 `data: []` 变成没有见证的硬上游错误；现改为有界停滞。

### 摄取边界的正确性

11. **`_record_run_contents` 把 B 站的 30 条上限套用到了所有平台。** 三个新有界摄取声明 1000，于是任何超过 30 条笔记的微博页都会中止摄取并无限重试。上限现在是必填的 `limit` 参数，由各调用点按平台传入。
12. **微博的 `declared_total` 比耐久列更宽松。** 超过 2⁵³−1 的值能通过扫描层，随后在管线事务内触发 CHECK 失败，把已完成的单元变成无限重试。witness 与 summary 现均按列边界拒绝。

### 安全

13. **`secure_delete=ON` 覆盖不到 WAL 旁文件。** 已实测：进程突然退出后，主文件干净而 `crash.sqlite3-wal` 里仍能读到 sentinel。`checkpoint_sqlite_wal()` 现于 `upgrade_database` 之后执行，并有回归测试证明 sentinel 从旁文件消失。
14. **调用方注入的 Alembic 连接不执行任何 pragma。** 由普通 `create_engine()` 得到的裸 `Connection` 会以 `secure_delete=OFF` 执行 0003 重建。`env.py` 现通过裸 DBAPI cursor 施加 pragma（而非 `exec_driver_sql`，后者会隐式开启事务并破坏 Alembic）。
15. **`db status` 使用普通 `create_engine`。** 它是唯一没有托管 pragma 的引擎；现改用 `create_database_engine`。
16. **ffprobe/ffmpeg 子进程继承整个环境。** 由于 `Settings` 从 `os.environ` 解析 `env:` 密钥引用，每个探针/封装子进程都拿到了平台 Cookie 与媒体服务器 API Key。现均运行在 `media_child_environment()` 允许列表下。

### 前端

17. **原生二维码面板永远显示不出二维码。** `nativeQrRead` 请求 `/crawler/api/crawler/qrcode`，而 `sessionRequest` 只允许 `/api/`，在 `fetch` 之前就抛错。面板随后归咎平台，并让所有用户改用 Cookie 粘贴。现允许该只读中继前缀，且 `dispose()` 会中止在途轮询。
18. **快手面板恰在有真实证据时退化为"证据不可用"。** 它复用抖音的停止原因集合，其中没有 `no_more_echoed`。停止原因现按平台声明，未知标签回退到原始码而不是整块置空。
19. **微博/贴吧/知乎完全没有交付基线面板**，尽管 API 早已发送三者载荷。已补类型、卡片规格（含平台专有的 `declared_total` / `last_page_number` / `last_offset` 字段与停止原因）与面板分支。
20. **导出的诊断报告在健康部署上声称 schema 漂移。** 前端修订列表停在 `0011_cookie_login`，于是两个修订都被置空、`revision_matches` 强制为 false。现已与后端集合对齐到 `0020_zhihu_creator_answers`，并用集合比较验证相等。
21. **概览把单个接口失败报成"服务连接失败"。** 九个请求在同一个 `Promise.all` 里，且一并清了 `healthOk`；一个 503 会丢掉其余八个成功结果。现改为独立（`allSettled`），`healthOk` 只由 `/health` 决定。30 秒刷新也不再让计数器闪成"—"。
22. **缺失的错误文案把 snake_case 泄露到界面。** 已补 API 实际使用的码（`operation_state_conflict`、`database_not_ready`、`log_cursor_stale`、`login_qr_gone` 等），并给剪贴板复制加上 `try/catch`。

### 操作者契约

23. **九个构造点全都缺续跑策略。** WebUI 的贴吧/知乎流程根本不会物化进度行，管线 publisher 也以 `upstream_sha=None` 计算绑定。七个策略现已贯穿 `api.py`（5 处）与 `cli.py`（4 处），并在缺失处导入 `WeiboScanContinuationPolicy`。
24. **`_KNOWN_DATABASE_REVISIONS` 里有两个条目是文件名而非修订 ID。** 停在 `0001_core`/`0002_checkpoint` 的数据库会报 `revision: null`。已修复，并加了逐迁移解析真实 `revision` 字符串的联动测试。
25. **"恰好一个" 守卫只覆盖四个平台**（输出一致性元组与封存恢复的策略↔manifest 配对都是）。已扩展到七个。
26. **`models.__all__` 漏了三个新进度类**及其词表。

## 核实后驳回

- *"每份导出的诊断报告都是错的"* 部分夸大：修订列表确实陈旧（已修），但报告解析器本身是正确的。
- *"知乎的 `stalled_units` 是死代码"*：位移语义修复后，该计数器已成为知乎唯一的阻塞路径，该结论不再成立。

## 已报告但未改动

- **抖音 `bit_rate` 上限为 8 项**，真实的 10–16 项载荷会静默回退到钉定扁平化，而不是使用 0083 的排序。放宽上限会改变 0083 的冻结行为，需要独立执行。
- **`validate_ks_image_url` 没有 CDN 主机允许列表；`validate_xhs_video_url` 接受明文 `http`。** 两者都是 0081/0076 行为，不在本次审查的改动范围内；各自需要独立执行并重新推导上游事实。
- **动画 GIF/WebP 在五个平台上被当作静态 IMAGE 接受**（只有贴吧/知乎要求静态）。同样的理由。
- **`DEFAULT` 请求 profile 仍会发送 httpx 的 `User-Agent`**，因此文档中"完全不发 User-Agent"的措辞不准确。仅文档问题。

## 已运行命令

```text
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy --strict src
python scripts/check_docs.py
python scripts/check_upstreams.py
npm --prefix web run check | test | format:check | build
git diff --check
```
