[English](security-review.md) | **中文**

# 安全与隐私审查（执行 0046）

范围：media-sync 在 0046 边界的已实现姿态，逐条声明并附强制机制。这是自审，不是外部审计。

## 1. 凭据与机密

| 声明 | 强制机制 |
| --- | --- |
| 原始 Cookie/密码绝不进入数据库、配置、日志、argv 或 Git | 需求 AUTH-004；账户只存不透明 `credential_ref`；QR/OTP 材料只存在于登录子进程内 |
| 机密引用仅在进程启动时解析 | `security/secrets.py`：`env:` / `keyring:` / `file:` 三种 scheme，`MEDIA_SYNC_SECRET_FILE_DIR` 收容根目录 |
| 签名 CDN URL 仅运行时存在 | 详情协议子进程在有界 frame/内存中携带；持久化前递归剥离（执行 0009、0013+）；留存树扫描断言零匹配 |
| 创作者权限引用为机密类型 | `creator_input.secret_ref` 走 `SecretValue` 来源；含义不明的 query/fragment URL 默认拒绝 |

## 2. 进程边界

| 声明 | 强制机制 |
| --- | --- |
| 上游爬虫绝不导入主服务 | ADR-0001：外部锁定 checkout 作为子进程；模块身份检查（`_module_belongs_to_checkout`）拒绝外来模块 |
| Cookie 只走私有环境通道 | 桥接经环境变量注入、由小型 runner 读取并在导入前移除；公开 argv 只含入口 + 受限 spec 路径 |
| 登录/抓取子进程被确定性回收 | 父进程 START/CANCEL/EOF framing、结果后 guardian、Windows Job 对象 / POSIX 进程组（执行 0012） |

## 3. 网络与文件系统策略

| 声明 | 强制机制 |
| --- | --- |
| 下载只到达公网已验证地址 | 每一跳 DNS 答案必须为公网；连接钉定；手动重定向跨源丢弃 Range validator |
| 下载路径无法逃逸配置根 | 路径收容 guard；每个目录做 symlink/lstat 检查；归档 blob 为不可变 no-clobber 链接 |
| 上游二进制下载保持关闭 | 桥接配置强制 `ENABLE_GET_MEIDAS/GET_MEDIAS = False` |

## 4. 服务暴露

| 声明 | 强制机制 |
| --- | --- |
| API/控制台默认回环 | `MEDIA_SYNC_API_HOST=127.0.0.1`；compose 仅发布 `127.0.0.1:8632:8632` |
| 无鉴权是已记录的决策 | API 是本地优先的操作者界面；容器部署文档要求可信网络；API 不可读取任何机密（payload 均为脱敏投影） |
| 结构化日志已脱敏 | 机密分类名称在落点掩码；原始适配器异常绝不进入 CLI/API 输出 |

## 5. 隐私

- 归档有意把内容关联到用户订阅的作者；采集受每订阅 `max_items`、请求延迟与封闭 request profile 约束；评论与关键词抓取为明确非目标。
- 浏览器 profile 按“平台 × 账户”隔离在 0o700 运行根下；为 Web 控制台中继的二维码图也在同一根内，并随登录尝试删除（执行 0040）。

## 6. 残余风险（如实清单）

1. API 无鉴权：能访问宿主机端口的人即可控制服务。缓解：回环/Tailscale/可信局域网。
2. SQLite 是唯一存储；拿到磁盘即拿到全部数据（含凭据*引用*——仍需 secret provider 才能使用）。
3. 上游平台行为变化可能改变锁定爬虫的行为；许可证门是确认书，不是对上游行为的技术控制。
4. 未执行外部审计（`NOT_RUN`，操作者可选项）。
