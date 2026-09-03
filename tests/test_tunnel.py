"""Tests for tunnel provider selection, URL parsing, and auto fallback.

These are pure unit tests — no real network or tunnel binaries are used.
Real tunnel connectivity is covered by the optional integration smoke test
(scripts/mcp_smoke.py) and manual `termux-mcp start --tunnel ...`.
"""

import sys
import time
import urllib.error

import pytest

from termux_mcp import tunnel


# ── HTTPS URL parsing ────────────────────────────────────────────────────────

def test_extract_https_url_pinggy():
    text = "Forwarding traffic... https://abc123.a.free.pinggy.link"
    url = tunnel._extract_https_url(text, tunnel._URL_PATTERNS["pinggy"])
    assert url == "https://abc123.a.free.pinggy.link"


def test_extract_https_url_pinggy_io():
    text = "https://abc123.pinggy.io is live"
    url = tunnel._extract_https_url(text, tunnel._URL_PATTERNS["pinggy"])
    assert url == "https://abc123.pinggy.io"


def test_extract_https_url_cloudflare():
    text = "Your quick Tunnel has been created! Visit it at https://abc-123.trycloudflare.com"
    url = tunnel._extract_https_url(text, tunnel._URL_PATTERNS["cloudflare"])
    assert url == "https://abc-123.trycloudflare.com"


def test_extract_https_url_localhost_run():
    text = "https://abc.lhr.life forwarded to localhost:8765"
    url = tunnel._extract_https_url(text, tunnel._URL_PATTERNS["localhost-run"])
    assert url == "https://abc.lhr.life"


def test_extract_https_url_no_match():
    assert tunnel._extract_https_url("no url here", tunnel._URL_PATTERNS["pinggy"]) is None


# ── Provider selection ───────────────────────────────────────────────────────

def test_get_provider():
    assert tunnel.get_provider("pinggy").name == "pinggy"
    assert tunnel.get_provider("cloudflare").name == "cloudflare"
    assert tunnel.get_provider("localhost-run").name == "localhost-run"
    assert tunnel.get_provider("unknown") is None


def test_start_tunnel_unknown_provider():
    result = tunnel.start_tunnel(8765, provider="unknown", timeout=1)
    assert result.url == ""
    assert "unknown" in result.error


def test_start_tunnel_provider_not_available(monkeypatch):
    class FakePinggy:
        name = "pinggy"

        def available(self):
            return False

        def start(self, port, timeout):
            raise AssertionError("start must not be called when unavailable")

    monkeypatch.setattr(tunnel, "_PROVIDERS", {"pinggy": FakePinggy})
    result = tunnel.start_tunnel(8765, provider="pinggy", timeout=1)
    assert result.url == ""
    assert "not installed" in result.error


# ── Auto fallback ────────────────────────────────────────────────────────────

def test_start_tunnel_auto_fallback(monkeypatch):
    """First provider times out, second succeeds — auto picks the second."""
    class FakePinggy:
        name = "pinggy"

        def available(self):
            return True

        def start(self, port, timeout):
            return tunnel.TunnelResult(provider="pinggy", error="timeout after 1s")

    class FakeCloudflare:
        name = "cloudflare"

        def available(self):
            return True

        def start(self, port, timeout):
            return tunnel.TunnelResult(
                provider="cloudflare", url="https://x.trycloudflare.com"
            )

    monkeypatch.setattr(
        tunnel, "_PROVIDERS", {"pinggy": FakePinggy, "cloudflare": FakeCloudflare}
    )
    monkeypatch.setattr(tunnel, "TUNNEL_PROVIDERS", ["pinggy", "cloudflare"])
    monkeypatch.setattr(tunnel, "verify_url", lambda url: True)
    result = tunnel.start_tunnel(8765, provider="auto", timeout=1)
    assert result.url == "https://x.trycloudflare.com"
    assert result.provider == "cloudflare"


def test_start_tunnel_auto_fallback_on_unreachable_url(monkeypatch):
    """First provider returns a URL that is NOT reachable — auto falls back."""
    class FakePinggy:
        name = "pinggy"

        def available(self):
            return True

        def start(self, port, timeout):
            return tunnel.TunnelResult(
                provider="pinggy", url="https://dead.a.free.pinggy.link"
            )

    class FakeCloudflare:
        name = "cloudflare"

        def available(self):
            return True

        def start(self, port, timeout):
            return tunnel.TunnelResult(
                provider="cloudflare", url="https://x.trycloudflare.com"
            )

    monkeypatch.setattr(
        tunnel, "_PROVIDERS", {"pinggy": FakePinggy, "cloudflare": FakeCloudflare}
    )
    monkeypatch.setattr(tunnel, "TUNNEL_PROVIDERS", ["pinggy", "cloudflare"])
    monkeypatch.setattr(
        tunnel, "verify_url",
        lambda url: url.startswith("https://x.trycloudflare.com"),
    )
    result = tunnel.start_tunnel(8765, provider="auto", timeout=1)
    assert result.url == "https://x.trycloudflare.com"
    assert result.provider == "cloudflare"


def test_start_tunnel_single_provider_unreachable_url(monkeypatch):
    """A single provider whose URL is unreachable must report failure."""
    class FakePinggy:
        name = "pinggy"

        def available(self):
            return True

        def start(self, port, timeout):
            return tunnel.TunnelResult(
                provider="pinggy", url="https://dead.a.free.pinggy.link"
            )

    monkeypatch.setattr(tunnel, "_PROVIDERS", {"pinggy": FakePinggy})
    monkeypatch.setattr(tunnel, "verify_url", lambda url: False)
    result = tunnel.start_tunnel(8765, provider="pinggy", timeout=1)
    assert result.url == ""
    assert "not reachable" in result.error


def test_start_tunnel_auto_all_fail(monkeypatch):
    class FakePinggy:
        name = "pinggy"

        def available(self):
            return True

        def start(self, port, timeout):
            return tunnel.TunnelResult(provider="pinggy", error="timeout")

    monkeypatch.setattr(tunnel, "_PROVIDERS", {"pinggy": FakePinggy})
    monkeypatch.setattr(tunnel, "TUNNEL_PROVIDERS", ["pinggy"])
    result = tunnel.start_tunnel(8765, provider="auto", timeout=1)
    assert result.url == ""
    assert "all configured providers failed" in result.error


def test_start_tunnel_auto_skips_unavailable(monkeypatch):
    class FakePinggy:
        name = "pinggy"

        def available(self):
            return False

        def start(self, port, timeout):
            raise AssertionError("unavailable provider must be skipped")

    class FakeCloudflare:
        name = "cloudflare"

        def available(self):
            return True

        def start(self, port, timeout):
            return tunnel.TunnelResult(
                provider="cloudflare", url="https://x.trycloudflare.com"
            )

    monkeypatch.setattr(
        tunnel, "_PROVIDERS", {"pinggy": FakePinggy, "cloudflare": FakeCloudflare}
    )
    monkeypatch.setattr(tunnel, "TUNNEL_PROVIDERS", ["pinggy", "cloudflare"])
    monkeypatch.setattr(tunnel, "verify_url", lambda url: True)
    result = tunnel.start_tunnel(8765, provider="auto", timeout=1)
    assert result.url == "https://x.trycloudflare.com"


# ── URL verification ─────────────────────────────────────────────────────────

def test_verify_url_401_counts_reachable(monkeypatch):
    """401 (auth working) must count as reachable."""
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", None, None)

    monkeypatch.setattr(tunnel.urllib.request, "urlopen", fake_urlopen)
    assert tunnel.verify_url("https://x.trycloudflare.com") is True


def test_verify_url_200_reachable(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        return FakeResp()

    monkeypatch.setattr(tunnel.urllib.request, "urlopen", fake_urlopen)
    assert tunnel.verify_url("https://x.trycloudflare.com") is True


def test_verify_url_unreachable(monkeypatch):
    def fake_urlopen(req, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(tunnel.urllib.request, "urlopen", fake_urlopen)
    assert tunnel.verify_url("https://x.trycloudflare.com") is False


def test_verify_url_probes_mcp_endpoint(monkeypatch):
    """Health probe must hit {url}/mcp without any Authorization header."""
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", None, None)

    monkeypatch.setattr(tunnel.urllib.request, "urlopen", fake_urlopen)
    assert tunnel.verify_url("https://x.trycloudflare.com") is True
    assert seen["url"] == "https://x.trycloudflare.com/mcp"
    assert seen["auth"] is None


def test_verify_url_530_unreachable(monkeypatch):
    """Cloudflare 530 (origin unreachable) must count as unreachable."""
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 530, "Origin DNS error", None, None)

    monkeypatch.setattr(tunnel.urllib.request, "urlopen", fake_urlopen)
    assert tunnel.verify_url("https://x.trycloudflare.com") is False


# ── Provider command construction ────────────────────────────────────────────

def test_pinggy_command_non_interactive(monkeypatch):
    """Pinggy must use the verified non-interactive SSH flags."""
    captured = {}

    def fake_run(provider, cmd, patterns, timeout):
        captured["cmd"] = cmd
        return tunnel.TunnelResult(provider=provider, url="https://x.a.free.pinggy.link")

    monkeypatch.setattr(tunnel, "_run_and_wait_for_url", fake_run)
    result = tunnel.get_provider("pinggy").start(8765, timeout=10)
    assert result.url == "https://x.a.free.pinggy.link"
    cmd = captured["cmd"]
    assert cmd[0] == "ssh"
    assert "-p" in cmd and cmd[cmd.index("-p") + 1] == "443"
    assert "-o" in cmd
    opts = cmd[cmd.index("-o") + 1 : cmd.index("-R")]
    assert "StrictHostKeyChecking=no" in opts
    assert "ServerAliveInterval=30" in opts
    assert "BatchMode=yes" in opts
    assert "ConnectTimeout=15" in opts
    assert "ExitOnForwardFailure=yes" in opts
    assert f"0:127.0.0.1:8765" in cmd
    assert "a@free.pinggy.io" in cmd


def test_localhost_run_command_non_interactive(monkeypatch):
    captured = {}

    def fake_run(provider, cmd, patterns, timeout):
        captured["cmd"] = cmd
        return tunnel.TunnelResult(provider=provider, url="https://x.lhr.life")

    monkeypatch.setattr(tunnel, "_run_and_wait_for_url", fake_run)
    result = tunnel.get_provider("localhost-run").start(8765, timeout=10)
    assert result.url == "https://x.lhr.life"
    cmd = captured["cmd"]
    assert cmd[0] == "ssh"
    assert "BatchMode=yes" in cmd
    assert "StrictHostKeyChecking=no" in cmd
    assert f"80:127.0.0.1:8765" in cmd
    assert "nokey@localhost.run" in cmd


# ── Real subprocess + tunnel log ─────────────────────────────────────────────

def test_run_and_wait_writes_tunnel_log_and_returns_process(tmp_path, monkeypatch):
    """A real subprocess that prints a URL must: return the URL, keep the
    process alive, and persist its output to tunnel.log."""
    from termux_mcp import process as proc_mod

    monkeypatch.setattr(proc_mod, "TUNNEL_LOG_FILE", str(tmp_path / "tunnel.log"))
    # A tiny python child that prints a pinggy URL then sleeps.
    code = (
        "import sys,time;"
        "print('Forwarding traffic... https://abc123.a.free.pinggy.link');"
        "sys.stdout.flush();time.sleep(30)"
    )
    result = tunnel._run_and_wait_for_url(
        "pinggy",
        [sys.executable, "-c", code],
        tunnel._URL_PATTERNS["pinggy"],
        timeout=10,
    )
    try:
        assert result.url == "https://abc123.a.free.pinggy.link"
        assert result.process is not None
        assert result.process.poll() is None  # still alive
        # tunnel.log must contain the child's output.
        log = (tmp_path / "tunnel.log").read_text(encoding="utf-8", errors="replace")
        assert "abc123.a.free.pinggy.link" in log
    finally:
        if result.process:
            tunnel._terminate(result.process)


def test_run_and_wait_auth_prompt_fails_fast(tmp_path, monkeypatch):
    """An SSH password prompt must fail fast (never block until timeout)."""
    from termux_mcp import process as proc_mod

    monkeypatch.setattr(proc_mod, "TUNNEL_LOG_FILE", str(tmp_path / "tunnel.log"))
    code = (
        "import sys,time;"
        "print(\"a@free.pinggy.io's password:\");"
        "sys.stdout.flush();time.sleep(30)"
    )
    t0 = time.time()
    result = tunnel._run_and_wait_for_url(
        "pinggy",
        [sys.executable, "-c", code],
        tunnel._URL_PATTERNS["pinggy"],
        timeout=30,
    )
    elapsed = time.time() - t0
    assert result.url == ""
    assert "interactive auth required" in result.error
    assert elapsed < 10  # must not wait for the full timeout