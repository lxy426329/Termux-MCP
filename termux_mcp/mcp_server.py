"""Minimal standards-compliant MCP layer for termux-mcp.

Exposes a curated set of 8 MCP tools over Streamable HTTP using the
official `mcp` Python SDK. The tools call the same shared operations as
the REST API (termux_mcp.operations) directly — they never proxy through
the REST HTTP API.

Security:
  * Authorization: Bearer only (no tokens in URL query parameters).
  * Dangerous commands stay blocked; warning commands return a structured
    confirmation-required result.
  * Optional workspace root restriction for filesystem tools, enforced
    with realpath resolution.
"""

import hmac
import logging
import threading

from . import operations
from .config import AUTH_TOKEN, MCP_HOST, MCP_PORT, REQUIRE_AUTH, WORKSPACE_ROOT

logger = logging.getLogger(__name__)


# ── MCP tools (module-level so tests can call them directly) ─────────────────

def tool_run_command(cmd: str, confirmed: bool = False) -> dict:
    """Run a shell command on the device and return its output.

    Dangerous commands are blocked outright. Warning-level commands
    (e.g. rm -rf) require `confirmed=True` and otherwise return a
    structured confirmation-required response.
    """
    assessment = operations.assess_command(cmd, confirmed)
    if assessment["blocked"]:
        return {
            "blocked": True,
            "risk_level": assessment["risk_level"],
            "message": assessment["message"],
            "stdout": "",
            "stderr": "",
            "exit_code": 1,
            "truncated": False,
            "snapshots": [],
        }
    if assessment["confirmation_required"]:
        return {
            "confirmation_required": True,
            "risk_level": assessment["risk_level"],
            "message": assessment["message"],
            "command": cmd,
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
            "truncated": False,
            "snapshots": [],
        }
    result = operations.execute_command(cmd)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "truncated": result.truncated,
        "risk_level": result.risk_level,
        "snapshots": result.snapshots,
        "timed_out": result.timed_out,
        "cwd": result.cwd,
    }


def tool_read_file(path: str, offset: int = 0, limit: int = 500) -> dict:
    """Read a text file with line offset/limit support."""
    return operations.read_file(path, offset=offset, limit=limit, workspace=WORKSPACE_ROOT)


def tool_write_file(path: str, content: str) -> dict:
    """Write text content to a file. The previous version is snapshotted."""
    return operations.write_file(path, content, workspace=WORKSPACE_ROOT)


def tool_list_files(path: str = ".") -> dict:
    """List directory entries (including dotfiles)."""
    return operations.list_files(path, workspace=WORKSPACE_ROOT)


def tool_make_directory(path: str) -> dict:
    """Create a directory (and any missing parents)."""
    return operations.make_directory(path, workspace=WORKSPACE_ROOT)


def tool_get_location(provider: str = "gps") -> dict:
    """Get the device's last known location."""
    return operations.get_location(provider)


def tool_get_battery() -> dict:
    """Get battery status."""
    return operations.get_battery()


def tool_send_notification(
    title: str = "TermuxGPT",
    content: str = "",
    priority: str = "default",
) -> dict:
    """Send a device notification."""
    return operations.send_notification(title, content, priority)


# ── App construction ─────────────────────────────────────────────────────────

def _build_mcp_app():
    """Build the FastMCP server and return its Starlette app (with auth)."""
    from mcp.server.fastmcp import FastMCP
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    mcp = FastMCP("termux-mcp", json_response=True)

    # Explicit names: the module-level functions keep their `tool_` prefix
    # so tests can call them directly, but the MCP protocol exposes the
    # curated names required by the task spec.
    mcp.tool(name="run_command")(tool_run_command)
    mcp.tool(name="read_file")(tool_read_file)
    mcp.tool(name="write_file")(tool_write_file)
    mcp.tool(name="list_files")(tool_list_files)
    mcp.tool(name="make_directory")(tool_make_directory)
    mcp.tool(name="get_location")(tool_get_location)
    mcp.tool(name="get_battery")(tool_get_battery)
    mcp.tool(name="send_notification")(tool_send_notification)

    app = mcp.streamable_http_app()

    if REQUIRE_AUTH:
        class _AuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                auth = request.headers.get("Authorization", "")
                if auth.startswith("Bearer ") and hmac.compare_digest(
                    auth[7:], AUTH_TOKEN
                ):
                    return await call_next(request)
                return JSONResponse({"error": "Unauthorized"}, status_code=401)

        app.add_middleware(_AuthMiddleware)

    return app


def start_mcp_server():
    """Start the MCP Streamable HTTP server in a background thread.

    Returns the uvicorn Server instance (for tests) or None on failure.
    """
    try:
        import uvicorn
    except ImportError:
        logger.warning("uvicorn not installed — MCP layer disabled")
        return None

    try:
        app = _build_mcp_app()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Failed to build MCP app: %s", e)
        return None

    config = uvicorn.Config(app, host=MCP_HOST, port=MCP_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="mcp-uvicorn")
    thread.start()
    logger.info("MCP Streamable HTTP endpoint on http://%s:%d/mcp", MCP_HOST, MCP_PORT)
    return server