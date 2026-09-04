"""Minimal standards-compliant MCP layer for termux-mcp.

Exposes built-in device tools and managed-MCP control tools over Streamable HTTP using the
official `mcp` Python SDK. The tools call the same shared operations as
the REST API (termux_mcp.operations) directly — they never proxy through
the REST HTTP API.

Security:
  * Authorization: Bearer only (no tokens in URL query parameters).
  * Command behavior follows the permission level chosen by the device owner.
  * Optional workspace root restriction for filesystem tools, enforced
    with realpath resolution.
"""

import logging
import threading
import time
from urllib.parse import urlparse

from . import config
from . import managed_mcp
from . import operations
from . import permissions
from .auth import get_auth_provider
from .config import MCP_HOST, MCP_PORT, WORKSPACE_ROOT

logger = logging.getLogger(__name__)

# DNS rebinding protection (mcp SDK TransportSecuritySettings). localhost is
# always allowed; the current trusted public tunnel host is added at runtime
# once the CLI has verified a tunnel URL (see _watch_public_url). Hosts are
# never derived from Host / X-Forwarded-* request headers.
_LOCALHOST_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_LOCALHOST_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
_PUBLIC_URL_POLL_INTERVAL = 2.0

_transport_security = None  # TransportSecuritySettings instance shared with FastMCP
_transport_watcher = None   # daemon thread syncing allowed_hosts with the runtime URL
_transport_lock = threading.Lock()


def _host_entries_for_url(url: str) -> list:
    """allowed_hosts entries (host + host:*) for a trusted public base URL."""
    host = urlparse(url).hostname
    if not host:
        return []
    return [host, f"{host}:*"]


def _apply_public_url(settings, url: str) -> None:
    """Replace allowed_hosts with localhost + the current trusted public host.

    Replaces (never appends) so a changed tunnel hostname does not leave the
    previous host trusted indefinitely.
    """
    entries = list(_LOCALHOST_HOSTS)
    if url:
        entries.extend(_host_entries_for_url(url))
    settings.allowed_hosts = entries


def _watch_public_url(settings) -> None:
    """Daemon loop: keep allowed_hosts in sync with the runtime public URL.

    The MCP server can start before the CLI tunnel succeeds, so the trusted
    public host is learned from the runtime public-URL registry (written by
    the CLI only after a tunnel is verified) rather than from request headers.
    """
    current = None
    while True:
        try:
            url = config.get_public_url()
            if url != current:
                current = url
                _apply_public_url(settings, url)
        except Exception:
            pass
        time.sleep(_PUBLIC_URL_POLL_INTERVAL)


def _start_transport_security_watcher() -> None:
    """Start the public-URL watcher thread once (production server only)."""
    global _transport_watcher
    if _transport_security is None:
        return
    with _transport_lock:
        if _transport_watcher is None or not _transport_watcher.is_alive():
            _transport_watcher = threading.Thread(
                target=_watch_public_url,
                args=(_transport_security,),
                daemon=True,
                name="transport-security-watcher",
            )
            _transport_watcher.start()


# ── MCP tools (module-level so tests can call them directly) ─────────────────

def tool_run_command(cmd: str, confirmed: bool = False) -> dict:
    """Run a shell command on the device and return its output.

    Dangerous commands are blocked outright. Warning-level commands
    (e.g. rm -rf) require `confirmed=True` and otherwise return a
    structured confirmation-required response.
    """
    if not permissions.allows("command.run"):
        return permissions.denied("command.run")
    # Full mode is an explicit device-owner decision. It intentionally skips
    # repeated confirmation prompts while retaining snapshots/output limits.
    assessment = operations.assess_command(
        cmd, confirmed or permissions.current_mode() == "full"
    )
    if permissions.current_mode() == "full":
        assessment["blocked"] = False
        assessment["confirmation_required"] = False
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
    result.risk_level = assessment["risk_level"]
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
    if not permissions.allows("filesystem.write"):
        return permissions.denied("filesystem.write")
    return operations.write_file(path, content, workspace=WORKSPACE_ROOT)


def tool_list_files(path: str = ".") -> dict:
    """List directory entries (including dotfiles)."""
    return operations.list_files(path, workspace=WORKSPACE_ROOT)


def tool_make_directory(path: str) -> dict:
    """Create a directory (and any missing parents)."""
    if not permissions.allows("filesystem.write"):
        return permissions.denied("filesystem.write")
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
    if not permissions.allows("device.write"):
        return permissions.denied("device.write")
    return operations.send_notification(title, content, priority)


def tool_permissions_status() -> dict:
    """Show the permission level chosen locally by the device owner."""
    return permissions.status()


def tool_mcp_install(
    source: str,
    name: str = "",
    command: str = "",
    authorization: str = "",
) -> dict:
    """Install a remote MCP URL or GitHub MCP repository.

    For unusual GitHub projects, pass the repository's documented stdio
    launch command. The server is then available through mcp_inspect and
    mcp_call without asking the user to return to Termux.
    """
    if not permissions.allows("managed.install"):
        return permissions.denied("managed.install")
    try:
        entry = managed_mcp.install(source, name, command, authorization)
        return {
            "installed": True,
            "server": entry,
            "next": f"Call mcp_inspect with name={entry['name']!r}",
        }
    except managed_mcp.ManagedMCPError as exc:
        return {"installed": False, "error": str(exc)}


def tool_mcp_list() -> dict:
    """List MCP servers managed by this Termux gateway."""
    return managed_mcp.list_servers()


async def tool_mcp_inspect(name: str) -> dict:
    """Connect to a managed MCP server and list its available tools."""
    try:
        return await managed_mcp.inspect(name)
    except Exception as exc:
        return {"error": str(exc), "server": name}


async def tool_mcp_call(name: str, tool: str, arguments: dict = None) -> dict:
    """Call a tool exposed by an installed or imported MCP server."""
    if not permissions.allows("managed.call"):
        return permissions.denied("managed.call")
    try:
        return await managed_mcp.call(name, tool, arguments)
    except Exception as exc:
        return {"error": str(exc), "server": name, "tool": tool}


def tool_mcp_remove(name: str) -> dict:
    """Remove a managed MCP registration and archive its local files."""
    if not permissions.allows("managed.remove"):
        return permissions.denied("managed.remove")
    try:
        return managed_mcp.remove(name)
    except managed_mcp.ManagedMCPError as exc:
        return {"error": str(exc), "server": name}


# ── App construction ─────────────────────────────────────────────────────────

def _build_mcp_app():
    """Build the FastMCP server and return its Starlette app (with auth)."""
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    from . import oauth

    global _transport_security
    # Keep DNS rebinding protection enabled. localhost stays allowed; the
    # trusted public tunnel host is added once known (see _apply_public_url /
    # _watch_public_url). Passing settings explicitly also keeps the exact
    # same localhost defaults the SDK would auto-apply for host=127.0.0.1.
    _transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(_LOCALHOST_HOSTS),
        allowed_origins=list(_LOCALHOST_ORIGINS),
    )

    mcp = FastMCP(
        "termux-mcp",
        json_response=True,
        transport_security=_transport_security,
    )

    # FastMCP copies the settings into its own Settings object and the
    # session manager reads that copy, so keep the module reference on the
    # copy for runtime updates (see _apply_public_url / _watch_public_url).
    _transport_security = mcp.settings.transport_security
    # Seed with any already-known public URL (configured TERMUX_MCP_PUBLIC_URL
    # or a runtime URL written before the server started). Tunnel URLs that
    # arrive later are picked up by the watcher thread in start_mcp_server().
    _apply_public_url(_transport_security, config.get_public_url())

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
    mcp.tool(name="permissions_status")(tool_permissions_status)
    mcp.tool(name="mcp_install")(tool_mcp_install)
    mcp.tool(name="mcp_list")(tool_mcp_list)
    mcp.tool(name="mcp_inspect")(tool_mcp_inspect)
    mcp.tool(name="mcp_call")(tool_mcp_call)
    mcp.tool(name="mcp_remove")(tool_mcp_remove)

    app = mcp.streamable_http_app()

    # OAuth: authorization-server + protected-resource metadata routes.
    # These are public (no Bearer required) so MCP clients can discover
    # and complete the OAuth flow. When OAuth is disabled nothing is
    # advertised and the static Bearer behavior is unchanged.
    if oauth.oauth_enabled():
        for route in oauth.build_auth_routes():
            app.router.routes.append(route)
        for route in oauth.build_protected_resource_routes():
            app.router.routes.append(route)

    auth = get_auth_provider()
    if auth.enabled:
        class _AuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if oauth.is_public_path(request.url.path):
                    return await call_next(request)
                result = await auth.authenticate_async(dict(request.headers))
                if result.authorized:
                    return await call_next(request)
                return JSONResponse(
                    {"error": "Unauthorized"},
                    status_code=401,
                    headers=auth.challenge_headers(),
                )

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

    # The CLI may start the tunnel after this server is already up; the
    # watcher keeps DNS-rebinding allowed_hosts in sync with the runtime
    # public URL so the verified tunnel host is accepted.
    _start_transport_security_watcher()

    config = uvicorn.Config(app, host=MCP_HOST, port=MCP_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="mcp-uvicorn")
    thread.start()
    logger.info("MCP Streamable HTTP endpoint on http://%s:%d/mcp", MCP_HOST, MCP_PORT)
    return server
