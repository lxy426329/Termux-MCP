# Termux-MCP

> **Turn an Android phone running Termux into a secure local execution node for AI clients through MCP.**

Termux-MCP exposes shell, filesystem, and Android device capabilities through a standards-compliant MCP endpoint, then handles authentication, permissions, tunneling, lifecycle management, diagnostics, and recovery.

**AI client ↔ MCP gateway ↔ Android / Termux**

It is intentionally not a general workflow platform, VPS manager, MCP marketplace, or application suite.

> **Fork notice:** This repository is derived from [termuxgpt/termux-mcp](https://github.com/termuxgpt/termux-mcp) (AGPL-3.0). Original code and attribution remain with the upstream authors. This fork keeps the original REST surface for compatibility and focuses on a standards-compliant MCP layer plus deployment, safety, and reliability tooling.

## Quick start

```bash
curl -fsSL https://raw.githubusercontent.com/lxy426329/Termux-MCP/main/scripts/bootstrap.sh | bash
```

The setup asks for your target AI client and permission level, starts the service, verifies the MCP protocol endpoint, and prints the connection URL.

The default authentication mode is a locally generated **Bearer token**. OAuth is optional and is not silently enabled by setup.

## Core execution

- Streamable HTTP MCP endpoint at `/mcp`, built with the official Python MCP SDK.
- Shell execution through Termux.
- Filesystem read/write/list/create tools.
- Android capabilities such as battery, location, and notifications where supported.
- Structured command results including exit code, truncation, risk level, and snapshots.
- Shared operations layer so REST and MCP use the same implementation instead of proxying through localhost REST.

## Safety and owner control

Termux-MCP has three owner-selected permission modes:

- `read-only`: inspection and read-only capabilities.
- `standard` (default): normal Android/Termux operations; command risk classification and confirmation remain active.
- `full`: explicit owner opt-in for unrestricted Termux execution and advanced managed-MCP execution.

Important: **`full` bypasses command risk blocking/confirmation for shell commands.** Authentication and transport boundaries still apply, but `full` should be treated as giving the connected AI the same effective command authority as the Termux user.

Additional safeguards include:

- `realpath` workspace boundaries to reject traversal and symlink escapes;
- snapshot-before-write and upstream trash/recovery behavior;
- Bearer tokens accepted only through the `Authorization` header, never query parameters;
- managed-MCP install/call/remove restricted to `full` mode.

## Reliability and connection lifecycle

- `start`, `stop`, `restart`, `status`, `logs`, `doctor`, token management, and guided setup.
- Startup requires a real MCP `initialize` + `tools/list` handshake before a public tunnel is launched.
- Server-only restart can preserve a running tunnel and its public URL.
- Profile isolation lets stable and dev/test instances coexist on one phone.
- Multi-provider tunnel fallback.
- Persistent config/state with restrictive file permissions.
- Unit/security tests plus a live MCP smoke test in CI.

## Install manually

```bash
pkg update -y && pkg upgrade -y
pkg install -y git
git clone https://github.com/lxy426329/Termux-MCP.git
cd Termux-MCP
bash scripts/install.sh
```

Then start it:

```bash
termux-mcp start
```

A healthy startup looks roughly like:

```text
Auth token: configured (length 43)
Server started (pid 12345)
REST http://127.0.0.1:8080: OK
MCP  http://127.0.0.1:8765/mcp: OK
Tunnel (pinggy): https://xxxx.example/mcp
Public endpoint: reachable
```

If startup reports `PROTOCOL CHECK FAILED`, run:

```bash
termux-mcp doctor
termux-mcp logs -n 100
```

## Connect an MCP client

Use the URL printed by `termux-mcp start` with **Streamable HTTP**.

Bearer authentication is the default. Show the current token only when you actually need to copy it into a trusted client:

```bash
termux-mcp token --show
```

Rotate a leaked token with:

```bash
termux-mcp token --rotate
termux-mcp restart
```

Never put the token in a URL query parameter or share it publicly.

## Permission modes

```bash
termux-mcp permissions
termux-mcp permissions set read-only
termux-mcp permissions set standard
termux-mcp permissions set full
```

`standard` is the intended everyday mode. Third-party managed-MCP install, removal, and tool invocation require `full` because those servers may run package installers, build scripts, or arbitrary tool code.

## Tunnel and public access

Supported automatic tunnel providers include:

- Pinggy
- Cloudflare quick tunnel
- localhost.run

Examples:

```bash
termux-mcp start --tunnel auto
termux-mcp restart --tunnel cloudflare
termux-mcp restart --no-tunnel
```

A plain `termux-mcp restart` restarts the server while attempting to keep an already-running tunnel and public URL.

Do not expose raw port `8765` or the REST port directly to the public Internet. Keep remote access behind HTTPS and authentication.

## OAuth (optional, advanced)

Static Bearer authentication is the safe default.

The project also implements a self-hosted OAuth 2.0 authorization-code + PKCE flow for compatible clients. OAuth is enabled only when `TERMUX_MCP_OAUTH_ISSUER` is configured.

This lightweight server does **not yet provide an interactive device-owner consent UI**. Therefore the public `/authorize` endpoint denies authorization by default. Non-interactive automatic approval requires an explicit local opt-in:

```bash
TERMUX_MCP_OAUTH_ISSUER=auto
TERMUX_MCP_OAUTH_AUTO_APPROVE=1
```

Only enable automatic approval when you deliberately accept that trust model for an owner-controlled deployment. See [docs/oauth.md](docs/oauth.md).

## Advanced / experimental: managed MCP

Termux-MCP can import or host additional MCP servers and expose managed-MCP controls such as list, inspect, health, install, call, and remove.

This remains an **advanced extension**, not the core product identity. Read-only discovery is available without `full`, while installing, removing, or invoking third-party managed MCPs requires `full` permission.

It should not evolve into a general marketplace or orchestration platform inside this repository.

## Bounded multi-step execution

`run_steps` can execute an explicit list of bounded steps and keep full results locally while returning a compact response to the AI client. It does not invent plans, evaluate arbitrary conditions, or automatically replay failed side-effecting operations.

This exists to reduce tool-round-trip/context cost, not to turn Termux-MCP into a workflow engine.

## Configuration

Persistent configuration lives at:

```text
~/.config/termux-mcp/config.env
```

Environment variables override persisted values.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TERMUX_MCP_AUTH_TOKEN` | generated | Bearer token |
| `TERMUX_MCP_PORT` | `8080` | REST port |
| `TERMUX_MCP_MCP_PORT` | `8765` | MCP port |
| `TERMUX_MCP_WORKSPACE` | empty | Optional filesystem boundary |
| `TERMUX_MCP_PERMISSIONS` | `standard` | `read-only` / `standard` / `full` |
| `TERMUX_MCP_PROFILE` | empty | Isolated instance name |
| `TERMUX_MCP_TIMEOUT` | `0` | Command timeout seconds (`0` = no watchdog timeout) |
| `TERMUX_MCP_MAX_OUTPUT` | `20000` | Maximum returned command output bytes |
| `TERMUX_MCP_TUNNEL_PROVIDERS` | `pinggy,cloudflare,localhost-run` | Auto tunnel order |
| `TERMUX_MCP_OAUTH_ISSUER` | empty | Enables optional OAuth |
| `TERMUX_MCP_OAUTH_AUTO_APPROVE` | `0` | Explicitly allow non-interactive OAuth approval |

### Profile isolation

```bash
# stable instance
termux-mcp start

# separate dev/test instance
TERMUX_MCP_PROFILE=dev termux-mcp start --no-tunnel
TERMUX_MCP_PROFILE=dev termux-mcp status
```

Profiles use separate config/state directories and default ports.

## Fixed domains

Named Cloudflare tunnel helpers are available for users who need a stable hostname:

```bash
termux-mcp domain list
termux-mcp domain add mcp.example.com --port 8765 --tunnel my-tunnel
```

See [docs/DOMAIN_MIGRATION.md](docs/DOMAIN_MIGRATION.md).

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q
python scripts/mcp_smoke.py
```

CI runs the test matrix on supported Python versions, critical Ruff checks, shell syntax checks, and the live MCP smoke flow on Python 3.12.

## Project scope

- [Product scope](docs/PRODUCT.md)
- [Roadmap](docs/ROADMAP.md)
- [OAuth notes](docs/oauth.md)

## License

AGPL-3.0 — see [LICENSE](LICENSE).

Original project: [termuxgpt/termux-mcp](https://github.com/termuxgpt/termux-mcp).
