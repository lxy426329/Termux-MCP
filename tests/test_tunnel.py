"""Tests for tunnel provider selection, URL parsing, and auto fallback.

These are pure unit tests — no real network or tunnel binaries are used.
Real tunnel connectivity is covered by the optional integration smoke test
(scripts/mcp_smoke.py) and manual `termux-mcp start --tunnel ...`.
"""

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
    result = tunnel.start_tunnel(8765, provider="auto", timeout=1)
    assert result.url == "https://x.trycloudflare.com"
    assert result.provider == "cloudflare"


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