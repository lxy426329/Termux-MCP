"""Tests for the MCP Streamable HTTP layer.

The MCP app is served by a real uvicorn server (lifespan runs the session
manager's task group), then exercised with plain HTTP for auth checks and
with the official SDK client for tools/list + tools/call smoke tests.
"""

import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from termux_mcp.config import AUTH_TOKEN
from termux_mcp.mcp_server import _build_mcp_app

EXPECTED_TOOLS = [
    "run_command",
    "read_file",
    "write_file",
    "list_files",
    "make_directory",
    "get_location",
    "get_battery",
    "send_notification",
]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def mcp_server():
    port = _free_port()
    app = _build_mcp_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/mcp"
    # Wait for the server to accept connections.
    for _ in range(100):
        try:
            httpx.get(url, timeout=0.3)
            break
        except Exception:
            time.sleep(0.1)
    yield url
    server.should_exit = True
    thread.join(timeout=5)


# ── Authentication ───────────────────────────────────────────────────────────

def test_mcp_requires_auth(mcp_server):
    r = httpx.post(mcp_server, json={})
    assert r.status_code == 401


def test_mcp_rejects_wrong_token(mcp_server):
    r = httpx.post(
        mcp_server, json={},
        headers={"Authorization": "Bearer wrong-token-0000000000000000"},
    )
    assert r.status_code == 401


def test_mcp_accepts_valid_token(mcp_server):
    r = httpx.post(
        mcp_server, json={},
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    )
    # Passes the auth middleware; the MCP layer answers with its own
    # protocol-level response (never 401).
    assert r.status_code != 401


def test_mcp_rejects_token_in_query_string(mcp_server):
    # Tokens in URL query parameters must NOT be supported.
    r = httpx.post(f"{mcp_server}?token={AUTH_TOKEN}", json={})
    assert r.status_code == 401


# ── Smoke: tools/list + tools/call ──────────────────────────────────────────

def test_tools_list_and_call_smoke(mcp_server):
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def run():
        async with streamablehttp_client(
            mcp_server,
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # tools/list
                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                assert names == EXPECTED_TOOLS

                # tools/call — run_command returns structured JSON
                res = await session.call_tool("run_command", {"cmd": "echo hello"})
                assert res.isError is False
                text = res.content[0].text
                for key in ("stdout", "stderr", "exit_code", "truncated",
                            "risk_level", "snapshots"):
                    assert f'"{key}"' in text
                assert "hello" in text

    asyncio.run(run())


def test_tools_call_dangerous_blocked(mcp_server):
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def run():
        async with streamablehttp_client(
            mcp_server,
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("run_command", {"cmd": "rm -rf /"})
                text = res.content[0].text
                assert '"blocked": true' in text
                assert '"risk_level": "dangerous"' in text

    asyncio.run(run())


def test_tools_call_warning_confirmation_required(mcp_server):
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def run():
        async with streamablehttp_client(
            mcp_server,
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("run_command", {"cmd": "rm -rf somefile"})
                text = res.content[0].text
                assert '"confirmation_required": true' in text
                assert '"risk_level": "warning"' in text

    asyncio.run(run())