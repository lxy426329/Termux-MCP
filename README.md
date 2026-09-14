# Termux-MCP

> **Turn an Android phone running Termux into a secure local execution node for AI clients through MCP.**

Termux-MCP exposes shell, filesystem, and Android device capabilities through a standards-compliant MCP endpoint, then handles the practical parts around it: authentication, permissions, tunneling, lifecycle management, diagnostics, and recovery.

The product boundary is intentionally narrow:

**AI client ↔ MCP gateway ↔ Android / Termux**

It is not intended to become a general workflow platform, VPS manager, MCP marketplace, or application suite.

> **Fork notice**: This repository is a fork of [termuxgpt/termux-mcp](https://github.com/termuxgpt/termux-mcp) (upstream, AGPL-3.0). All original code, copyright, and attribution belong to the upstream authors. This fork keeps the original REST API intact and adds a standards-compliant MCP layer plus deployment, safety, and reliability tooling.

## Quick start

If Termux is already installed, one command handles environment checks, source download/update, dependency installation, setup, and final self-test:

```bash
curl -fsSL https://raw.githubusercontent.com/lxy426329/Termux-MCP/main/scripts/bootstrap.sh | bash
```

The first setup asks for your target AI client and permission level, starts the service, and prints the MCP URL you need to connect.

After that, normal operation should happen through the connected AI whenever practical.

## What Termux-MCP gives you

### Core execution

- **Streamable HTTP MCP endpoint** at `/mcp`, built with the official Python MCP SDK.
- **Shell execution** through Termux.
- **Filesystem tools** for reading, writing, listing, and creating files/directories.
- **Android device capabilities** exposed through Termux, including battery, location, and notifications where supported.
- **Structured tool responses** for command output, exit codes, truncation, risk level, and snapshots.
- **Shared operations layer** so REST and MCP use the same implementation instead of MCP proxying through localhost REST.

### Safety and owner control

- **Owner-selected permission modes**: `read-only`, `standard`, or `full`.
- **Command risk classification** with dangerous commands blocked and warning-class commands handled according to permission mode.
- **Snapshot-before-write** and trash-on-delete behavior inherited from the upstream safety model.
- **Workspace restriction** with `realpath` boundary checks to reject traversal and symlink escapes.
- **Bearer authentication** for remote MCP access; tokens in URL query parameters are not supported.
- Optional **OAuth 2.0 authorization-code + PKCE** support for compatible clients.

### Reliability and connection lifecycle

- **One-command launcher**: `start`, `stop`, `restart`, `status`, `logs`, `doctor`, and token management.
- **Server/tunnel lifecycle separation**: a normal server restart preserves a retained tunnel and verified public URL.
- **Persistent OAuth state** so server-only restarts do not unnecessarily force re-authorization.
- **Profile isolation** for stable and dev/test instances on the same phone.
- **Multi-tunnel support** with automatic fallback between supported providers.
- **Persistent config** under `~/.config/termux-mcp/` with restrictive file permissions.
- **Live MCP smoke test** plus unit/security coverage in CI.

## Advanced / experimental extensions

Termux-MCP can also import or host additional MCP servers and expose managed-MCP controls such as install/list/inspect/call/remove.

These features are intentionally treated as **extensions**, not the core product identity. They should remain separable from the Android execution gateway and must not drive the main roadmap toward a universal MCP marketplace or orchestration platform.

## Why this fork exists

The upstream project provides the original Termux control foundation. This fork focuses on making that foundation usable as a real MCP-connected Android execution node:

| Area | This fork's focus |
| --- | --- |
| Protocol | Streamable HTTP MCP endpoint built on the official Python SDK |
| Permissions | Owner-selected `read-only`, `standard`, or `full` control |
| Architecture | REST and MCP share the same operation functions |
| Safety | Workspace boundaries, path validation, command-risk handling, authenticated remote access |
| Reliability | Managed server/tunnel state, health checks, persistent authorization state, isolated profiles |
| Onboarding | One-line bootstrap, guided setup, one copy-ready MCP URL |

For the formal product boundary, see [docs/PRODUCT.md](docs/PRODUCT.md).

---

# 从零开始：把 Termux-MCP 跑起来

> 下面的教程面向完全不熟悉 Linux、Python、MCP 或命令行的用户。已经会用 Termux 的用户可以直接使用上面的 Quick start。

## 第 1 步：安装 Termux

从 Termux 官方推荐的发行渠道安装 Termux。常见选择包括 F-Droid 或 Termux 官方 GitHub Release。

打开 Termux，看到 `$` 提示符后即可继续。

## 第 2 步：授予存储权限（可选但推荐）

```bash
termux-setup-storage
```

手机弹出权限请求时选择允许。

## 第 3 步：更新软件包

```bash
pkg update -y && pkg upgrade -y
```

## 第 4 步：安装 git

```bash
pkg install -y git
```

## 第 5 步：下载仓库

```bash
git clone https://github.com/lxy426329/Termux-MCP.git
cd Termux-MCP
```

## 第 6 步：安装

```bash
bash scripts/install.sh
```

安装脚本会安装运行依赖、安装本项目、生成访问令牌并进行基础自检。

如果你从空 Termux 开始，更推荐直接使用：

```bash
curl -fsSL https://raw.githubusercontent.com/lxy426329/Termux-MCP/main/scripts/bootstrap.sh | bash
```

## 第 7 步：第一次启动

```bash
termux-mcp start
```

典型输出类似：

```text
Auth token: configured (length 43)
Server started (pid 12345)
REST http://127.0.0.1:8080: OK
MCP  http://127.0.0.1:8765/mcp: OK
Tunnel (pinggy): https://xxxx.a.free.pinggy.link
Public endpoint: reachable
MCP public: https://xxxx.a.free.pinggy.link/mcp
```

如果本地服务正常、但公网 tunnel 失败，服务本身仍可能已经启动。可以先运行：

```bash
termux-mcp status
termux-mcp doctor
```

## 第 8 步：连接 MCP 客户端

拿到 `termux-mcp start` 输出的 MCP public URL 后，在支持 MCP 的客户端中添加该服务。

通常需要：

- MCP URL：形如 `https://xxxx.example/mcp`
- 传输方式：Streamable HTTP
- 认证：Bearer token，或项目启用的 OAuth 流程

查看当前 token：

```bash
termux-mcp token --show
```

如果怀疑 token 泄露：

```bash
termux-mcp token --rotate
termux-mcp restart
```

**不要把 token 发给其他人，也不要把 token 放进 URL query 参数。**

## 第 9 步：第二天再次启动

```bash
termux-mcp start
```

配置和认证状态会按项目规则保留，不需要每次重新安装。

---

# Permission modes

查看当前权限：

```bash
termux-mcp permissions
```

权限模式：

- `read-only`：只读能力为主，适合保守场景。
- `standard`：默认模式，保留风险控制和必要确认。
- `full`：由设备所有者明确开启的高权限模式。

切换示例：

```bash
termux-mcp permissions set full
termux-mcp restart
```

`full` 不代表关闭认证或边界保护；它只是改变连接后的执行权限策略。

# Tunnel 与公网访问

手机通常位于 NAT、运营商网络或家庭路由器后面，因此远程 AI 客户端往往不能直接访问本地端口。Termux-MCP 可以通过 tunnel 暴露一个 HTTPS MCP 地址。

支持的 tunnel provider 包括：

- `pinggy`
- `cloudflare`
- `localhost.run`

自动模式：

```bash
termux-mcp start --tunnel auto
```

指定 provider：

```bash
termux-mcp restart --tunnel pinggy
termux-mcp restart --tunnel cloudflare
termux-mcp restart --tunnel localhost-run
```

普通：

```bash
termux-mcp restart
```

默认只重启服务器，尽量保留正在运行的 tunnel、PID 和已验证公网 URL。

显式：

```bash
termux-mcp restart --tunnel auto
```

才会重建 tunnel。

# 日常使用命令速查

| 命令 | 作用 |
| --- | --- |
| `termux-mcp start` | 启动服务器 + 自动 tunnel，打印 MCP URL |
| `termux-mcp start --no-tunnel` | 只启动本地服务器 |
| `termux-mcp start --tunnel cloudflare` | 指定 tunnel provider |
| `termux-mcp stop` | 停止服务器和 tunnel |
| `termux-mcp restart` | 只重启服务器，尽量保留现有 tunnel |
| `termux-mcp restart --tunnel auto` | 重启服务器并重建 tunnel |
| `termux-mcp restart --no-tunnel` | 重启服务器并停止 tunnel |
| `termux-mcp status` | 查看运行状态 |
| `termux-mcp logs` | 查看日志 |
| `termux-mcp doctor` | 自检（PASS/WARN/FAIL） |
| `termux-mcp doctor --json` | 输出结构化诊断结果 |
| `termux-mcp setup` | 重新运行首次连接向导 |
| `termux-mcp permissions` | 查看当前 AI 权限 |
| `termux-mcp permissions set full` | 切换到完全控制模式 |
| `termux-mcp token --show` | 显示 token |
| `termux-mcp token --rotate` | 更换 token |
| `termux-mcp domain list` | 查看命名 tunnel / 固定域名路由 |

# 配置

配置文件：

```text
~/.config/termux-mcp/config.env
```

文件自动创建并使用限制性权限。环境变量 `TERMUX_MCP_*` 优先级更高。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `TERMUX_MCP_AUTH_TOKEN` | 自动生成 | Bearer token |
| `TERMUX_MCP_PORT` | `8080` | REST 端口 |
| `TERMUX_MCP_HOST` | `127.0.0.1` | REST 绑定地址 |
| `TERMUX_MCP_MCP_PORT` | `8765` | MCP 端口 |
| `TERMUX_MCP_MCP_HOST` | `127.0.0.1` | MCP 绑定地址 |
| `TERMUX_MCP_WORKSPACE` | 空 | MCP 文件工具工作区根目录 |
| `TERMUX_MCP_CLIENT` | `chatgpt` | 首选客户端：`chatgpt` / `claude` / `grok` |
| `TERMUX_MCP_PERMISSIONS` | `standard` | `read-only` / `standard` / `full` |
| `TERMUX_MCP_TIMEOUT` | `0` | 命令超时秒数，`0` 表示不超时 |
| `TERMUX_MCP_MAX_OUTPUT` | `20000` | 输出上限字节 |
| `TERMUX_MCP_TUNNEL_PROVIDERS` | `pinggy,cloudflare,localhost-run` | auto 模式 tunnel 顺序 |
| `TERMUX_MCP_TUNNEL_TIMEOUT` | `45` | 单 provider 超时秒数 |
| `TERMUX_MCP_PROFILE` | 空 | 独立实例 profile 名称 |

## Profile isolation

同一台 Termux 可以同时运行 stable 与 dev/test 实例：

```bash
# stable
termux-mcp start

# dev
TERMUX_MCP_PROFILE=dev termux-mcp start --no-tunnel
TERMUX_MCP_PROFILE=dev termux-mcp status
```

带 profile 的实例使用独立 config/state 目录和默认端口，避免 PID、日志、public URL、token 和 OAuth state 相互覆盖。

# Security & Deployment

- **Do not expose raw MCP port 8765 or REST port 8080 directly to the public Internet.**
- Put remote MCP access behind **HTTPS** using a secure tunnel or reverse proxy.
- Keep **authentication required end-to-end**.
- **Do not put tokens in URL query parameters.**
- Bind services to localhost by default when using a local proxy or tunnel.
- Rotate credentials immediately if they are exposed.
- Consider setting `TERMUX_MCP_WORKSPACE` when the connected AI should only access a bounded directory tree.

Recommended topology:

```text
ChatGPT / Claude / MCP client
        |  HTTPS + auth
        v
secure tunnel / reverse proxy
        |  loopback HTTP
        v
127.0.0.1:8765/mcp
        |
        v
Android / Termux
```

# OAuth

Static Bearer token is the default authentication mode.

A standards-compliant OAuth 2.0 authorization-code + PKCE flow is also implemented for compatible clients. Registered clients and refresh/access tokens can persist across server-only restarts.

See [docs/oauth.md](docs/oauth.md) for implementation and configuration details.

# Advanced: managed MCP

The project currently includes optional tools for importing or managing additional MCP servers on the phone.

This is an **advanced extension**, not part of the core promise. The default product remains Android execution through MCP.

Typical advanced capabilities include:

- importing a remote MCP URL;
- preparing supported Python / Node.js MCP projects;
- listing and inspecting managed MCPs;
- calling or removing a managed MCP.

These capabilities may evolve independently and should not be required for a normal Termux-MCP installation.

# Fixed domains

Fixed-domain and named-tunnel support exists for users who need a stable public endpoint.

Useful commands include:

```bash
termux-mcp domain list
termux-mcp domain add mcp.example.com --port 8765 --tunnel my-tunnel
```

See [docs/DOMAIN_MIGRATION.md](docs/DOMAIN_MIGRATION.md) for migration details.

# Troubleshooting

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `command not found: termux-mcp` | 安装未完成 | 重跑 `bash scripts/install.sh` |
| `uvicorn not installed` | 依赖未安装完整 | 重跑安装脚本 |
| `No module named mcp` | MCP SDK 未安装 | 重跑安装脚本或检查 Python 环境 |
| `port already in use` | 已有实例占用端口 | `termux-mcp status` 后决定是否停止旧实例 |
| `401 Unauthorized` | 未带认证或凭据错误 | 检查 Bearer token / OAuth 配置 |
| `400 Bad Request / Missing session` | MCP 握手或 session 问题 | 确认 URL 以 `/mcp` 结尾并使用支持的客户端 |
| `406 Not Acceptable` | 请求头 / transport 不兼容 | 使用支持 Streamable HTTP 的客户端 |
| tunnel timeout | 网络或 provider 不可达 | 更换 provider 或网络后重试 |
| Pinggy URL 变化 | tunnel 被重建 | 普通 `restart` 尽量保留 URL；重建后更新客户端配置 |
| Android 杀后台 | 系统回收 Termux | 检查电池优化、后台权限与 wake-lock 配置 |

如果无法判断问题来源：

```bash
termux-mcp doctor
termux-mcp logs -n 100
```

# Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
python scripts/mcp_smoke.py
```

CI currently covers supported Python versions, unit tests, critical Ruff checks, and shell syntax checks.

See also:

- [Product scope](docs/PRODUCT.md)
- [Roadmap](docs/ROADMAP.md)
- [OAuth notes](docs/oauth.md)

# License

AGPL-3.0 — see [LICENSE](LICENSE).

Original project by [termuxgpt/termux-mcp](https://github.com/termuxgpt/termux-mcp).
