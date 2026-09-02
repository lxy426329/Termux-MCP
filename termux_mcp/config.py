"""Configuration for termux-mcp.

Values are resolved in this order (highest priority first):
  1. Environment variables (TERMUX_MCP_*)
  2. Persistent config file  ~/.config/termux-mcp/config.env
  3. Built-in defaults

The config file is created automatically by `termux-mcp start` / `ensure_token()`
with mode 0600 so the auth token never leaks to other users. Tokens are never
printed to logs and never accepted in URL query parameters.
"""

import os
import secrets

HOME: str = os.environ.get("HOME", "/data/data/com.termux/files/home")

CONFIG_DIR: str = os.path.join(HOME, ".config", "termux-mcp")
CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.env")


def _load_config_file() -> dict:
    """Load key=value pairs from the config file (if present)."""
    values = {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


_FILE_VALUES: dict = _load_config_file()


def _env_or_file(name: str, default: str) -> str:
    """Environment variables override the config file."""
    if name in os.environ:
        return os.environ[name]
    return _FILE_VALUES.get(name, default)


def _write_config(updates: dict) -> None:
    """Persist config values to the config file (mode 0600)."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    values = dict(_FILE_VALUES)
    values.update(updates)
    lines = [
        "# termux-mcp configuration (auto-generated)",
        "# This file may contain secrets and is chmod 600.",
        "# Environment variables TERMUX_MCP_* override these values.",
    ]
    for key, value in values.items():
        lines.append(f"{key}={value}")
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, CONFIG_FILE)
    _FILE_VALUES.clear()
    _FILE_VALUES.update(values)


PORT: int = int(_env_or_file("TERMUX_MCP_PORT", "8080"))
HOST: str = _env_or_file("TERMUX_MCP_HOST", "127.0.0.1")

# Command timeout in seconds. 0 (default) = NO timeout — long operations
# like pkg update/upgrade/install run until they finish. Set a positive
# value (e.g. 600) to re-enable the watchdog kill.
COMMAND_TIMEOUT: int = int(_env_or_file("TERMUX_MCP_TIMEOUT", "0"))

# Cap on streamed command output sent to clients. Output beyond this is
# drained (process keeps running) but discarded, with a truncation marker
# appended. Keeps LLM tool results small and token-efficient.
MAX_OUTPUT_BYTES: int = int(_env_or_file("TERMUX_MCP_MAX_OUTPUT", "20000"))

AUTH_TOKEN: str = _env_or_file("TERMUX_MCP_AUTH_TOKEN", "")
REQUIRE_AUTH: bool = bool(AUTH_TOKEN)

# MCP Streamable HTTP layer (official `mcp` Python SDK).
MCP_ENABLED: bool = _env_or_file("TERMUX_MCP_MCP_ENABLED", "1").lower() in (
    "1", "true", "yes", "on",
)
MCP_HOST: str = _env_or_file("TERMUX_MCP_MCP_HOST", HOST)
MCP_PORT: int = int(_env_or_file("TERMUX_MCP_MCP_PORT", "8765"))

# Optional workspace root for MCP filesystem tools. When set, MCP
# read_file/write_file/list_files/make_directory are restricted to paths
# inside this root (resolved with realpath). REST is unaffected.
WORKSPACE_ROOT: str = _env_or_file("TERMUX_MCP_WORKSPACE", "").strip()

# Tunnel provider order for `termux-mcp start --tunnel auto`.
TUNNEL_PROVIDERS: list = [
    p.strip()
    for p in _env_or_file("TERMUX_MCP_TUNNEL_PROVIDERS", "pinggy,cloudflare,localhost-run").split(",")
    if p.strip()
]
# Seconds to wait for a tunnel provider to produce a public URL before
# terminating it and trying the next one.
TUNNEL_TIMEOUT: int = int(_env_or_file("TERMUX_MCP_TUNNEL_TIMEOUT", "45"))

AUTO_INPUT_INTERVAL: float = 0.5
PORT_POLL_INTERVAL: float = 0.3
AUTO_YES_COMMANDS: list[str] = [
    "pkg install",
    "pkg upgrade",
    "pkg update",
    "apt install",
    "apt upgrade",
    "apt update",
]


def ensure_token() -> str:
    """Ensure an auth token exists — generate and persist one if missing.

    Returns the active token. Updates the module-level AUTH_TOKEN /
    REQUIRE_AUTH so the running process enforces auth immediately.
    """
    global AUTH_TOKEN, REQUIRE_AUTH
    if AUTH_TOKEN:
        return AUTH_TOKEN
    token = secrets.token_urlsafe(32)
    _write_config({"TERMUX_MCP_AUTH_TOKEN": token})
    AUTH_TOKEN = token
    REQUIRE_AUTH = True
    return token


def rotate_token() -> str:
    """Generate a fresh auth token and persist it. Returns the new token."""
    global AUTH_TOKEN, REQUIRE_AUTH
    token = secrets.token_urlsafe(32)
    _write_config({"TERMUX_MCP_AUTH_TOKEN": token})
    AUTH_TOKEN = token
    REQUIRE_AUTH = True
    return token


def token_configured() -> bool:
    """True when an auth token is configured (env or config file)."""
    return bool(AUTH_TOKEN)