#!/usr/bin/env python3
"""Live-server smoke test for termux-mcp (REST + MCP Streamable HTTP).

Starts the real server on free loopback ports and validates REST auth plus a
real authenticated MCP initialize -> tools/list -> tools/call round trip.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

TOKEN = os.environ.get("TERMUX_MCP_AUTH_TOKEN", "smoke-test-token-0123456789")

CORE_TOOLS = {
    "run_command",
    "read_file",
    "write_file",
    "list_files",
    "make_directory",
    "get_location",
    "get_battery",
    "send_notification",
    "permissions_status",
}

FAILURES = []


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def http_request(url, method="GET", body=None, headers=None):
    data = None
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def wait_for(url, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            http_request(url)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def wait_for_mcp(url, timeout=15):
    """Wait until the MCP listener answers HTTP, even if the answer is 401."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _ = http_request(url, method="POST", body={})
            if status in (200, 400, 401, 405):
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


async def mcp_flow(mcp_url):
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(
        mcp_url, headers={"Authorization": f"Bearer {TOKEN}"}
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            check(
                "MCP tools/list contains the public core surface",
                CORE_TOOLS.issubset(names),
                f"missing {sorted(CORE_TOOLS - names)}",
            )
            check(
                "Walnut private tools are absent from public main",
                not any(n.startswith(("inbox_", "board_")) for n in names),
                f"got {sorted(names)}",
            )
            res = await session.call_tool("run_command", {"cmd": "echo smoke-ok"})
            text = res.content[0].text
            check(
                "MCP tools/call run_command returns structured JSON",
                all(
                    f'"{k}"' in text
                    for k in (
                        "stdout", "stderr", "exit_code", "truncated",
                        "risk_level", "snapshots",
                    )
                )
                and "smoke-ok" in text,
                text[:120],
            )


def main():
    rest_port = _free_port()
    mcp_port = _free_port()
    rest_url = f"http://127.0.0.1:{rest_port}"
    mcp_url = f"http://127.0.0.1:{mcp_port}/mcp"

    env = dict(os.environ)
    env["TERMUX_MCP_AUTH_TOKEN"] = TOKEN
    env["TERMUX_MCP_HOST"] = "127.0.0.1"
    env["TERMUX_MCP_PORT"] = str(rest_port)
    env["TERMUX_MCP_MCP_HOST"] = "127.0.0.1"
    env["TERMUX_MCP_MCP_PORT"] = str(mcp_port)
    env["TERMUX_MCP_OAUTH_ISSUER"] = ""

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.Popen(
        [sys.executable, "-m", "termux_mcp"],
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        if not wait_for(f"{rest_url}/ping"):
            print("FAIL: REST server did not come up")
            return 1
        if not wait_for_mcp(mcp_url):
            print("FAIL: MCP server did not come up")
            return 1

        status, body = http_request(f"{rest_url}/ping")
        check("REST GET /ping returns 200 without auth", status == 200, body[:80])

        status, _ = http_request(f"{rest_url}/env")
        check("REST GET /env rejects missing Bearer token", status == 401)

        status, _ = http_request(mcp_url, method="POST", body={})
        check("MCP POST /mcp rejects missing Bearer token", status == 401)

        asyncio.run(mcp_flow(mcp_url))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) FAILED")
        return 1
    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
