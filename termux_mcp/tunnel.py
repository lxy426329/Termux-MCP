"""Tunnel providers for exposing the local MCP endpoint publicly.

Supported providers (order is configurable via TERMUX_MCP_TUNNEL_PROVIDERS):
  * pinggy        — `ssh -p 443 -R0:localhost:<port> a@free.pinggy.io`
  * cloudflare    — `cloudflared tunnel --url http://127.0.0.1:<port>`
  * localhost-run — `ssh -R 80:localhost:<port> nokey@localhost.run`

`start_tunnel(port, "auto")` tries each available provider in order, gives
each a bounded timeout, terminates a provider that hangs, and returns the
first public HTTPS URL that appears. Tunnel URLs are deployment-sensitive
and are never uploaded anywhere.
"""

import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from . import process
from .config import TUNNEL_PROVIDERS, TUNNEL_TIMEOUT

# URL patterns per provider, in priority order.
_URL_PATTERNS = {
    "pinggy": [
        r"https://[a-zA-Z0-9-]+\.a\.free\.pinggy\.link",
        r"https://[a-zA-Z0-9-]+\.pinggy\.io",
        r"https://[a-zA-Z0-9-]+\.pinggy\.link",
    ],
    "cloudflare": [
        r"https://[a-zA-Z0-9-]+\.trycloudflare\.com",
    ],
    "localhost-run": [
        r"https://[a-zA-Z0-9-]+\.lhr\.life",
        r"https://[a-zA-Z0-9-]+\.lhr\.rocks",
    ],
}

# Output markers that mean the tunnel needs interactive auth (fail fast).
_AUTH_PROMPT_MARKERS = (
    "password:",
    "Password:",
    "passphrase",
    "Enter passphrase",
    "Host key verification failed",
    "Permission denied",
)


@dataclass
class TunnelResult:
    provider: str
    url: str = ""
    process: Optional[subprocess.Popen] = None
    error: str = ""


class TunnelProvider(ABC):
    name: str = ""

    @abstractmethod
    def available(self) -> bool:
        """True when the provider's binary is installed."""

    @abstractmethod
    def start(self, port: int, timeout: int) -> TunnelResult:
        """Start the tunnel and return the public URL (or an error)."""


def _extract_https_url(text: str, patterns: List[str]) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0).rstrip("/")
    return None


def _run_and_wait_for_url(
    provider: str,
    cmd: List[str],
    patterns: List[str],
    timeout: int,
) -> TunnelResult:
    """Run a tunnel command, watch its output for a public URL.

    Output is read on a background thread into a queue so the timeout is
    always honored even if the tunnel process goes completely silent
    (e.g. cloudflared stuck in precheck). Every line is also appended to
    the tunnel log (~/.local/state/termux-mcp/tunnel.log) so failures can
    be diagnosed later. stdin is /dev/null so an SSH password prompt can
    never block the launcher. Terminates the process on timeout or when an
    auth prompt appears.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        env=os.environ.copy(),
    )
    out_q: "queue.Queue[str]" = queue.Queue()
    log_path = process.TUNNEL_LOG_FILE

    def _reader() -> None:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8", errors="replace") as log_f:
                for line in proc.stdout:
                    out_q.put(line)
                    log_f.write(line)
                    log_f.flush()
        except Exception:
            pass

    threading.Thread(target=_reader, daemon=True).start()

    deadline = time.time() + timeout
    buf = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = ""
            while True:
                try:
                    tail += out_q.get_nowait()
                except queue.Empty:
                    break
            return TunnelResult(
                provider=provider,
                process=proc,
                error=f"exited early (code {proc.returncode}): {tail[-300:]}",
            )
        try:
            line = out_q.get(timeout=0.2)
        except queue.Empty:
            continue
        buf += line
        if any(marker in line for marker in _AUTH_PROMPT_MARKERS):
            _terminate(proc)
            return TunnelResult(
                provider=provider,
                process=None,
                error=f"interactive auth required: {line.strip()[:120]}",
            )
        url = _extract_https_url(buf, patterns)
        if url:
            return TunnelResult(provider=provider, url=url, process=proc)
    _terminate(proc)
    return TunnelResult(
        provider=provider,
        process=None,
        error=f"timeout after {timeout}s (no public URL)",
    )


def _terminate(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


class PinggyProvider(TunnelProvider):
    name = "pinggy"

    def available(self) -> bool:
        return shutil.which("ssh") is not None

    def start(self, port: int, timeout: int) -> TunnelResult:
        # Non-interactive flags verified on-device:
        #   -p 443, StrictHostKeyChecking=no, ServerAliveInterval=30,
        #   BatchMode=yes (never prompt for a password), ConnectTimeout,
        #   ExitOnForwardFailure, and 127.0.0.1 (avoid IPv6 localhost).
        cmd = [
            "ssh", "-p", "443",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=30",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=15",
            "-o", "ExitOnForwardFailure=yes",
            "-R", f"0:127.0.0.1:{port}",
            "a@free.pinggy.io",
        ]
        return _run_and_wait_for_url(self.name, cmd, _URL_PATTERNS[self.name], timeout)


class CloudflareProvider(TunnelProvider):
    name = "cloudflare"

    def available(self) -> bool:
        return shutil.which("cloudflared") is not None

    def start(self, port: int, timeout: int) -> TunnelResult:
        cmd = ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}"]
        return _run_and_wait_for_url(self.name, cmd, _URL_PATTERNS[self.name], timeout)


class LocalhostRunProvider(TunnelProvider):
    name = "localhost-run"

    def available(self) -> bool:
        return shutil.which("ssh") is not None

    def start(self, port: int, timeout: int) -> TunnelResult:
        cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=30",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=15",
            "-o", "ExitOnForwardFailure=yes",
            "-R", f"80:127.0.0.1:{port}",
            "nokey@localhost.run",
        ]
        return _run_and_wait_for_url(self.name, cmd, _URL_PATTERNS[self.name], timeout)


_PROVIDERS = {
    "pinggy": PinggyProvider,
    "cloudflare": CloudflareProvider,
    "localhost-run": LocalhostRunProvider,
}


def get_provider(name: str) -> Optional[TunnelProvider]:
    cls = _PROVIDERS.get(name)
    return cls() if cls else None


def start_tunnel(
    port: int,
    provider: str = "auto",
    timeout: Optional[int] = None,
) -> TunnelResult:
    """Start a tunnel and return the first public URL.

    `provider="auto"` tries each configured provider in order
    (TERMUX_MCP_TUNNEL_PROVIDERS), skipping unavailable ones and falling
    back on timeout/failure. A provider only counts as successful once its
    public URL is actually reachable (see verify_url) — a parsed URL that
    does not answer (e.g. Cloudflare 530) is treated as a failure.
    """
    timeout = timeout or TUNNEL_TIMEOUT
    last_error = ""
    if provider == "auto":
        for name in TUNNEL_PROVIDERS:
            p = get_provider(name)
            if p is None or not p.available():
                continue
            result = p.start(port, timeout)
            if result.url:
                if verify_url(result.url):
                    return result
                if result.process:
                    _terminate(result.process)
                last_error = f"{name}: public URL not reachable: {result.url}"
                continue
            last_error = f"{name}: {result.error}"
        return TunnelResult(
            provider="auto",
            error=f"all configured providers failed: {last_error}",
        )
    p = get_provider(provider)
    if p is None:
        return TunnelResult(provider=provider, error=f"unknown provider: {provider}")
    if not p.available():
        return TunnelResult(
            provider=provider,
            error=f"{provider} is not installed (install ssh/cloudflared)",
        )
    result = p.start(port, timeout)
    if result.url and not verify_url(result.url):
        if result.process:
            _terminate(result.process)
        return TunnelResult(
            provider=provider,
            error=f"public URL not reachable: {result.url}",
        )
    return result


def verify_url(url: str, timeout: float = 15.0) -> bool:
    """Check that a public MCP endpoint is reachable.

    Probes `{url}/mcp` without any Authorization header. Any HTTP response
    (including 401 — auth working as intended) counts as reachable; only
    network-level failures and Cloudflare 530 (origin unreachable) count as
    unreachable.
    """
    probe = url.rstrip("/")
    if not probe.endswith("/mcp"):
        probe += "/mcp"
    try:
        req = urllib.request.Request(probe, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True
    except urllib.error.HTTPError as e:
        return e.code in (200, 401, 403, 404)
    except Exception:
        return False