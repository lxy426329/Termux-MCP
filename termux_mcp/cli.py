"""termux-mcp command-line interface.

Commands:
  termux-mcp                          Run the server in the foreground (default).
  termux-mcp start [--tunnel MODE]    Start server + optional public tunnel.
  termux-mcp stop                     Stop the running server (and tunnel).
  termux-mcp restart [--tunnel MODE]  Restart server (+ tunnel).
  termux-mcp status                   Show server / tunnel / auth status.
  termux-mcp logs [-n N]              Show recent server logs.
  termux-mcp doctor                   Run self-checks (PASS/WARN/FAIL).
  termux-mcp token [--show] [--rotate]  Manage the auth token.

`start` is the one-command experience: it ensures an auth token exists,
starts the server, waits for REST + MCP health, starts the selected tunnel,
verifies the public URL, and prints the final MCP URL.
"""

import argparse
import os
import sys
from typing import List, Optional

from . import __version__
from . import process
from . import tunnel as tunnel_mod
from .config import (
    AUTH_TOKEN,
    MCP_ENABLED,
    MCP_HOST,
    MCP_PORT,
    PORT,
    WORKSPACE_ROOT,
    ensure_token,
    rotate_token,
    token_configured,
)

TUNNEL_CHOICES = ["auto", "pinggy", "cloudflare", "localhost-run", "none"]


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="termux-mcp",
        description="Termux MCP server — REST API + MCP Streamable HTTP + tunnel launcher.",
    )
    parser.add_argument("--version", action="version", version=f"termux-mcp {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="Start the server (and optionally a tunnel)")
    p_start.add_argument(
        "--tunnel", default="auto", choices=TUNNEL_CHOICES,
        help="Tunnel provider (default: auto)",
    )
    p_start.add_argument(
        "--no-tunnel", action="store_true",
        help="Start the server without any public tunnel",
    )

    sub.add_parser("stop", help="Stop the running server and tunnel")

    p_restart = sub.add_parser("restart", help="Restart the server")
    p_restart.add_argument(
        "--tunnel", default="auto", choices=TUNNEL_CHOICES,
        help="Tunnel provider (default: auto)",
    )
    p_restart.add_argument(
        "--no-tunnel", action="store_true",
        help="Restart without any public tunnel",
    )

    sub.add_parser("status", help="Show server / tunnel / auth status")

    p_logs = sub.add_parser("logs", help="Show recent server logs")
    p_logs.add_argument("-n", type=int, default=50, help="Number of lines (default 50)")

    sub.add_parser("doctor", help="Run self-checks")

    p_token = sub.add_parser("token", help="Manage the auth token")
    p_token.add_argument("--show", action="store_true", help="Print the full token")
    p_token.add_argument("--rotate", action="store_true", help="Generate a new token")

    return parser.parse_args(argv)


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_start(args: argparse.Namespace) -> int:
    # A. Load config / ensure token.
    token = ensure_token()
    print(f"Auth token: configured (length {len(token)})")

    # B. Avoid duplicate instances.
    if process.is_running():
        print(
            f"termux-mcp is already running (pid {process.read_pid()}). "
            "Use 'termux-mcp status' or 'termux-mcp restart'."
        )
        return 1

    # C. Start the server.
    pid = process.start_server()
    print(f"Server started (pid {pid})")

    # D. Wait for REST + MCP health.
    rest_ok = process.wait_http(PORT)
    mcp_ok = process.wait_http(MCP_PORT) if MCP_ENABLED else True
    print(f"REST http://127.0.0.1:{PORT}: {'OK' if rest_ok else 'NOT RESPONDING'}")
    if MCP_ENABLED:
        print(f"MCP  http://127.0.0.1:{MCP_PORT}/mcp: {'OK' if mcp_ok else 'NOT RESPONDING'}")
    if not rest_ok:
        print("Server did not become healthy. Check 'termux-mcp logs'.")
        return 1

    # E/F/G/H. Tunnel.
    choice = "none" if args.no_tunnel else args.tunnel
    if choice != "none":
        result = tunnel_mod.start_tunnel(MCP_PORT, choice)
        if result.url:
            mcp_url = result.url.rstrip("/") + "/mcp"
            print(f"Tunnel ({result.provider}): {mcp_url}")
            if result.process and result.process.pid:
                process.write_tunnel_pid(result.process.pid)
            if tunnel_mod.verify_url(result.url):
                print("Public endpoint: reachable")
            else:
                print("WARNING: public endpoint not reachable yet — check network/VPN.")
        else:
            print(f"Tunnel failed: {result.error}")
            print("The server is still running locally — use 'termux-mcp start --no-tunnel'.")

    # I. Next steps.
    print("\nNext steps:")
    print(f"  REST API:   http://127.0.0.1:{PORT}")
    print(f"  MCP local:  http://127.0.0.1:{MCP_PORT}/mcp")
    if choice != "none" and result.url:
        print(f"  MCP public: {mcp_url}")
    print("  Status:     termux-mcp status")
    print("  Logs:       termux-mcp logs")
    print("  Stop:       termux-mcp stop")
    return 0


def cmd_stop() -> int:
    tunnel_pid = process.read_tunnel_pid()
    if tunnel_pid:
        process.kill_pid(tunnel_pid)
        process.clear_tunnel_pid()
        print(f"Tunnel stopped (pid {tunnel_pid})")
    if process.is_running():
        pid = process.read_pid()
        process.stop_server()
        print(f"Server stopped (pid {pid})")
    else:
        process.clear_pid()
        print("Server is not running.")
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    cmd_stop()
    # Small pause so the ports are released before rebinding.
    import time
    time.sleep(1)
    return cmd_start(args)


def cmd_status() -> int:
    running = process.is_running()
    pid = process.read_pid()
    print(f"Server: {'RUNNING' if running else 'STOPPED'}" + (f" (pid {pid})" if pid else ""))
    print(f"REST http://127.0.0.1:{PORT}: {'OK' if process.port_open(PORT) else 'DOWN'}")
    if MCP_ENABLED:
        print(f"MCP  http://127.0.0.1:{MCP_PORT}/mcp: {'OK' if process.port_open(MCP_PORT) else 'DOWN'}")
    print(f"Auth: {'enabled' if token_configured() else 'DISABLED'}")
    if WORKSPACE_ROOT:
        print(f"Workspace: {WORKSPACE_ROOT}")
    tunnel_pid = process.read_tunnel_pid()
    if tunnel_pid:
        print(f"Tunnel: running (pid {tunnel_pid})")
    return 0 if running else 1


def cmd_logs(args: argparse.Namespace) -> int:
    text = process.tail_log(args.n)
    if not text:
        print("No log output yet.")
        return 0
    print(text, end="")
    return 0


def cmd_token(args: argparse.Namespace) -> int:
    if args.rotate:
        token = rotate_token()
        print("New auth token generated and saved to config (chmod 600).")
        if args.show:
            print(f"Token: {token}")
        print("Restart the server for the new token to take effect: termux-mcp restart")
        return 0
    if token_configured():
        print("Auth token: configured")
        if args.show:
            print(f"Token: {AUTH_TOKEN}")
        else:
            print("Use 'termux-mcp token --show' to display it.")
    else:
        print("Auth token: NOT configured")
        print("Run 'termux-mcp start' to auto-generate one, or 'termux-mcp token --rotate'.")
    return 0


# ── doctor ───────────────────────────────────────────────────────────────────

def _pkg_version(name: str) -> Optional[str]:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return None


def _check(checks: List[tuple], name: str, ok: bool, detail: str = "", warn: bool = False) -> None:
    status = "WARN" if warn else ("PASS" if ok else "FAIL")
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    checks.append((name, status))


def cmd_doctor() -> int:
    checks: List[tuple] = []
    print(f"termux-mcp doctor (v{__version__})\n")

    # OS / Termux
    is_termux = os.environ.get("PREFIX", "").startswith("/data/data/com.termux")
    _check(checks, "Termux environment", is_termux,
           "PREFIX detected" if is_termux else "not Termux (running on desktop?)", warn=not is_termux)

    # Python
    py = sys.version.split()[0]
    _check(checks, "Python version", py >= "3.10", py)

    # Package / deps
    pkg = _pkg_version("termux-mcp")
    _check(checks, "termux-mcp installed", pkg is not None,
           pkg or "not installed via pip (running from source is fine)", warn=pkg is None)
    mcp_ver = _pkg_version("mcp")
    _check(checks, "MCP SDK (mcp>=1.28,<2)", mcp_ver is not None and mcp_ver < "2",
           mcp_ver or "not installed")
    uvi = _pkg_version("uvicorn")
    _check(checks, "uvicorn", uvi is not None, uvi or "not installed")

    # Auth
    _check(checks, "Auth token configured", token_configured(),
           "enabled" if token_configured() else "DISABLED — run 'termux-mcp start'")

    # Workspace
    if WORKSPACE_ROOT:
        _check(checks, "Workspace root", os.path.isdir(WORKSPACE_ROOT), WORKSPACE_ROOT)
    else:
        _check(checks, "Workspace root", True, "not set (MCP filesystem tools unrestricted)", warn=True)

    # Ports
    _check(checks, f"REST port {PORT}", process.port_open(PORT),
           "listening" if process.port_open(PORT) else "not listening")
    if MCP_ENABLED:
        _check(checks, f"MCP port {MCP_PORT}", process.port_open(MCP_PORT),
               "listening" if process.port_open(MCP_PORT) else "not listening")

    # Process
    running = process.is_running()
    _check(checks, "Server process", running,
           f"pid {process.read_pid()}" if running else "not running", warn=not running)

    # Tunnel deps
    for name in ("ssh", "cloudflared"):
        import shutil
        found = shutil.which(name) is not None
        _check(checks, f"tunnel dep: {name}", found,
               shutil.which(name) or "not installed", warn=not found)

    # Localhost MCP health (authenticated probe)
    if MCP_ENABLED and process.port_open(MCP_PORT):
        try:
            import urllib.request
            req = urllib.request.Request(
                f"http://127.0.0.1:{MCP_PORT}/mcp",
                data=b"{}",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                urllib.request.urlopen(req, timeout=5)
                _check(checks, "MCP health", True, "responded")
            except urllib.error.HTTPError as e:
                _check(checks, "MCP health", e.code == 401,
                       f"HTTP {e.code}" + (" (auth working)" if e.code == 401 else ""))
        except Exception as e:
            _check(checks, "MCP health", False, str(e))
    else:
        _check(checks, "MCP health", False, "MCP port not listening", warn=True)

    print()
    fails = [c for c in checks if c[1] == "FAIL"]
    warns = [c for c in checks if c[1] == "WARN"]
    if fails:
        print(f"{len(fails)} FAIL, {len(warns)} WARN, {len(checks) - len(fails) - len(warns)} PASS")
        print("Fix the FAIL items above, then re-run 'termux-mcp doctor'.")
        return 1
    print(f"{len(checks) - len(warns)} PASS, {len(warns)} WARN, 0 FAIL")
    if warns:
        print("WARN items are optional — see details above.")
    return 0


# ── Entry point ──────────────────────────────────────────────────────────────

def run(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    if args.command is None:
        # Backward compatible: bare `termux-mcp` runs the server in the
        # foreground (same as `python -m termux_mcp`).
        from .server import run as run_server
        run_server()
        return 0

    if args.command == "start":
        return cmd_start(args)
    if args.command == "stop":
        return cmd_stop()
    if args.command == "restart":
        return cmd_restart(args)
    if args.command == "status":
        return cmd_status()
    if args.command == "logs":
        return cmd_logs(args)
    if args.command == "doctor":
        return cmd_doctor()
    if args.command == "token":
        return cmd_token(args)
    return 0


if __name__ == "__main__":
    sys.exit(run())