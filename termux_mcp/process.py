"""Process management for the termux-mcp launcher.

State lives under ~/.local/state/termux-mcp/ (XDG-style):
  server.pid   — PID of the running `python -m termux_mcp` server
  tunnel.pid   — PID of the active tunnel process (if any)
  server.log   — captured stdout/stderr of the server
  tunnel.log   — captured stdout/stderr of the tunnel process

The launcher never uses bare `&` backgrounding: every child is tracked by
PID file, and stop/restart/status operate on those PIDs.
"""

import asyncio
import os
import signal
import subprocess
import sys
import time
from typing import Optional

from .config import STATE_DIR

PID_FILE: str = os.path.join(STATE_DIR, "server.pid")
TUNNEL_PID_FILE: str = os.path.join(STATE_DIR, "tunnel.pid")
LOG_FILE: str = os.path.join(STATE_DIR, "server.log")
TUNNEL_LOG_FILE: str = os.path.join(STATE_DIR, "tunnel.log")


def state_dir() -> str:
    return STATE_DIR


def pid_file() -> str:
    return PID_FILE


def tunnel_pid_file() -> str:
    return TUNNEL_PID_FILE


def log_file() -> str:
    return LOG_FILE


def tunnel_log_file() -> str:
    return TUNNEL_LOG_FILE


def _pid_alive(pid: Optional[int]) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        waited_pid, _ = os.waitpid(pid, os.WNOHANG)
        if waited_pid == pid:
            return False
    except ChildProcessError:
        pass
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as stat_file:
            fields = stat_file.read().split()
        if len(fields) >= 3 and fields[2] == "Z":
            return False
    except OSError:
        pass
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def read_pid() -> Optional[int]:
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def write_pid(pid: int) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(pid))


def clear_pid() -> None:
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def read_tunnel_pid() -> Optional[int]:
    try:
        with open(TUNNEL_PID_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def write_tunnel_pid(pid: Optional[int]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    if pid:
        with open(TUNNEL_PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    else:
        clear_tunnel_pid()


def clear_tunnel_pid() -> None:
    try:
        os.remove(TUNNEL_PID_FILE)
    except OSError:
        pass


def is_running() -> bool:
    """True when the server PID file points at a live process."""
    pid = read_pid()
    if not pid:
        return False
    if _pid_alive(pid):
        return True
    clear_pid()
    return False


def tunnel_is_running() -> bool:
    """True when the tunnel PID file points at a live process."""
    pid = read_tunnel_pid()
    if not pid:
        return False
    if _pid_alive(pid):
        return True
    clear_tunnel_pid()
    return False


def kill_pid(pid: Optional[int], timeout: float = 5.0) -> bool:
    """Terminate a process by PID (SIGTERM, then force-kill)."""
    if not pid or not _pid_alive(pid):
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, signal.SIGTERM)
            break
        except OSError:
            time.sleep(0.2)
    while time.time() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.2)
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except (OSError, AttributeError):
            pass
    return not _pid_alive(pid)


def start_server(env: Optional[dict] = None) -> int:
    """Start the termux-mcp server as a detached child process."""
    if is_running():
        raise RuntimeError(
            f"termux-mcp is already running (pid {read_pid()}). "
            "Use 'termux-mcp status' or 'termux-mcp restart'."
        )
    os.makedirs(STATE_DIR, exist_ok=True)
    log_f = open(LOG_FILE, "ab")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    child_env = dict(env or os.environ.copy())
    proc = subprocess.Popen(
        [sys.executable, "-m", "termux_mcp"],
        cwd=repo_root,
        env=child_env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    write_pid(proc.pid)
    return proc.pid


def stop_server(timeout: float = 10.0) -> bool:
    """Stop the running server. Returns True if it was stopped."""
    pid = read_pid()
    if not pid:
        return False
    stopped = kill_pid(pid, timeout)
    if not stopped:
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if not _pid_alive(pid):
                stopped = True
                break
            time.sleep(0.2)
    if stopped or not _pid_alive(pid):
        clear_pid()
    return stopped


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    """Check whether a TCP port is accepting connections."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_http(port: int, timeout: float = 15.0) -> bool:
    """Wait until a TCP listener is available (REST warm-up helper)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port):
            return True
        time.sleep(0.3)
    return False


async def _mcp_probe(url: str, token: str) -> bool:
    """Perform a real MCP initialize + tools/list round trip."""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(
        url, headers={"Authorization": f"Bearer {token}"}
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return bool(tools.tools)


def mcp_healthy(port: int, token: str, timeout: float = 4.0) -> bool:
    """Return True only when the MCP protocol handshake actually succeeds."""
    if not token:
        return False
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        return bool(asyncio.run(asyncio.wait_for(_mcp_probe(url, token), timeout=timeout)))
    except Exception:
        return False


def wait_mcp(port: int, token: str, timeout: float = 15.0) -> bool:
    """Wait for a usable MCP endpoint, not merely an open TCP port."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port, timeout=0.5):
            remaining = max(0.5, min(4.0, deadline - time.time()))
            if mcp_healthy(port, token, timeout=remaining):
                return True
        time.sleep(0.3)
    return False


def tail_log(n: int = 50) -> str:
    """Return the last n lines of the server log."""
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except OSError:
        return ""


def tail_tunnel_log(n: int = 50) -> str:
    """Return the last n lines of the tunnel log."""
    try:
        with open(TUNNEL_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except OSError:
        return ""
