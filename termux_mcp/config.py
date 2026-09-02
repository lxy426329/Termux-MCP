import os

PORT: int = int(os.environ.get("TERMUX_MCP_PORT", 8080))
HOST: str = os.environ.get("TERMUX_MCP_HOST", "127.0.0.1")

HOME: str = os.environ.get("HOME", "/data/data/com.termux/files/home")

# Command timeout in seconds. 0 (default) = NO timeout — long operations
# like pkg update/upgrade/install run until they finish. Set a positive
# value (e.g. 600) to re-enable the watchdog kill.
COMMAND_TIMEOUT: int = int(os.environ.get("TERMUX_MCP_TIMEOUT", "0"))

# Cap on streamed command output sent to clients. Output beyond this is
# drained (process keeps running) but discarded, with a truncation marker
# appended. Keeps LLM tool results small and token-efficient.
MAX_OUTPUT_BYTES: int = int(os.environ.get("TERMUX_MCP_MAX_OUTPUT", 20000))

AUTH_TOKEN: str = os.environ.get("TERMUX_MCP_AUTH_TOKEN", "")
REQUIRE_AUTH: bool = bool(AUTH_TOKEN)

# MCP Streamable HTTP layer (official `mcp` Python SDK).
MCP_ENABLED: bool = os.environ.get("TERMUX_MCP_MCP_ENABLED", "1").lower() in (
    "1", "true", "yes", "on",
)
MCP_HOST: str = os.environ.get("TERMUX_MCP_MCP_HOST", HOST)
MCP_PORT: int = int(os.environ.get("TERMUX_MCP_MCP_PORT", "8765"))

# Optional workspace root for MCP filesystem tools. When set, MCP
# read_file/write_file/list_files/make_directory are restricted to paths
# inside this root (resolved with realpath). REST is unaffected.
WORKSPACE_ROOT: str = os.environ.get("TERMUX_MCP_WORKSPACE", "").strip()

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
