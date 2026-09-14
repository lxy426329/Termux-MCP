"""Security regression tests for the public OAuth approval boundary."""

import socket
import threading
import time

import httpx
import uvicorn

from termux_mcp import config, oauth
from termux_mcp.auth import reset_auth_provider
from termux_mcp.mcp_server import _build_mcp_app


def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _start_server(app):
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(base + "/mcp", timeout=0.3)
            break
        except Exception:
            time.sleep(0.1)
    return server, thread, base


def test_public_authorize_denied_without_explicit_auto_approve(monkeypatch):
    monkeypatch.setattr(config, "OAUTH_ISSUER", "https://mcp.example.com")
    monkeypatch.setattr(config, "PUBLIC_URL", "https://mcp.example.com")
    monkeypatch.setattr(config, "OAUTH_AUTO_APPROVE", False)
    config.clear_public_url()
    reset_auth_provider()
    oauth.reset_auth_server_provider()

    app = _build_mcp_app()
    server, thread, base = _start_server(app)
    try:
        response = httpx.get(base + "/authorize")
        assert response.status_code == 403
        body = response.json()
        assert body["error"] == "access_denied"
        assert "automatic approval is disabled" in body["error_description"]
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        reset_auth_provider()
        oauth.reset_auth_server_provider()
